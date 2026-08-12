"""efloud birlesik cok-bot izleme paneli (Faz 2, 2026-08-12).

3 bot instance'inin (V1 mid / V2 long / V3 scalp) mevcut dashboard API'lerini
server-side aggregate eder; bot koduna SIFIR dokunus. Ozellikler:
  - Tek ekranda 3 botun durum/breaker/pozisyon/PnL gorunumu + toplam ozet seridi
  - Birlesik kumulatif-PnL grafigi (3 seri, /api/equity'den)
  - Operasyonel butonlar: Start / Stop / Restart / Breaker Reset (bot API proxy'si)
  - HTTP Basic auth (DASHBOARD_PASSWORD; istege bagli DASHBOARD_USERNAME;
    Caddy TLS arkasinda). Env'ler HER istekte okunur -> rotate-credentials.sh
    sonrasi panel restart'siz yeni sifreyi kabul eder.

Guvenlik notlari:
  - Bot cookie'si Secure flag'li oldugundan (auth.py:81) http:// ic agda
    cookie-jar replay CALISMAZ — Set-Cookie elle alinip Cookie header'i
    olarak tasinir (2026-07-24 breaker-reset incident'inde kanitlanan yol).
  - /api/positions her cagrida Binance'e gider -> panel 15s server-side
    cache tutar ki panel polling'i Binance weight butcesini yemesin
    (2026-07-24: weight %102 CRITICAL goruldu; panel bunu AGIRLASTIRMAMALI).
  - PAGE inline-JS innerHTML ile render eder; bot API'sinden gelen HER serbest
    metin (last_error, error, sembol...) esc()'ten gecer (XSS, 2026-08-12).
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
OVERVIEW_CACHE_SEC = float(os.environ.get("PANEL_CACHE_SEC", "15"))
EQUITY_DAYS = int(os.environ.get("PANEL_EQUITY_DAYS", "30"))

app = FastAPI(title="efloud panel", docs_url=None, redoc_url=None, openapi_url=None)

_sessions: dict = {}          # bot_id -> "efloud_session=..." cookie
_overview_cache: dict = {"ts": 0.0, "data": None}
_cache_lock = asyncio.Lock()


def _get_password() -> str:
    """Call-time okunur: rotate-credentials.sh env'i degistirip konteyneri
    yeniden olusturur ama testler/rotasyon icin import-time cache'i yanlisti."""
    return os.environ.get("DASHBOARD_PASSWORD", "")


def _get_username() -> str:
    """Bos = kullanici adi zorunlu degil (geriye uyumlu)."""
    return os.environ.get("DASHBOARD_USERNAME", "")


def _check_basic_auth(request: Request) -> None:
    """HTTP Basic: sifre DASHBOARD_PASSWORD; DASHBOARD_USERNAME set ise
    kullanici adi da eslesmek zorunda (ikisi de constant-time)."""
    password = _get_password()
    if not password:
        raise HTTPException(503, "DASHBOARD_PASSWORD env eksik — panel devre disi")
    expected_user = _get_username()
    hdr = request.headers.get("authorization", "")
    ok = False
    if hdr.startswith("Basic "):
        try:
            raw = base64.b64decode(hdr[6:]).decode("utf-8", "replace")
            user, _, pw = raw.partition(":")
            ok = secrets.compare_digest(pw, password)
            if expected_user:
                # tek '&' bilincli: kisa devre yok -> timing farki yok
                ok = ok & secrets.compare_digest(user, expected_user)
        except Exception:
            ok = False
    if not ok:
        raise HTTPException(401, "auth", headers={"WWW-Authenticate": 'Basic realm="efloud-panel"'})


async def _login(client: httpx.AsyncClient, bot_id: str) -> str:
    base = BOTS[bot_id]["base"]
    r = await client.post(f"{base}/api/login", json={"password": _get_password()})
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
    except Exception:
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
    "restart": ("POST", "/api/bot/restart"),
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
  .sub { color:var(--dim); font-size:12px; margin-bottom:12px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .sub button { padding:2px 8px; font-size:11px; }
  .totals { display:flex; gap:18px; flex-wrap:wrap; background:var(--card); border:1px solid var(--line);
            border-radius:8px; padding:10px 14px; margin-bottom:14px; font-size:13px; }
  .totals .t-item b { display:block; font-size:16px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px; margin-bottom:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; }
  .card h2 { font-size:15px; display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; gap:6px; flex-wrap:wrap; }
  .badge { font-size:11px; padding:2px 8px; border-radius:10px; font-weight:600; }
  .b-run { background:#0d2818; color:var(--green); }
  .b-stop { background:#2d1517; color:var(--red); }
  .b-halt { background:#2d2308; color:var(--amber); }
  .b-test { background:#1c2d41; color:var(--blue); }
  .kv { color:var(--dim); font-size:12px; margin:2px 0; }
  .kv b { color:var(--txt); font-weight:600; }
  b.pnl-pos, .kv b.pnl-pos, .totals b.pnl-pos { color:var(--green); }
  b.pnl-neg, .kv b.pnl-neg, .totals b.pnl-neg { color:var(--red); }
  table { width:100%; border-collapse:collapse; font-size:12px; margin-top:8px; }
  th { text-align:left; color:var(--dim); font-weight:500; border-bottom:1px solid var(--line); padding:3px 6px; }
  td { padding:3px 6px; border-bottom:1px solid #21262d; }
  .pnl-pos { color:var(--green); } .pnl-neg { color:var(--red); }
  .btns { display:flex; gap:6px; margin-top:10px; flex-wrap:wrap; }
  button { background:#21262d; color:var(--txt); border:1px solid var(--line); border-radius:6px;
           padding:5px 10px; font-size:12px; cursor:pointer; }
  button:hover { border-color:var(--blue); }
  button.danger:hover { border-color:var(--red); color:var(--red); }
  .chartbox { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; margin-bottom:16px; }
  .err { color:var(--red); font-size:12px; overflow-wrap:anywhere; }
  #msg { position:fixed; bottom:14px; right:14px; background:#21262d; border:1px solid var(--line);
         border-radius:8px; padding:10px 14px; font-size:13px; display:none; max-width:420px; }
</style>
</head>
<body>
<h1>efloud · birleşik panel</h1>
<div class="sub">
  <span id="updated">yükleniyor…</span>
  <span id="countdown"></span>
  <button onclick="refresh(true)">⟳ Yenile</button>
</div>
<div class="totals" id="totals" style="display:none"></div>
<div class="grid" id="cards"></div>
<div class="chartbox">
  <h2 style="font-size:15px;margin-bottom:8px">Kümülatif PnL (USDT, son 30 gün)</h2>
  <canvas id="chart" height="90"></canvas>
  <div class="kv" id="chart-fallback" style="display:none">grafik kütüphanesi yüklenemedi (CDN erişimi yok) — veriler karttaki değerlerden izlenebilir</div>
</div>
<div class="chartbox">
  <h2 style="font-size:15px;margin-bottom:8px">Son işlemler</h2>
  <div id="trades"></div>
</div>
<div id="msg"></div>
<script>
const COLORS = { v1:"#58a6ff", v2:"#bc8cff", v3:"#39c5cf" };
const REFRESH_SEC = 15;
let chart = null, nextRefresh = Date.now() + REFRESH_SEC*1000;

// Bot API'sinden gelen HER serbest metin buradan geçer (XSS guard).
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
}
function fmt(n, d=2) { const x = Number(n); return isFinite(x) ? x.toFixed(d) : "—"; }
function pnlCls(v) { return v >= 0 ? "pnl-pos" : "pnl-neg"; }
function toast(t, isErr) {
  const m = document.getElementById("msg");
  m.textContent = t; m.style.display = "block";
  m.style.borderColor = isErr ? "var(--red)" : "var(--green)";
  setTimeout(() => m.style.display = "none", 6000);
}

async function act(bot, action) {
  const labels = { start:"START", stop:"STOP", restart:"RESTART", "breaker-reset":"BREAKER RESET" };
  if (!confirm(bot.toUpperCase() + " için " + labels[action] + " — emin misin?")) return;
  try {
    const r = await fetch(`/api/bot/${bot}/${action}`, { method:"POST" });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.status);
    toast(bot.toUpperCase() + " " + labels[action] + " ✓ " + JSON.stringify(j.result).slice(0,120), false);
    setTimeout(() => refresh(true), 1200);
  } catch (e) { toast(bot.toUpperCase() + " " + action + " HATA: " + e.message, true); }
}

function badge(st) {
  if (!st) return `<span class="badge b-stop">ERİŞİLEMİYOR</span>`;
  const br = esc(st.breaker_state || "?");
  let out = "";
  if (br === "HALTED") out = `<span class="badge b-halt">HALTED</span>`;
  else out = st.running ? `<span class="badge b-run">ÇALIŞIYOR · ${br}</span>`
                        : `<span class="badge b-stop">DURDU · ${br}</span>`;
  if (st.testnet) out += ` <span class="badge b-test">TESTNET</span>`;
  if (st.dry_run) out += ` <span class="badge b-halt">DRY-RUN</span>`;
  return out;
}

function upnlSum(ps) {
  let s = 0, any = false;
  for (const p of ps || []) {
    const v = Number(p.unrealizedPnl ?? p.unrealized_pnl ?? p.pnl ?? NaN);
    if (isFinite(v)) { s += v; any = true; }
  }
  return any ? s : null;
}
function lastEquity(eq) {
  if (!eq || !eq.length) return null;
  const v = Number(eq[eq.length-1].equity);
  return isFinite(v) ? v : null;
}

function posTable(ps) {
  if (!ps || !ps.length) return `<div class="kv">açık pozisyon yok</div>`;
  const rows = ps.map(p => {
    const pnl = Number(p.unrealizedPnl ?? p.unrealized_pnl ?? p.pnl ?? NaN);
    return `<tr><td>${esc(p.symbol || "?")}</td><td>${esc(p.side || p.direction || "")}</td>` +
           `<td>${fmt(p.contracts ?? p.size ?? p.positionAmt, 4)}</td>` +
           `<td>${fmt(p.entryPrice ?? p.entry_price, 4)}</td>` +
           `<td class="${pnlCls(pnl)}">${isFinite(pnl) ? fmt(pnl) : "—"}</td></tr>`;
  }).join("");
  return `<table><tr><th>Sembol</th><th>Yön</th><th>Boyut</th><th>Giriş</th><th>uPnL</th></tr>${rows}</table>`;
}

function card(b) {
  const st = b.status;
  let inner = "";
  if (b.error) inner = `<div class="err">${esc(b.error)}</div>`;
  else {
    const up = upnlSum(b.positions), cum = lastEquity(b.equity);
    inner = `<div class="kv">cycle: <b>${st.cycle_count ?? "—"}</b>` +
            ` · son: <b>${esc(String(st.last_cycle_at || "—")).slice(11,19)}</b>` +
            (st.last_cycle_duration_ms != null ? ` · süre: <b>${fmt(st.last_cycle_duration_ms,0)}ms</b>` : "") +
            `</div>` +
            `<div class="kv">açık poz: <b>${(b.positions||[]).length}</b>` +
            (up != null ? ` · uPnL: <b class="${pnlCls(up)}">${fmt(up)}</b>` : "") +
            (cum != null ? ` · kümülatif: <b class="${pnlCls(cum)}">${fmt(cum)}</b>` : "") +
            `</div>` +
            (st.last_error ? `<div class="err">son hata: ${esc(String(st.last_error)).slice(0,90)}</div>` : "") +
            (b.positions_error ? `<div class="err">pozisyonlar alınamadı: ${esc(String(b.positions_error)).slice(0,90)}</div>` : "") +
            posTable(b.positions) +
            `<div class="btns">` +
            `<button onclick="act('${b.id}','start')">Start</button>` +
            `<button class="danger" onclick="act('${b.id}','stop')">Stop</button>` +
            `<button onclick="act('${b.id}','restart')">Restart</button>` +
            `<button class="danger" onclick="act('${b.id}','breaker-reset')">Breaker Reset</button></div>`;
  }
  return `<div class="card"><h2><span style="color:${COLORS[b.id]}">${esc(b.name)}</span><span>${badge(st)}</span></h2>${inner}</div>`;
}

function renderTotals(bots) {
  let up = 0, cum = 0, pos = 0, running = 0, total = 0, halted = 0;
  for (const id of Object.keys(bots)) {
    const b = bots[id]; total++;
    if (b.status && b.status.running) running++;
    if (b.status && b.status.breaker_state === "HALTED") halted++;
    const u = upnlSum(b.positions); if (u != null) up += u;
    const c = lastEquity(b.equity); if (c != null) cum += c;
    pos += (b.positions || []).length;
  }
  const el = document.getElementById("totals");
  el.style.display = "flex";
  el.innerHTML =
    `<div class="t-item">çalışan bot <b>${running}/${total}${halted ? ` <span class="badge b-halt">${halted} HALTED</span>` : ""}</b></div>` +
    `<div class="t-item">açık pozisyon <b>${pos}</b></div>` +
    `<div class="t-item">toplam uPnL <b class="${pnlCls(up)}">${fmt(up)} USDT</b></div>` +
    `<div class="t-item">toplam kümülatif PnL <b class="${pnlCls(cum)}">${fmt(cum)} USDT</b></div>`;
}

function renderChart(bots) {
  if (typeof Chart === "undefined") {
    document.getElementById("chart-fallback").style.display = "block";
    document.getElementById("chart").style.display = "none";
    return;
  }
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
    return `<tr><td style="color:${COLORS[t.bot]}">${esc(t.bot.toUpperCase())}</td>` +
           `<td>${esc(t.symbol || "?")}</td><td>${esc(t.direction || t.side || "")}</td>` +
           `<td>${esc(String(t.exit_timestamp||t.timestamp||"")).slice(0,16).replace("T"," ")}</td>` +
           `<td class="${pnlCls(pnl)}">${isFinite(pnl) ? fmt(pnl) : "—"}</td></tr>`;
  }).join("");
  document.getElementById("trades").innerHTML = all.length
    ? `<table><tr><th>Bot</th><th>Sembol</th><th>Yön</th><th>Çıkış</th><th>PnL</th></tr>${rows}</table>`
    : `<div class="kv">işlem yok</div>`;
}

async function refresh(manual) {
  nextRefresh = Date.now() + REFRESH_SEC*1000;
  try {
    const r = await fetch("/api/overview");
    if (!r.ok) throw new Error("overview " + r.status);
    const j = await r.json();
    const bots = j.bots;
    document.getElementById("cards").innerHTML = ["v1","v2","v3"].map(id => card(bots[id])).join("");
    renderTotals(bots); renderChart(bots); renderTrades(bots);
    document.getElementById("updated").textContent =
      "güncelleme: " + new Date().toLocaleTimeString("tr-TR") + " · veriler ~15s önbellekli";
  } catch (e) {
    document.getElementById("updated").innerHTML = `<span class="err">bağlantı hatası: ${esc(e.message)}</span>`;
  }
}
setInterval(() => {
  const s = Math.max(0, Math.round((nextRefresh - Date.now())/1000));
  document.getElementById("countdown").textContent = "sonraki yenileme: " + s + "s";
}, 1000);
refresh();
setInterval(refresh, REFRESH_SEC*1000);
</script>
</body>
</html>"""
