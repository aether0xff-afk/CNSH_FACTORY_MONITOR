"use strict";
const $ = id => document.getElementById(id);
const num = v => (v === null || v === undefined ? "—" : Number(v).toLocaleString("ko-KR"));
const sign = v => (v > 0 ? "+" : "") + num(v);
const time = s => s ? new Date(s).toLocaleString("ko-KR", {hour12:false,month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit"}) : "—";
const iconFor = item => item.includes("gunpowder") ? "G" : item.includes("iron") ? "Fe" : item.includes("sugar_cane") ? "S" : "◻";
const stateLabel = f => f.status === "paused" ? "수집 일시정지" : f.status === "error" ? "조회 오류" : f.status === "stale" ? "데이터 지연" : f.status === "waiting" ? "측정 대기" : f.stats_10m.in > 0 ? "유입 관측" : "조회 정상";
const pillType = f => f.status === "ok" ? "good" : f.status === "error" ? "bad" : "warn";
const esc = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
let factories = [], selectedId = null, hours = 1, historySeq = 0;

async function api(path, options = {}) {
  const response = await fetch(path, {cache:"no-store", ...options});
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { const data = await response.json(); detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail); } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function updateHeader() {
  $("total-factories").textContent = num(factories.length);
  $("live-factories").textContent = num(factories.filter(f => f.status === "ok").length);
  $("total-in").textContent = num(factories.reduce((s,f) => s + f.stats_10m.in, 0));
  $("total-out").textContent = num(factories.reduce((s,f) => s + f.stats_10m.out, 0));
  $("factory-count").textContent = num(factories.length);
  $("last-refresh").textContent = new Date().toLocaleTimeString("ko-KR", {hour12:false});
  $("server-indicator").className = "connection online";
  $("server-indicator").innerHTML = "<i></i> 서비스 연결됨";
}

function renderList() {
  const container = $("factory-list");
  container.replaceChildren();
  if (!factories.length) {container.innerHTML = '<div class="empty">공장을 등록해 주세요.</div>';return;}
  for (const f of factories) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "factory-card" + (f.id === selectedId ? " selected" : "");
    card.setAttribute("aria-pressed", String(f.id === selectedId));
    card.innerHTML = `<span class="factory-icon">${iconFor(f.item_id)}</span><span class="factory-meta"><b>${esc(f.name)}</b><small>${esc(f.item_id)}</small><span class="factory-card-bottom"><span class="pill ${pillType(f)}">${stateLabel(f)}</span><strong>${num(f.stock)}개</strong></span></span>`;
    card.addEventListener("click", () => {selectedId = f.id;renderList();renderDetail();loadHistory();});
    container.appendChild(card);
  }
}

function renderDetail() {
  const f = factories.find(f => f.id === selectedId);
  if (!f) return;
  $("factory-name").textContent = f.name;
  $("factory-item").textContent = f.item_id + " · " + f.dimension;
  $("status-tag").textContent = stateLabel(f);
  $("status-tag").className = "state-tag " + (f.status === "ok" ? "good" : f.status === "error" ? "bad" : "");
  $("factory-coords").textContent = "⌖ " + f.containers.map(c => c.join(", ")).join(" · ");
  $("factory-updated").textContent = "마지막 측정: " + time(f.last_checked);
  $("stock").textContent = num(f.stock);
  $("stock-capacity").textContent = "최대 " + num(f.capacity) + "개";
  $("net-10m").textContent = sign(f.stats_10m.net);
  $("net-sub").textContent = "유입 +" + num(f.stats_10m.in) + " · 유출 -" + num(f.stats_10m.out) + " · 관측 " + num(f.stats_10m.covered_seconds) + "초";
  $("rate-10m").textContent = f.stats_10m.net_per_second === null ? "—" : f.stats_10m.net_per_second.toFixed(3);
  const pct = f.stock === null ? 0 : Math.min(100, f.stock / f.capacity * 100);
  $("capacity-pct").textContent = f.stock === null ? "—" : pct.toFixed(1) + "%";
  $("capacity-fill").style.width = pct + "%";
  if (f.error) $("factory-updated").textContent += " · " + f.error;
}

const svgNS = "http://www.w3.org/2000/svg";
function svgEl(name, attrs = {}, textContent = "") {
  const e = document.createElementNS(svgNS, name);
  Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));
  if (textContent !== "")e.textContent = textContent;
  return e;
}
function drawChart(rows) {
  const svg = $("stock-chart"); svg.replaceChildren();
  const good = rows.filter(r => r.stock !== null && r.status === "ok");
  $("chart-empty").hidden = good.length !== 0;
  if (!good.length) return;
  const left=61,right=780,top=17,bottom=223;
  const gridColor = "#e7e9ef";
  const lineColor = "#78b39e";
  const vals = good.map(r=>r.stock), min=Math.min(...vals), max=Math.max(...vals);
  const pad = Math.max(5,(max-min)*.1), low=Math.max(0,min-pad), high=max+pad;
  const timestamps = rows.map(r=>new Date(r.ts).getTime());
  const first = timestamps[0], last = timestamps.at(-1), span = Math.max(last-first,1000);
  const x=t=>left+(t-first)/span*(right-left);
  const y=v=>bottom-(v-low)/(high-low)*(bottom-top);
  for(let i=0;i<5;i++){
    const yi=top+(bottom-top)*i/4;
    svg.appendChild(svgEl("line",{x1:left,y1:yi,x2:right,y2:yi,stroke:gridColor,"stroke-dasharray":"3 5"}));
    svg.appendChild(svgEl("text",{x:52,y:yi+4,fill:"#8792a0","font-size":"12","text-anchor":"end"},num(Math.round(high-(high-low)*i/4))));
  }
  for(let i=0;i<=4;i++){
    const ti=first+span*i/4;
    svg.appendChild(svgEl("text",{x:left+(right-left)*i/4,y:247,fill:"#8792a0","font-size":"11","text-anchor":i===0?"start":i===4?"end":"middle"},new Date(ti).toLocaleTimeString("ko-KR",{hour:"2-digit",minute:"2-digit",hour12:false})));
  }
  let d="", prevValid=false;
  for(let i=0;i<rows.length;i++){
    const r=rows[i],valid=r.stock !== null && r.status==="ok";
    if(valid){d+=(prevValid?"L":"M")+x(timestamps[i]).toFixed(2)+" "+y(r.stock).toFixed(2)+" ";}
    prevValid=valid;
  }
  svg.appendChild(svgEl("path",{d,fill:"none",stroke:lineColor,"stroke-width":"2.5","stroke-linecap":"round","stroke-linejoin":"round"}));
  const lastPoint=good.at(-1);
  svg.appendChild(svgEl("circle",{cx:x(new Date(lastPoint.ts).getTime()),cy:y(lastPoint.stock),r:4,fill:lineColor,stroke:"#ffffff","stroke-width":2}));
}

async function loadHistory() {
  const fid=selectedId, period=hours;
  if (!fid) return;
  const seq=++historySeq;
  try {
    const data = await api(`/api/factories/${encodeURIComponent(fid)}/history?hours=${period}`);
    if (seq!==historySeq || fid!==selectedId || period!==hours) return;
    drawChart(data.history);
    $("sample-count").textContent = `${num(data.total_samples)}개 측정 표본`;
    const tbody=$("events");tbody.replaceChildren();
    if (!data.events.length) tbody.innerHTML='<tr><td colspan="4" class="empty-cell">관측된 순변화가 없습니다.</td></tr>';
    for (const e of data.events) {
      const tr=document.createElement("tr"), up=e.delta>0;
      tr.innerHTML=`<td>${esc(time(e.ts))}</td><td>${up?"순유입":"순유출"}</td><td class="${up?"positive":"negative"}">${sign(e.delta)}개</td><td>${num(e.stock)}개</td>`;
      tbody.appendChild(tr);
    }
  } catch(e){$("chart-empty").hidden=false;$("chart-empty").textContent="이력 조회 오류: "+e.message;}
}

async function refresh() {
  try {
    const data=await api("/api/factories");
    factories=data.factories;
    if (!factories.some(f=>f.id===selectedId)) selectedId=factories[0]?.id||null;
    updateHeader();renderList();renderDetail();
    if (selectedId) loadHistory();
  } catch(e) {
    $("server-indicator").className="connection offline";
    $("server-indicator").innerHTML="<i></i> 서버 연결 오류";
    console.error(e);
  }
}

for (const button of document.querySelectorAll(".time-tabs button")) {
  button.addEventListener("click",()=>{
    hours=Number(button.dataset.hours);
    document.querySelectorAll(".time-tabs button").forEach(b=>b.classList.toggle("selected",b===button));
    loadHistory();
  });
}
const dialog=$("factory-dialog");
$("add-button").addEventListener("click",()=>dialog.showModal());
$("close-dialog").addEventListener("click",()=>dialog.close());
$("cancel-dialog").addEventListener("click",()=>dialog.close());
$("factory-form").addEventListener("submit",async e=>{
  e.preventDefault(); const form=e.currentTarget, fd=new FormData(form);
  $("form-error").textContent="";
  let containers;
  try {
    containers=String(fd.get("coordinates")).split(/\n+/).map(s=>s.trim()).filter(Boolean).map(s=>{
      const parts=s.split(/[\s,]+/).map(Number);
      if(parts.length!==3||parts.some(n=>!Number.isSafeInteger(n)))throw Error("좌표는 한 줄에 X Y Z 세 정수로 입력하세요.");
      return parts;
    });
    if(containers.length===0)throw Error("상자 좌표가 필요합니다.");
    const created=await api("/api/factories",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      name:fd.get("name"),item_id:fd.get("item_id"),dimension:fd.get("dimension"),containers,
      slots_per_container:Number(fd.get("slots_per_container")),stack_size:Number(fd.get("stack_size"))})});
    selectedId=created.id;dialog.close();form.reset();await refresh();
  }catch(err){$("form-error").textContent=err.message;}
});
refresh();setInterval(refresh,10000);