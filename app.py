"""Minecraft Factory Monitor: RCON -> SQLite -> authenticated FastAPI dashboard.

Run with ``python app.py`` on the Minecraft server computer.
All RCON operations are read-only; no forceloads or game settings are changed.
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from mcrcon import MCRcon
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.environ.get("FM_DB_PATH", str(DATA_DIR / "factory.db")))
RCON_HOST = os.environ.get("RCON_HOST", "127.0.0.1")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
RCON_PASSWORD = os.environ.get("RCON_PASSWORD", "")
FM_USER = os.environ.get("FM_USER", "admin")
FM_PASSWORD = os.environ.get("FM_PASSWORD", "")
POLL_SECONDS = max(5, int(os.environ.get("FM_POLL_SECONDS", "10")))
DISABLE_COLLECTOR = os.environ.get("FM_DISABLE_COLLECTOR", "0") == "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("factory-monitor")
ITEM_RE = re.compile(r'\{[^{}]*\}')
COUNT_RE = re.compile(r'\bcount\s*:\s*(\d+)(?:[bBsSlL])?\b')
ID_RE = re.compile(r'\bid\s*:\s*"([a-z0-9_.-]+:[a-z0-9_./-]+)"')
IDENT_RE = re.compile(r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')


class FactoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    dimension: str = "minecraft:overworld"
    item_id: str = "minecraft:gunpowder"
    containers: list[tuple[int, int, int]] = Field(min_length=1, max_length=32)
    slots_per_container: int = Field(default=27, ge=1, le=108)
    stack_size: int = Field(default=64, ge=1, le=99)

    @field_validator("dimension", "item_id")
    @classmethod
    def valid_identifier(cls, value: str) -> str:
        if not IDENT_RE.fullmatch(value):
            raise ValueError("minecraft:overworld 같은 네임스페이스 ID가 필요합니다")
        return value

    @field_validator("containers")
    @classmethod
    def unique_containers(cls, value: list[tuple[int, int, int]]):
        if len(set(value)) != len(value):
            raise ValueError("중복 상자 좌표가 있습니다")
        for x, y, z in value:
            if abs(x) > 30_000_000 or abs(z) > 30_000_000 or not (-2032 <= y <= 2032):
                raise ValueError("좌표가 유효 범위를 벗어났습니다")
        return value


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    db = sqlite3.connect(DB_PATH, timeout=15)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=15000")
        with db:
            yield db
    finally:
        db.close()


def initialize_db() -> None:
    with get_conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS factories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            dimension TEXT NOT NULL,
            item_id TEXT NOT NULL,
            containers_json TEXT NOT NULL,
            slots_per_container INTEGER NOT NULL DEFAULT 27,
            stack_size INTEGER NOT NULL DEFAULT 64,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factory_id TEXT NOT NULL REFERENCES factories(id) ON DELETE CASCADE,
            ts TEXT NOT NULL,
            stock INTEGER,
            delta INTEGER,
            status TEXT NOT NULL CHECK(status IN ('ok', 'error')),
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS samples_by_factory_time
            ON samples(factory_id, ts);
        """)
        has_factories = db.execute("SELECT EXISTS(SELECT 1 FROM factories)").fetchone()[0]
        if not has_factories:
            config_file = ROOT / "factories.json"
            if config_file.exists():
                for obj in json.loads(config_file.read_text(encoding="utf-8")):
                    factory = FactoryCreate.model_validate(obj)
                    insert_factory(db, factory)
                log.info("기본 공장 등록 완료")


def insert_factory(db: sqlite3.Connection, f: FactoryCreate) -> str:
    factory_id = uuid.uuid4().hex[:12]
    db.execute("""INSERT INTO factories
        (id, name, dimension, item_id, containers_json, slots_per_container,
         stack_size, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        (factory_id, f.name.strip(), f.dimension, f.item_id,
         json.dumps(f.containers), f.slots_per_container, f.stack_size, now_iso()))
    return factory_id


def parse_stock(response: str, item_id: str) -> int:
    """Parse Minecraft /data get Items SNBT. Fail closed on unexpected output."""
    if "has the following block data:" not in response:
        raise ValueError("상자 조회 실패: " + response[:250])
    body = response.split("has the following block data:", 1)[1].strip()
    if body == "[]":
        return 0
    if not body.startswith("[") or not body.endswith("]"):
        raise ValueError("예상하지 못한 RCON 응답 형식")
    items = ITEM_RE.findall(body)
    if not items:
        raise ValueError("아이템 목록 분석 실패")
    result = 0
    for raw in items:
        id_match = ID_RE.search(raw)
        count_match = COUNT_RE.search(raw)
        if id_match is None or count_match is None:
            raise ValueError("아이템 ID 또는 count 파싱 실패")
        if id_match.group(1) == item_id:
            result += int(count_match.group(1))
    return result


def read_inventory(mc: MCRcon, f: sqlite3.Row) -> int:
    containers = json.loads(f["containers_json"])
    stock = 0
    for x, y, z in containers:
        command = (f"execute in {f['dimension']} run "
                   f"data get block {x} {y} {z} Items")
        stock += parse_stock(mc.command(command), f["item_id"])
    return stock


def record_sample(db: sqlite3.Connection, factory_id: str, stock: int | None,
                  error: str | None = None, ts: str | None = None) -> None:
    ts = ts or now_iso()
    last = db.execute(
        "SELECT ts, stock, status FROM samples WHERE factory_id=? ORDER BY id DESC LIMIT 1",
        (factory_id,)
    ).fetchone()
    delta = None
    if stock is not None and last and last["status"] == "ok":
        gap = (datetime.fromisoformat(ts) - datetime.fromisoformat(last["ts"])).total_seconds()
        if 0 <= gap <= max(45, POLL_SECONDS * 3):
            delta = stock - last["stock"]
    db.execute("""INSERT INTO samples(factory_id, ts, stock, delta, status, error)
                 VALUES (?, ?, ?, ?, ?, ?)""",
               (factory_id, ts, stock, delta,
                "error" if stock is None else "ok", error[:400] if error else None))


def poll_once() -> None:
    with get_conn() as db:
        factories = db.execute("SELECT * FROM factories WHERE enabled=1").fetchall()
    if not factories:
        return
    # One RCON connection per collection cycle; an error does not crash the web server.
    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mc:
            for f in factories:
                try:
                    stock = read_inventory(mc, f)
                    with get_conn() as db:
                        record_sample(db, f["id"], stock)
                    log.debug("%s stock=%s", f["name"], stock)
                except Exception as exc:
                    log.warning("공장 %s 조회 실패: %s", f["name"], exc)
                    with get_conn() as db:
                        record_sample(db, f["id"], None, str(exc))
    except Exception as exc:
        log.warning("RCON 연결 실패: %s", type(exc).__name__)
        with get_conn() as db:
            for f in factories:
                record_sample(db, f["id"], None, f"RCON 연결 실패: {type(exc).__name__}")


async def collector_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        started = time.monotonic()
        await asyncio.to_thread(poll_once)
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(1, POLL_SECONDS - (time.monotonic() - started)))
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not FM_PASSWORD or FM_PASSWORD.startswith("REPLACE_") or len(FM_PASSWORD) < 12:
        raise RuntimeError(".env FM_PASSWORD를 길이 12자 이상의 비밀번호로 설정하세요")
    if not DISABLE_COLLECTOR and (not RCON_PASSWORD or RCON_PASSWORD.startswith("REPLACE_")):
        raise RuntimeError(".env RCON_PASSWORD를 설정하세요")
    initialize_db()
    stop = asyncio.Event()
    task = None
    if not DISABLE_COLLECTOR:
        task = asyncio.create_task(collector_loop(stop))
    try:
        yield
    finally:
        stop.set()
        if task:
            await task


app = FastAPI(title="Minecraft Factory Monitor", version="0.1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def authentication(request: Request, call_next):
    header = request.headers.get("authorization", "")
    user, password = "", ""
    if header.startswith("Basic "):
        try:
            data = base64.b64decode(header.split(" ", 1)[1], validate=True).decode("utf-8")
            user, password = data.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            pass
    if not (hmac.compare_digest(user, FM_USER) and
            hmac.compare_digest(password, FM_PASSWORD) and FM_PASSWORD):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Factory Monitor", charset="UTF-8"',
                                                  "Cache-Control": "no-store"})
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


def aggregate_stats(db: sqlite3.Connection, factory_id: str, window_minutes: int) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat(timespec="seconds")
    rows = db.execute("""SELECT s.ts, s.delta,
                    (SELECT p.ts FROM samples p WHERE p.factory_id=s.factory_id AND p.id<s.id
                     ORDER BY p.id DESC LIMIT 1) AS prev_ts
                    FROM samples s
                    WHERE s.factory_id=? AND s.ts>=? AND s.status='ok' AND s.delta IS NOT NULL
                    ORDER BY s.id""", (factory_id, cutoff)).fetchall()
    inbound = sum(max(row["delta"], 0) for row in rows)
    outbound = sum(-min(row["delta"], 0) for row in rows)
    # Only count measured intervals; outages/unobserved gaps must not imply zero flow.
    covered_seconds = sum(max(0, (datetime.fromisoformat(r["ts"]) -
                                  datetime.fromisoformat(r["prev_ts"])).total_seconds())
                          for r in rows if r["prev_ts"])
    net_rate = (inbound - outbound) / covered_seconds if covered_seconds else None
    in_rate = inbound / covered_seconds if covered_seconds else None
    return {"in": inbound, "out": outbound, "net": inbound - outbound,
            "net_per_second": round(net_rate, 4) if net_rate is not None else None,
            "in_per_second": round(in_rate, 4) if in_rate is not None else None,
            "covered_intervals": len(rows), "covered_seconds": covered_seconds,
            "window_minutes": window_minutes}


def factory_detail(db: sqlite3.Connection, f: sqlite3.Row) -> dict[str, Any]:
    latest = db.execute("SELECT * FROM samples WHERE factory_id=? ORDER BY id DESC LIMIT 1",
                        (f["id"],)).fetchone()
    last_in = db.execute("""SELECT ts FROM samples WHERE factory_id=? AND delta>0
                        ORDER BY id DESC LIMIT 1""", (f["id"],)).fetchone()
    capacity = (len(json.loads(f["containers_json"])) * f["slots_per_container"] * f["stack_size"])
    status = "paused" if not f["enabled"] else "waiting"
    if f["enabled"] and latest:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest["ts"])).total_seconds()
        if age > max(POLL_SECONDS * 3, 45):
            status = "stale"
        elif latest["status"] == "error":
            status = "error"
        else:
            status = "ok"  # Successfully observed, not proof of mob-spawning activity.
    return {
        "id": f["id"], "name": f["name"], "dimension": f["dimension"],
        "item_id": f["item_id"], "containers": json.loads(f["containers_json"]),
        "slots_per_container": f["slots_per_container"], "stack_size": f["stack_size"],
        "enabled": bool(f["enabled"]), "capacity": capacity,
        "status": status, "stock": latest["stock"] if latest and latest["status"] == "ok" else None,
        "last_checked": latest["ts"] if latest else None,
        "error": latest["error"] if latest and latest["status"] == "error" else None,
        "last_inbound_at": last_in["ts"] if last_in else None,
        "stats_10m": aggregate_stats(db, f["id"], 10),
        "stats_1h": aggregate_stats(db, f["id"], 60),
    }


@app.get("/api/factories")
def list_factories():
    with get_conn() as db:
        return {"server_time": now_iso(), "poll_seconds": POLL_SECONDS,
                "factories": [factory_detail(db, f) for f in db.execute("SELECT * FROM factories ORDER BY created_at, name")]}


@app.post("/api/factories", status_code=201)
def add_factory(f: FactoryCreate):
    with get_conn() as db:
        fid = insert_factory(db, f)
        row = db.execute("SELECT * FROM factories WHERE id=?", (fid,)).fetchone()
        return factory_detail(db, row)


@app.patch("/api/factories/{fid}/enabled")
def toggle_factory(fid: str, enabled: bool):
    with get_conn() as db:
        cur = db.execute("UPDATE factories SET enabled=? WHERE id=?", (int(enabled), fid))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="공장을 찾지 못했습니다")
        return {"ok": True, "enabled": enabled}


@app.get("/api/factories/{fid}/history")
def history(fid: str, hours: int = 24):
    hours = max(1, min(hours, 168))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with get_conn() as db:
        if not db.execute("SELECT 1 FROM factories WHERE id=?", (fid,)).fetchone():
            raise HTTPException(status_code=404, detail="공장을 찾지 못했습니다")
        rows = [dict(r) for r in db.execute("""SELECT ts, stock, delta, status, error FROM samples
                       WHERE factory_id=? AND ts>=? ORDER BY id ASC""", (fid, cutoff))]
        events = [r for r in rows if r["delta"] is not None and r["delta"] != 0][-30:]
        # Graph downsampling; store all samples in SQLite regardless of chart density.
        if len(rows) > 600:
            stride = (len(rows) - 1) // 599 + 1
            chart = rows[::stride]
            if chart[-1] is not rows[-1]:
                chart.append(rows[-1])
        else:
            chart = rows
        return {"history": chart, "events": list(reversed(events)), "total_samples": len(rows)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("FM_PORT", "8000")), log_level="info")