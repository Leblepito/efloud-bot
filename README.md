# 🏛️ Efloud SMC & u2algo Ecosystem

![u2algo Premium Banner](docs/images/u2algo_premium_banner.png)

> **Efloud SMC Trade Bot v2.1** represents a state-of-the-art, institutional-grade algoritmik trade infrastructure designed for **Binance USDT-M Futures** paired with the **u2algo** public web and automated social marketing engine. 

---

## 🌐 Ecosystem Architecture

The ecosystem merges automated algorithmic execution, high-fidelity chart visualization, serverless web hosting, and AI-driven compliance content pipelines:

```mermaid
graph TD
    %% Core Trading Engine
    subgraph Core ["🤖 EFLOUD PYTHON ENGINE (v2.1)"]
        A[main.py / Daemon] --> B[SafeOrchestrator]
        B --> C[SymbolUniverse]
        B --> D[SMCEngine & Signals]
        B --> E[PositionLifecycle]
        B --> F[Safety Layer / CircuitBreaker]
        E --> G[OrderManager]
        G --> H[Binance CCXT Client]
    end

    %% Web / Frontend Layer
    subgraph Web ["🌐 WEB & OPERATOR DASHBOARD"]
        I[FastAPI Backend :8080] <--> J[Next.js 15 Operator Dashboard]
        K[u2algo-site landing page] -->|Railway Deploy| L[Supabase DB / waitlist]
        K -.->|DB Offline Fallback| M[Local JSONL Backup]
    end

    %% High Fidelity Charts
    subgraph Pine ["📊 TRADINGVIEW & PINE SCRIPT v6"]
        N[Desktop MCP Bridge] --> O[Pine Smart Compiler]
        P[Trade-Horizon Profiles] -->|Monotonic Verification| Q[Chart Visuals & Signals]
        Q -->|Signal Viz Retention| R[Leak-free Drawing Engine]
        Q -->|Wrong Timeframe Warning| S[Visual Alert Tables]
    end

    %% Social and AI
    subgraph Social ["📣 MANUS SOCIAL CONTENT PIPELINE"]
        T[Event Fired / Signal] --> U[Manus MCP Connectors]
        U --> V[Compliance & Risk Scan]
        V -->|Strict DYOR Gate| W[Draft Captions / Media]
        W -->|Manual Approval| X[Multi-Platform Publish]
    end

    %% Connections
    H <-->|Execution & Reconcile| N
    B <-->|Daemon Parity| I
    T <==|Signal Stream| B
```

---

## 🌟 Key Features & Innovations

### 1. Trade-Horizon Profiles (Faz 3.7) 📊
A complete timeframe management overhaul featuring predefined profiles with **fail-fast monotonic guards** to prevent misconfigured executions across Entry, Medium, and High Timeframes:
* **Scalp Profile**: 5m Entry · 1h MTF · 12h HTF
* **Mid Profile**: 15m Entry · 1h MTF · 4h HTF (Inert default, zero regression)
* **Long Profile**: 1h Entry · 8h MTF · 1w HTF (Mapped to `"W"` on TradingView to prevent compile errors)
* **Validation Guard**: In-place mutation rules enforce `Entry < MTF < HTF` before launch. Auto-caps HTF weekly kline requests to `250` limits to protect performance.

### 2. High-Fidelity TradingView Integration 📈
Connected via a secure **Desktop MCP Bridge** allowing real-time pine compiles:
* **Dynamic Visualization Dropdowns**: Scalp/Mid/Long/Custom dropdown parameters in Pine script directly control the multi-timeframe feeds.
* **Fidelity Protection**: Active Order Block boxes dynamically refresh without graphic leaks, and past visual drawings automatically scale/cleanup by chart TF.
* **Visual Safety Banners**: Embedded warning tables (`⚠️ YANLIŞ ZAMAN DİLİMİ`) draw prominent warnings on active charts when the current timeframe mismatch is detected.

### 3. Bulletproof Live Ops Safety & Circuit Breakers 🛡️
* **Idempotent Reconcile-to-Breaker Sync**: Resolves manual/exchange-side exits and automatically registers them into `CircuitBreaker` daily/consecutive-loss counters, preventing double-counting while preserving execution safety.
* **Orphan Position Protection**: Automatic discovery and SL coverage (`place_missing_sl`) for untracked open positions.
* **SL Repair Precision Rounding**: Matches lot sizes against exchange decimal precision to avoid stepSize order rejections.
* **Pause New Entries**: Emergency halt (`pause_new_entries: true` or `EFLOUD_PAUSE_NEW_ENTRIES=true`) blocks new positions while gracefully managing existing SL/TPs.

### 4. u2algo Landing Site & Local Backup Fallbacks 💻
A premium public-facing marketing and waitlist portal deployed on **Railway**:
* **Tech Stack**: Next.js 15, PostCSS, Supabase DB.
* **Fail-Safe local-jsonl Fallback**: In the event of a Supabase connection outage or rate limits, the waitlist form automatically saves leads into a local `jsonl` file and completes requests with a clean `200 OK` response to prevent public 500 errors.

---

## 📂 Repository Directory Map

| Path | Responsibility | Area |
| :--- | :--- | :--- |
| **`main.py`** | Bot CLI startup, configuration loading, and primary loop | Core Engine |
| **`engine/safe_orchestrator.py`** | Core engine loop manager, state management, and safety wiring | Core Engine |
| **`engine/lifecycle.py`** | Multi-target TP/SL, Break-Even, and weakness exit management | Core Engine |
| **`engine/safety/`** | Circuit Breaker, Position Guards, and Mainnet protection rules | Core Engine |
| **`exchange/`** | CCXT Binance integration, order managers, and reconcile loop | Exchange |
| **`data/timeframes.py`** | Scalp/Mid/Long profile math and monotonic timeframe resolvers | Data |
| **`pine/`** | Indicators and strategy source code in Pine Script v6 | TradingView |
| **`u2algo-site/`** | Web source code, database sql migrations, and Railway manifests | Web Page |
| **`u2algo-site/launch-assets/`** | SVG & PNG design visual assets generated for social launch | Social |
| **`docs/handoff/`** | System handoff plans, capability maps, and social launch packs | Handoffs |

---

## ⚡ Setup, Verification & Testing

### 1. Run Unit Tests (TDD Coverage)
Validate all timeframe profiles, precision models, and idempotent synchronization states:
```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python -m pytest backend/tests/test_timeframe_profiles.py -v
.venv\Scripts\python -m pytest backend/tests/test_reconcile_breaker_sync.py -v
.venv\Scripts\python -m pytest backend/tests/test_sl_repair_precision.py -v
```

### 2. Verify Entire Test Suite
Ensure no regression exists across the 78+ core tests:
```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python -m pytest
.venv\Scripts\python test_safety.py
```

### 3. Verify Landing Page Build
Validate server, syntax, and asset pipelines:
```bash
cd u2algo-site
npm install
npm run smoke
node --check server.js
node --check scripts/generate-launch-assets.js
```

---

## 🏁 Verification & Compliance Gate

All social posts, landing metrics, and automation plans are subjected to a strict local **Compliance Gate**:
* **Strict Disclosures**: Public communication must clearly declare that u2algo is a research-oriented analytics infrastructure, not financial advice.
* **DYOR (Do Your Own Risk) Policy**: Mandatory disclaimer headers on all public captions.
* **Forbidden Hits Check**: Automatic rejection of absolute performance/ROI promises, fund collection, or trade guarantees.

---

## ⚠️ Live Ops Guardrails (MANDATORY)

> [!CAUTION]
> **Production is live.** The core engine executes live accounts (`dry_run: false`) on Binance.

1. **Production Configuration**: Never edit `config.yaml`, `.env`, or `docker-compose.prod.yml` without explicit human confirmation.
2. **Docker Environment Updates**: Remember that `docker restart` or `docker compose restart` does **not** pick up environment file modifications. You must recreate containers:
   ```bash
   docker compose -f docker-compose.prod.yml up -d efloud-bot
   ```
3. **Database Migrations**: Run migrations manually in production:
   ```bash
   docker exec efloud-bot python3 -m backend.migrate up
   ```

---

## 🏛️ AI & Operator Workflow Splits

* **Hermes / Operator**: Manages live configurations, executes VPS/SSH deployment tasks, performs DNS modifications, audits dual-side position modes, and signs off final social publication triggers.
* **Antigravity (Orchestrator Agent)**: Autonomously performs test-driven development, builds specs, implements precise logic fixes, manages local repository history, compiles Pine scripts via TV Desktop MCP bridge, and drafts handoff briefs.

---

## 📝 Recent Releases & Commits
* **`feat(u2algo)`** (Commit `4562e03`) — Added local JSONL waitlist database fallback, built premium social launch assets, and drafted the final social approval pack.
* **`feat(u2algo)`** (Commit `e25f922`) — Integrated u2algo landing site, sitemap/robot maps, and Hermes onboarding matrices.
* **`feat(timeframes)`** (Commit `984a7dc`) — Implemented Scalp/Mid/Long Trade-Horizon Profiles, monotonic safety constraints, and TV warning tables.
* **`feat(pine)`** (Commit `af02683`) — Applied Pine V1 fidelity fixes and target-inversion protection.
