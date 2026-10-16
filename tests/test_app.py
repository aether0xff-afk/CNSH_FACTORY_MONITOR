"""Offline tests. Run: python -m unittest discover -s tests -v"""
import base64
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.modules.setdefault("mcrcon", types.SimpleNamespace(MCRcon=object))
os.environ["FM_USER"] = "test-user"
os.environ["FM_PASSWORD"] = "a-test-password-long-enough"
os.environ["RCON_PASSWORD"] = "fake-rcon-secret"
os.environ["FM_DISABLE_COLLECTOR"] = "1"
import app as mon
from fastapi.testclient import TestClient

SAMPLE_EMPTY = "100, 64, 200 has the following block data: []"
SAMPLE_ITEMS = ('101, 64, 200 has the following block data: '
    + '[' + ', '.join(
       '{count: 64, Slot: %db, id: "minecraft:gunpowder"}' % i
       for i in range(11)
    ) + ', {count: 34, Slot: 11b, id: "minecraft:gunpowder"}]')


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = mon.DB_PATH
        mon.DB_PATH = Path(self.tmp.name) / "test.db"
        mon.initialize_db()
        # Never depend on a private factories.json file.
        with mon.get_conn() as db:
            db.execute("DELETE FROM factories")
            mon.insert_factory(db, mon.FactoryCreate(
                name="Test creeper farm", dimension="minecraft:overworld",
                item_id="minecraft:gunpowder",
                containers=[(100, 64, 200), (101, 64, 200)]))
        self.client_context = TestClient(mon.app)
        self.client = self.client_context.__enter__()
        self.headers = {"Authorization": "Basic " + base64.b64encode(
            b"test-user:a-test-password-long-enough").decode()}

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        mon.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def test_parse_stock(self):
        self.assertEqual(mon.parse_stock(SAMPLE_EMPTY, "minecraft:gunpowder"), 0)
        self.assertEqual(mon.parse_stock(SAMPLE_ITEMS, "minecraft:gunpowder"), 738)
        self.assertEqual(mon.parse_stock(SAMPLE_ITEMS, "minecraft:iron_ingot"), 0)
        with self.assertRaises(ValueError):
            mon.parse_stock("Target position is not loaded", "minecraft:gunpowder")

    def test_auth_and_seed(self):
        self.assertEqual(self.client.get("/").status_code, 401)
        self.assertEqual(self.client.get("/api/factories").status_code, 401)
        self.assertEqual(self.client.get("/", headers=self.headers).status_code, 200)
        rows = self.client.get("/api/factories", headers=self.headers).json()["factories"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "waiting")
        self.assertEqual(rows[0]["capacity"], 3456)
        self.assertEqual(rows[0]["containers"], [[100,64,200],[101,64,200]])

    def test_net_changes_and_error_gap(self):
        fid = self.client.get("/api/factories", headers=self.headers).json()["factories"][0]["id"]
        with mon.get_conn() as db:
            mon.record_sample(db,fid,738,ts="2026-10-17T00:00:00+00:00")
            mon.record_sample(db,fid,748,ts="2026-10-17T00:00:10+00:00")
            mon.record_sample(db,fid,684,ts="2026-10-17T00:00:20+00:00")
            mon.record_sample(db,fid,None,error="unloaded",ts="2026-10-17T00:00:30+00:00")
            mon.record_sample(db,fid,900,ts="2026-10-17T00:00:40+00:00")
            rows=db.execute("SELECT stock,delta FROM samples WHERE factory_id=? ORDER BY id",(fid,)).fetchall()
        self.assertEqual([(r["stock"],r["delta"]) for r in rows],
                         [(738,None),(748,10),(684,-64),(None,None),(900,None)])

    def test_poll_rcon(self):
        class FakeMCRcon:
            def __init__(self, host, password, port): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def command(self, command):
                if "100 64 200" in command: return SAMPLE_EMPTY
                if "101 64 200" in command: return SAMPLE_ITEMS
                raise AssertionError(command)
        old=mon.MCRcon
        mon.MCRcon=FakeMCRcon
        try: mon.poll_once()
        finally: mon.MCRcon=old
        f=self.client.get("/api/factories",headers=self.headers).json()["factories"][0]
        self.assertEqual(f["stock"],738)
        self.assertEqual(f["status"],"ok")
        self.assertIsNone(f["stats_10m"]["net_per_second"])
        h=self.client.get(f"/api/factories/{f['id']}/history?hours=1",headers=self.headers).json()
        self.assertEqual(h["history"][-1]["stock"],738)

    def test_registration_and_pause(self):
        payload={"name":"철 농장","item_id":"minecraft:iron_ingot",
                 "dimension":"minecraft:overworld","containers":[[12,64,32]]}
        result=self.client.post("/api/factories",headers=self.headers,json=payload)
        self.assertEqual(result.status_code,201)
        fid=result.json()["id"]
        self.assertEqual(self.client.patch(f"/api/factories/{fid}/enabled?enabled=false",
                                           headers=self.headers).status_code,200)
        rows=self.client.get("/api/factories",headers=self.headers).json()["factories"]
        self.assertEqual(next(f for f in rows if f["id"]==fid)["status"],"paused")
        invalid={**payload,"containers":[[12,64,32],[12,64,32]]}
        self.assertEqual(self.client.post("/api/factories",headers=self.headers,json=invalid).status_code,422)


if __name__=="__main__":
    unittest.main()
