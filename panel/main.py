"""efloud birlesik cok-bot izleme paneli (Faz 1, 2026-07-24).

3 bot instance'inin (V1 mid / V2 long / V3 scalp) mevcut dashboard API'lerini
server-side aggregate eder; bot koduna SIFIR dokunus. Ozellikler:
  - Tek ekranda 3 botun durum/breaker/pozisyon/PnL gorunumu
  - Birlesik kumulatif-PnL grafigi (3 seri, /api/equity'den)
  - Operasyonel butonlar: Start / Stop / Breaker Reset (bot API proxy'si)
  - HTTP Basic auth (DASHBOARD_PASSWORD; Caddy TLS arkasinda)

Guvenlik notlari:
  - Bot cookie'si Secure flag'li oldugundan (auth.py:81) http:// ic agda
    cookie-jar replay CALISMAZ — Set-Cookie elle alinip Cookie header'i
    olarak tasinir (2026-07-24 breaker-reset incident'inde kanitlanan yol).
  - /api/positions her cagrida Binance'e gider -> panel 15s server-side
    cache tutar ki panel polling'i Binance weight butcesini yemesin
    (2026-07-24: weight %102 CRITICAL goruldu; panel bunu AGIRLASTIRMAMALI).
"""
import asyncio
import base64
import os
import secrets
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

BOTS = {
    "v1": {"name": "V1 · Mid (15m)", "base": os.environ.get("PANEL_V1_URL", "http://efloud-bot:8080")},
    "v2": {"name": "V2 · Long (1h)", "base": os.environ.get("PANEL_V2_URL", "http://efloud-bot-long:8080")},
    "v3": {"name": "V3 · Scalp (5m)", "base": os.environ.get("PANEL_V3_URL", "http://efloud-bot-scalp:8080")},
}
PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
OVERVIEW_CACHE_SEC = float(os.environ.get("PANEL_CACHE_SEC", "15"))
EQUITY_DAYS = int(os.environ.get("PANEL_EQUITY_DAYS", "30"))

app = FastAPI(title="efloud panel", docs_url=None, redoc_url=None, openapi_url=None)

_sessions: dict = {}          # bot_id -> "efloud_session=..." cookie
_overview_cache: dict = {"ts": 0.0, "data": None}
_cache_lock = asyncio.Lock()


def _check_basic_auth(request: Request) -> None:
    """HTTP Basic: sifre DASHBOARD_PASSWORD, kullanici adi serbest."""
    if not PASSWORD:
        raise HTTPException(503, "DASHBOARD_PASSWORD env eksik — panel devre disi")
    hdr = request.headers.get("authorization", "")
    ok = False
    if hdr.startswith("Basic "):
        try:
            raw = base64.b64decode(hdr[6:]).decode("utf-8", "replace")
            _, _, pw = raw.partition(":")
            ok = secrets.compare_digest(pw, PASSWORD)
        except Exception:
            ok = False
    if not ok:
        raise HTTPException(401, "auth", headers={"WWW-Authenticate": 'Basic realm="efloud-panel"'})


async def _login(client: httpx.AsyncClient, bot_id: str) -> str:
    base = BOTS[bot_id]["base"]
    r = await client.post(f"{base}/api/login", json={"password": PASSWORD})
    r.raise_for_status()
    cookie = (r.headers.get("set-cookie") or "").split(";")[0]
    if not cookie.startswith("efloud_session="):
        raise RuntimeError(f"{bot_id}: login cookie gelmedi")
    _sessions[bot_id] = cookie
    return cookie


async def _bot_req(client: httpx.AsyncClient, bot_id: str, method: str, path: str):
    """Bot API cagrisi; 401'de bir kez re-login (cookie suresi/restart)."""
    base = BOTS[bot_id]["base"]
    cookie = _sessions.get(bot_id) or await _login(client, bot_id)
    for attempt in (1, 2):
        r = await client.request(method, f"{base}{path}", headers={"Cookie": cookie},
                                 json={} if method == "POST" else None)
        if r.status_code == 401 and attempt == 1:
            cookie = await _login(client, bot_id)
            continue
        r.raise_for_status()
        return r.json()


async def _bot_overview(client: httpx.AsyncClient, bot_id: str) -> dict:
    """Tek botun status+positions+equity paketi; her hata izole edilir."""
    out: dict = {"id": bot_id, "name": BOTS[bot_id]["name"]}
    try:
        out["status"] = await _bot_req(client, bot_id, "GET", "/api/status")
    except Exception as e:
        out["error"] = f"status: {e}"
        return out
    try:
        out["positions"] = await _bot_req(client, bot_id, "GET", "/api/positions")
    except Exception as e:
        out["positions"], out["positions_error"] = [], str(e)
    try:
        out["equity"] = await _bot_req(client, bot_id, "GET", f"/api/equity?days={EQUITY_DAYS}")
    except Exception as e:
        out["equity"], out["equity_error"] = [], str(e)
    try:
        out["history"] = await _bot_req(client, bot_id, "GET", "/api/history?limit=10")
    except Exception as e:
        out["history"] = []
    return out


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/api/overview")
async def overview(request: Request) -> JSONResponse:
    _check_basic_auth(request)
    async with _cache_lock:
        now = time.time()
        if _overview_cache["data"] is not None and now - _overview_cache["ts"] < OVERVIEW_CACHE_SEC:
            return JSONResponse(_overview_cache["data"])
        async with httpx.AsyncClient(timeout=15.0) as client:
            results = await asyncio.gather(*[_bot_overview(client, b) for b in BOTS])
        data = {"generated_at": time.time(), "bots": {r["id"]: r for r in results}}
        _overview_cache.update(ts=now, data=data)
        return JSONResponse(data)


_ACTIONS = {
    "start": ("POST", "/api/bot/start"),
    "stop": ("POST", "/api/bot/stop"),
    "breaker-reset": ("POST", "/api/breaker/reset"),
}


@app.post("/api/bot/{bot_id}/{action}")
async def bot_action(bot_id: str, action: str, request: Request) -> JSONResponse:
    _check_basic_auth(request)
    if bot_id not in BOTS or action not in _ACTIONS:
        raise HTTPException(404, "bilinmeyen bot/aksiyon")
    method, path = _ACTIONS[action]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            result = await _bot_req(client, bot_id, method, path)
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:300]
        except Exception:
            pass
        raise HTTPException(502, f"{bot_id} {action}: HTTP {e.response.status_code} {detail}")
    except Exception as e:
        raise HTTPException(502, f"{bot_id} {action}: {e}")
    _overview_cache["ts"] = 0.0   # aksiyondan sonra taze veri
    return JSONResponse({"ok": True, "bot": bot_id, "action": action, "result": result})


@app.get("/")
async def index(request: Request) -> HTMLResponse:
    _check_basic_auth(request)
    return HTMLResponse(PAGE)


PAGE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>efloud · birleşik panel</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<style>
  :root { --bg:#0d1117; --card:#161b22; --line:#30363d; --txt:#e6edf3; --dim:#8b949e;
          --green:#3fb950; --red:#f85149; --amber:#d29922; --blue:#58a6ff; }
  * { box-sizing:border-box; margin:0; }
  body { background:var(--bg); color:var(--txt); font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; padding:16px; }
  h1 { font-size:18px; margin-bottom:4px; }
  .sub { color:var(--dim); font-size:12px; margin-bottom:16px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px; margin-bottom:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; }
  .card h2 { font-size:15px; display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  .badge { font-size:11px; padding:2px 8px; border-radius:10px; font-weight:600; }
  .b-run { background:#0d2818; color:var(--green); }
  .b-stop { background:#2d1517; color:var(--red); }
  .b-halt { background:#2d2308; color:var(--amber); }
  .kv { color:var(--dim); font-size:12px; margin:2px 0; }
  .kv b { color:var(--txt); font-weight:600; }
  table { width:100%; border-collapse:collapse; font-size:12px; margin-top:8px; }
  th { text-align:left; color:var(--dim); font-weight:500; border-bottom:1px solid var(--line); padding:3px 6px; }
  td { padding:3px 6px; border-bottom:1px solid #21262d; }
  .pnl-pos { color:var(--green); } .pnl-neg { color:var(--red); }
  .btns { display:flex; gap:6px; margin-top:10px; }
  button { background:#21262d; color:var(--txt); border:1px solid var(--line); border-radius:6px;
           padding:5px 10px; font-size:12px; cursor:pointer; }
  button:hover { border-color:var(--blue); }
  button.danger:hover { border-color:var(--red); color:var(--red); }
  .chartbox { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; margin-bottom:16px; }
  .err { color:var(--red); font-size:12px; }
  #msg { position:fixed; bottom:14px; right:14px; background:#21262d; border:1px solid var(--line);
         border-radius:8px; padding:10px 14px; font-size:13px; display:none; max-width:420px; }
</style>
</head>
<body>
<h1>efloud · birleşik panel</h1>
<div class="sub" id="updated">yükleniyor…</div>
<div class="grid" id="cards"></div>
<div class="chartbox">
  <h2 style="font-size:15px;margin-bottom:8px">Kümülatif PnL (USDT, son 30 gün)</h2>
  <canvas id="chart" height="90"></canvas>
</div>
<div class="chartbox">
  <h2 style="font-size:15px;margin-bottom:8px">Son işlemler</h2>
  <div id="trades"></div>
</div>
<div id="msg"></div>
<script>
const COLORS = { v1:"#58a6ff", v2:"#bc8cff", v3:"#39c5cf" };
let chart = null;

function fmt(n, d=2) { const x = Number(n); return isFinite(x) ? x.toFixed(d) : "—"; }
function toast(t, isErr) {
  const m = document.getElementById("msg");
  m.textContent = t; m.style.display = "block";
  m.style.borderColor = isErr ? "var(--red)" : "var(--green)";
  setTimeout(() => m.style.display = "none", 6000);
}

async function act(bot, action) {
  const labels = { start:"START", stop:"STOP", "breaker-reset":"BREAKER RESET" };
  if (!confirm(bot.toUpperCase() + " için " + labels[action] + " — emin misin?")) return;
  try {
    const r = await fetch(`/api/bot/${bot}/${action}`, { method:"POST" });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.status);
    toast(bot.toUpperCase() + " " + labels[action] + " ✓ " + JSON.stringify(j.result).slice(0,120), false);
    setTimeout(refresh, 1200);
  } catch (e) { toast(bot.toUpperCase() + " " + action + " HATA: " + e.message, true); }
}

function badge(st) {
  if (!st) return `<span class="badge b-stop">ERİŞİLEMİYOR</span>`;
  const br = st.breaker_state || "?";
  if (br === "HALTED") return `<span class="badge b-halt">HALTED</span>`;
  return st.running ? `<span class="badge b-run">ÇALIŞIYOR · ${br}</span>`
                    : `<span class="badge b-stop">DURDU · ${br}</span>`;
}

function posTable(ps) {
  if (!ps || !ps.length) return `<div class="kv">açık pozisyon yok</div>`;
  const rows = ps.map(p => {
    const pnl = Number(p.unrealizedPnl ?? p.unrealized_pnl ?? p.pnl ?? NaN);
    const cls = pnl >= 0 ? "pnl-pos" : "pnl-neg";
    return `<tr><td>${p.symbol || "?"}</td><td>${p.side || p.direction || ""}</td>` +
           `<td>${fmt(p.contracts ?? p.size ?? p.positionAmt, 4)}</td>` +
           `<td>${fmt(p.entryPrice ?? p.entry_price, 4)}</td>` +
           `<td class="${cls}">${isFinite(pnl) ? fmt(pnl) : "—"}</td></tr>`;
  }).join("");
  return `<table><tr><th>Sembol</th><th>Yön</th><th>Boyut</th><th>Giriş</th><th>uPnL</th></tr>${rows}</table>`;
}

function card(b) {
  const st = b.status;
  let inner = "";
  if (b.error) inner = `<div class="err">${b.error}</div>`;
  else {
    inner = `<div class="kv">cycle: <b>${st.cycle_count ?? "—"}</b> · son: <b>${(st.last_cycle_at||"—").slice(11,19)}</b>` +
            `${st.dry_run ? ' · <b style="color:var(--amber)">DRY-RUN</b>' : ""}</div>` +
            (st.last_error ? `<div class="err">son hata: ${String(st.last_error).slice(0,90)}</div>` : "") +
            posTable(b.positions) +
            `<div class="btns">` +
            `<button onclick="act('${b.id}','start')">Start</button>` +
            `<button class="danger" onclick="act('${b.id}','stop')">Stop</button>` +
            `<button class="danger" onclick="act('${b.id}','breaker-reset')">Breaker Reset</button></div>`;
  }
  return `<div class="card"><h2><span style="color:${COLORS[b.id]}">${b.name}</span>${badge(st)}</h2>${inner}</div>`;
}

function renderChart(bots) {
  const ds = [];
  for (const id of Object.keys(bots)) {
    const eq = bots[id].equity || [];
    if (!eq.length) continue;
    ds.push({ label: bots[id].name, borderColor: COLORS[id], backgroundColor: COLORS[id],
              pointRadius: 0, borderWidth: 2, tension: 0.15,
              data: eq.filter(p => p.t).map(p => ({ x: new Date(p.t).getTime(), y: Number(p.equity) })) });
  }
  const cfg = { type:"line", data:{ datasets: ds },
    options:{ animation:false, responsive:true,
      interaction:{ mode:"nearest", intersect:false },
      scales:{ x:{ type:"linear", ticks:{ color:"#8b949e", maxTicksLimit:8,
                     callback:v => new Date(v).toLocaleDateString("tr-TR",{day:"2-digit",month:"2-digit"}) },
                   grid:{ color:"#21262d" } },
               y:{ ticks:{ color:"#8b949e" }, grid:{ color:"#21262d" } } },
      plugins:{ legend:{ labels:{ color:"#e6edf3" } },
                tooltip:{ callbacks:{ title: items => new Date(items[0].parsed.x).toLocaleString("tr-TR") } } } } };
  if (chart) { chart.data = cfg.data; chart.update(); } else chart = new Chart(document.getElementById("chart"), cfg);
}

function renderTrades(bots) {
  const all = [];
  for (const id of Object.keys(bots))
    for (const t of (bots[id].history || []))
      all.push({ bot:id, ...t });
  all.sort((a,b) => String(b.exit_timestamp||b.timestamp||"").localeCompare(String(a.exit_timestamp||a.timestamp||"")));
  const rows = all.slice(0,20).map(t => {
    const pnl = Number(t.realized_pnl ?? t.pnl ?? NaN);
    const cls = pnl >= 0 ? "pnl-pos" : "pnl-neg";
    return `<tr><td style="color:${COLORS[t.bot]}">${t.bot.toUpperCase()}</td>` +
           `<td>${t.symbol||"?"}</td><td>${t.direction||t.side||""}</td>` +
           `<td>${String(t.exit_timestamp||t.timestamp||"").slice(0,16).replace("T"," ")}</td>` +
           `<td class="${cls}">${isFinite(pnl) ? fmt(pnl) : "—"}</td></tr>`;
  }).join("");
  document.getElementById("trades").innerHTML = all.length
    ? `<table><tr><th>Bot</th><th>Sembol</th><th>Yön</th><th>Çıkış</th><th>PnL</th></tr>${rows}</table>`
    : `<div class="kv">işlem yok</div>`;
}

async function refresh() {
  try {
    const r = await fetch("/api/overview");
    if (!r.ok) throw new Error("overview " + r.status);
    const j = await r.json();
    const bots = j.bots;
    document.getElementById("cards").innerHTML = ["v1","v2","v3"].map(id => card(bots[id])).join("");
    renderChart(bots); renderTrades(bots);
    document.getElementById("updated").textContent =
      "güncelleme: " + new Date().toLocaleTimeString("tr-TR") + " · veriler ~15s önbellekli · Faz 1 (izleme + operasyon)";
  } catch (e) {
    document.getElementById("updated").innerHTML = `<span class="err">bağlantı hatası: ${e.message}</span>`;
  }
}
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""
