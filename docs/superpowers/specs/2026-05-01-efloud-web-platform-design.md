# Efloud Web Platform Design

**Tarih:** 2026-05-01
**Branch:** `feature/web-platform`
**Backup:** `backup-local-v2.1`

## Bağlam

Efloud Python SMC bot'u tek başına çalışan terminal uygulaması. Bunu web dashboard + cloud deploy ile sarmalıyoruz. Multi-tenant değil — tek kullanıcı (Utku) için.

## Kararlar (brainstorm + onay)

| Karar | Değer |
|---|---|
| Kullanıcı modeli | Tek kullanıcı (Utku) |
| Lifecycle | 24/7 + frontend kill switch |
| Cycle interval | **30sn (SMC için doğru, değişmez)** |
| TP/SL execution | **Server-side Binance order (0ms)** ← refactor |
| Position reconciliation | **Her cycle Binance ↔ local sync** ← yeni |
| Frontend live update | **WebSocket push (0ms)** |
| Auth | Tek password (env var, HTTP-only cookie) |
| Frontend stack | Next.js 15 + Tailwind + Recharts + WebSocket client |
| Backend stack | FastAPI + uvicorn + asyncio bot worker |
| Database | Supabase PostgreSQL (free tier) |
| Frontend host | Vercel (free hobby) |
| Backend host | Railway ($5-10/ay) |

## Mimari

```
┌─────────────────────────────────────┐
│  Vercel — Next.js frontend          │
│  - / (dashboard)                    │
│  - /login (password)                │
│  - WebSocket client → Railway       │
└──────────────┬──────────────────────┘
               │ HTTPS REST + WSS
               ▼
┌─────────────────────────────────────┐
│  Railway — FastAPI gateway          │
│  - /api/status, /api/positions      │
│  - /api/history, /api/equity        │
│  - /api/kill-switch (POST)          │
│  - /ws (WebSocket)                  │
│                                      │
│  Bot worker (asyncio task)          │
│  - SafeOrchestrator + OrderManager  │
│  - Binance ccxt async               │
│  - Server-side TP/SL orders         │
│  - Reconciliation per cycle         │
│  - Push events to WS                │
└──────────────┬──────────────────────┘
               │ asyncpg
               ▼
┌─────────────────────────────────────┐
│  Supabase Postgres                  │
│  - trades (id, symbol, dir, entry,  │
│    exit, pnl, opened_at, closed_at) │
│  - equity_history (ts, balance)     │
│  - breaker_state (singleton)        │
│  - audit_log (ts, event, payload)   │
└─────────────────────────────────────┘
               │
               ▼
       Binance Futures (mainnet)
```

## Backend (Railway)

### Klasör yapısı (mevcut + yeni)
```
efloud-bot/
├── main.py                   # ARTIK CLI WORKER ENTRY POINT (kalır)
├── engine/                   # mevcut (dokunulmaz, sadece OrderManager refactor)
├── exchange/__init__.py      # OrderManager: server-side TP/SL refactor
├── backend/                  # YENİ
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── api.py                # REST endpoints
│   ├── ws.py                 # WebSocket manager
│   ├── auth.py               # password middleware
│   ├── db.py                 # Supabase asyncpg client
│   ├── bot_runner.py         # Bot lifecycle: asyncio task wrapper
│   └── events.py             # Bot → WS event bus
├── supabase/                 # YENİ
│   └── migrations/
│       └── 001_initial.sql
├── railway.toml              # YENİ
└── Procfile                  # YENİ — Railway: web + worker
```

### Procfile
```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
worker: python -m backend.bot_runner
```

Railway'de iki process: `web` (FastAPI) + `worker` (bot). Aynı container, paylaşan asyncpg connection pool. Daha basit alternatif: tek process içinde FastAPI + asyncio task — bunu seçeceğiz, aşağıda.

### Tek-process model (basit alternatif)
```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

`backend/main.py` startup event'inde bot worker'ı asyncio task olarak başlatır. Avantaj: tek dyno (Railway'de daha ucuz), shared memory (event bus için kolay).

### REST API endpoints
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/login` | `{password}` | Set-Cookie: session |
| GET | `/api/status` | - | `{bot_running, breaker_state, last_cycle, cycle_count}` |
| GET | `/api/positions` | - | `[{symbol, dir, entry, sl, tp1, tp2, size, current_price, pnl_pct}]` |
| GET | `/api/history?limit=50` | - | `[{symbol, dir, entry, exit, pnl, opened_at, closed_at, reason}]` |
| GET | `/api/equity?days=7` | - | `[{ts, balance}]` |
| POST | `/api/kill-switch` | - | `{ok: true}` (breaker → HALTED, bot durur) |
| GET | `/api/config` | - | `{config_path, leverage, symbols, risk}` |

### WebSocket events (server → client)
- `cycle_start` `{cycle_n, ts}`
- `cycle_end` `{cycle_n, duration_ms, signals_found}`
- `position_opened` `{symbol, dir, entry, size, sl, tp1, tp2}`
- `position_closed` `{symbol, dir, entry, exit, pnl, reason}`
- `breaker_change` `{old_state, new_state, reason}`
- `error` `{message, traceback?}`

## OrderManager refactor (server-side TP/SL)

### Şu an
```python
def open_position(...):
    market_order = create_order(symbol, "market", side, size)
    sl_order = create_order(symbol, "STOP", reverse_side, size, sl, reduceOnly=True)
    # TP1, TP2 → polling-based (30sn lag)
```

### Yeni
```python
async def open_position(...):
    market_order = await client.create_order(symbol, "market", side, size)

    # Server-side SL (mevcut)
    sl_order = await client.create_order(
        symbol, "STOP_MARKET", reverse_side, size,
        params={"stopPrice": sl, "reduceOnly": True}
    )

    # Server-side TP1 (yeni — yarısını kapatır, break-even SL trigger eder)
    tp1_order = await client.create_order(
        symbol, "TAKE_PROFIT_MARKET", reverse_side, size / 2,
        params={"stopPrice": tp1, "reduceOnly": True}
    )

    # Server-side TP2 (yeni — kalan yarıyı kapatır)
    tp2_order = await client.create_order(
        symbol, "TAKE_PROFIT_MARKET", reverse_side, size / 2,
        params={"stopPrice": tp2, "reduceOnly": True}
    )

    return Position(..., sl_order_id=sl_order.id, tp1_order_id=tp1_order.id, tp2_order_id=tp2_order.id)
```

### Reconciliation (yeni — her cycle başı)
```python
async def reconcile():
    """Binance ile local state sync."""
    binance_positions = await client.fetch_positions()
    binance_orders = await client.fetch_open_orders()

    for local_pos in self.positions[:]:
        bn_match = next((p for p in binance_positions if p.symbol == local_pos.symbol), None)
        if not bn_match or float(bn_match["contracts"]) == 0:
            # Pozisyon Binance'de kapanmış (TP/SL hit veya manual close)
            log.info(f"Reconciled close: {local_pos.symbol}")
            self.positions.remove(local_pos)
            await db.record_trade_close(local_pos, reason="reconciled")
            await events.emit("position_closed", ...)
        else:
            # Pozisyon hâlâ açık — TP1 hit oldu mu kontrol et
            if local_pos.tp1_order_id and not local_pos.tp1_hit:
                tp1_status = next((o for o in binance_orders if o.id == local_pos.tp1_order_id), None)
                if tp1_status is None:  # Order kaybolmuş = filled
                    local_pos.tp1_hit = True
                    # Move SL to entry (break-even)
                    await client.cancel_order(local_pos.sl_order_id)
                    new_sl = await client.create_order(symbol, "STOP_MARKET", ..., stopPrice=local_pos.entry)
                    local_pos.sl_order_id = new_sl.id
```

## Frontend (Vercel — Next.js + frontend-design skill)

### Sayfalar
- `/login` — tek password input + submit
- `/` (dashboard, password korumalı)

### Dashboard layout
```
┌─────────────────────────────────────────────────┐
│ EFLOUD BOT                       [KILL SWITCH]  │
├─────────────────────────────────────────────────┤
│ ┌──────────────┐  ┌──────────────────────────┐ │
│ │ STATUS       │  │ EQUITY (7 days)          │ │
│ │ • Running    │  │  ┌─────────────┐          │ │
│ │ • Breaker:OK │  │  │  /\___      │          │ │
│ │ • Cycle #428 │  │  │ /     \____ │          │ │
│ │ • Last: 10s  │  │  └─────────────┘          │ │
│ └──────────────┘  └──────────────────────────┘ │
│                                                  │
│ OPEN POSITIONS (3)                              │
│ ┌──┬───────┬─────┬───────┬──────┬──────┬─────┐│
│ │  │Symbol │Dir  │Entry  │SL    │TP1   │PnL  ││
│ │1 │BTCUSDT│LONG │95000  │94500 │95800 │+1.2%││
│ │2 │ETHUSDT│SHORT│2400   │2440  │2360  │-0.3%││
│ └──┴───────┴─────┴───────┴──────┴──────┴─────┘│
│                                                  │
│ HISTORY (last 24h)                              │
│ ...                                              │
│                                                  │
│ CONFIG (read-only) [Show]                       │
└─────────────────────────────────────────────────┘
```

### Frontend stack
- Next.js 15 (App Router)
- TailwindCSS
- Recharts (equity grafiği)
- WebSocket client (native `WebSocket` API)
- shadcn/ui components

`frontend-design` skill ile production-grade aesthetic — generic AI dashboard görünümünden kaçın.

## Database schema (Supabase)

```sql
-- supabase/migrations/001_initial.sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry NUMERIC NOT NULL,
    exit NUMERIC,
    sl NUMERIC NOT NULL,
    tp1 NUMERIC NOT NULL,
    tp2 NUMERIC NOT NULL,
    size NUMERIC NOT NULL,
    pnl_usdt NUMERIC,
    pnl_pct NUMERIC,
    reason TEXT,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    confluence INT,
    binance_order_id TEXT
);

CREATE INDEX idx_trades_opened_at ON trades(opened_at DESC);
CREATE INDEX idx_trades_symbol ON trades(symbol);

CREATE TABLE equity_history (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    balance NUMERIC NOT NULL,
    open_positions_count INT NOT NULL DEFAULT 0
);

CREATE INDEX idx_equity_ts ON equity_history(ts DESC);

CREATE TABLE breaker_state (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- singleton
    state TEXT NOT NULL,
    reason TEXT,
    consecutive_losses INT NOT NULL DEFAULT 0,
    current_balance NUMERIC NOT NULL,
    peak_balance NUMERIC NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event TEXT NOT NULL,
    payload JSONB
);

CREATE INDEX idx_audit_ts ON audit_log(ts DESC);
```

## Environment variables (Railway backend)

```bash
# Mevcut (bot için)
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
EFLOUD_ALLOW_MAINNET=1

# YENİ (web platform için)
DASHBOARD_PASSWORD=...           # tek kullanıcı password
SESSION_SECRET=...                # cookie signing (random 32+ char)
DATABASE_URL=postgres://...       # Supabase pooler URL
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=...          # database write permissions
ALLOWED_ORIGINS=https://efloud-bot.vercel.app
EFLOUD_CONFIG_PATH=configs/config.phase2_micro.yaml
```

Frontend (Vercel) sadece public bilgiyi alır:
```bash
NEXT_PUBLIC_API_URL=https://efloud-bot.up.railway.app
```

## Güvenlik katmanları (mevcut korunur + yeni eklenir)

| Katman | Mevcut | Web platform |
|---|---|---|
| MainnetGuard | ✓ | ✓ (CLI mode'da `interactive=False` ile worker'da) |
| validate_config | ✓ (cherry-pick) | ✓ |
| CircuitBreaker | ✓ | ✓ + Supabase'de persist |
| PositionGuard | ✓ | ✓ |
| Server-side TP/SL | ❌ | **✓ YENİ** |
| Position reconciliation | ❌ | **✓ YENİ** |
| Kill switch | Ctrl+C | **✓ Frontend butonu (breaker → HALTED)** |
| Withdraw permission | ❌ (key tarafı) | (kullanıcı sorumluluğu, README'de hatırlatma) |
| HTTPS | - | ✓ (Vercel + Railway default) |
| Password rate limiting | - | ✓ (5 deneme/dk → 15 dk lock) |

## Test stratejisi

```bash
# 1. Mevcut testler regresyonsuz kalmalı
python test_safety.py        # 8/8
python test_v2_2_0.py        # 4/4
python test_regime.py        # 3/3
python -m pytest tests/      # 28/28

# 2. YENİ — backend unit testleri
python -m pytest backend/tests/ -v

# 3. YENİ — OrderManager refactor testleri (server-side TP/SL)
python -m pytest backend/tests/test_order_manager_v2.py -v

# 4. YENİ — E2E testnet smoke
# Testnet config + dry_run=False ile
python -m backend.main &
SERVER_PID=$!
sleep 5
curl http://localhost:8000/api/status   # should return bot_running
kill $SERVER_PID

# 5. Frontend build
cd frontend && npm run build && npm run typecheck
```

## Deployment akışı

1. **Supabase project create** (MCP) → DATABASE_URL, SERVICE_KEY
2. **Migrations run** → 001_initial.sql
3. **Railway project create** → backend deploy (Procfile)
4. **Railway env vars** → kullanıcı manuel girer (BINANCE_*, DASHBOARD_PASSWORD, DATABASE_URL)
5. **Vercel project create** (MCP) → frontend deploy (linked GitHub branch)
6. **Vercel env vars** → NEXT_PUBLIC_API_URL
7. **Backend health check** → https://xxx.up.railway.app/api/status
8. **Frontend health check** → https://xxx.vercel.app
9. **End-to-end smoke** → testnet'te bot 1 cycle, frontend cycle event görüyor

## Rollback

| Durum | Aksiyon |
|---|---|
| Frontend buggy | Vercel rollback to previous deployment |
| Backend buggy | Railway rollback / `git revert` + redeploy |
| Bot trade hatası | Frontend kill switch → breaker HALTED, sonra `git checkout backup-local-v2.1` |
| Database corruption | Supabase point-in-time restore (PITR) |

## Başarı kriteri

- [ ] Backend Railway'de live, /api/status 200 döner
- [ ] Frontend Vercel'de live, /login + dashboard çalışıyor
- [ ] Supabase'de trades + equity tabloları populated (testnet cycle ile)
- [ ] Server-side TP1/TP2 order'ları Binance testnet'te oluşturulup hit oluyor
- [ ] Reconciliation: manuel kapatma → bot 30sn içinde fark ediyor
- [ ] WebSocket: bot cycle event'i frontend'e <500ms'de ulaşıyor
- [ ] Kill switch: butona basınca breaker HALTED, bot durur
- [ ] Mevcut 28+8+4+3 = 43 testin hiçbirinde regresyon yok

---

*Auto mode altında brainstorming → spec → uygulama. writing-plans atlanır; spec direkt task listesine dönüştürülür.*
