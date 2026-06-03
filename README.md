<p align="center">
  <img src="docs/assets/banner.svg" alt="Efloud Bot" width="100%"/>
</p>

<p align="center">
  <img src="https://github.com/Leblepito/efloud-bot/actions/workflows/ci.yml/badge.svg" alt="CI"/>
  <img src="https://img.shields.io/badge/python-3.11-blue.svg" alt="Python 3.11"/>
  <img src="https://img.shields.io/badge/exchange-Binance%20USDT--M%20Futures-f0b90b.svg" alt="Binance"/>
  <img src="https://img.shields.io/badge/strategy-Smart%20Money%20Concepts-6366f1.svg" alt="SMC"/>
  <img src="https://img.shields.io/badge/tests-1261%20passing-2ea44f.svg" alt="Tests"/>
  <img src="https://img.shields.io/badge/license-Proprietary-lightgrey.svg" alt="License"/>
</p>

<p align="center"><b>Institutional-grade Smart Money Concepts trading bot for Binance USDT-M Futures — with a deterministic, multi-layer safety engine and a fail-safe LLM advisory team.</b></p>

---

## ✨ Overview

**Efloud Bot** is an automated futures trading system built around **Smart Money Concepts (SMC)** — Break of Structure (BoS), Change of Character (CHoCH), Order Blocks (OB), Fair Value Gaps (FVG) and Optimal Trade Entry (OTE) — across a multi-timeframe chain (4h bias → 1h confirmation → 15m entry).

What sets it apart is **not** the signals; it is the **discipline around them**:

- A **deterministic 7-layer safety engine** (circuit breaker, position guards, orphan protection, reverse-on-profit guard, entry-drift guard, flat-book preflight, margin isolation) that gates every order.
- An **exchange-truth reconciliation** layer — realized PnL is read from Binance income (`realizedPnl − commission − funding`), never trusted from local estimates.
- A **fail-safe multi-agent LLM layer** that *advises* but never overrides the deterministic guards. No API key → the bot runs unchanged.

> ⚠️ **Risk disclaimer.** This software trades real money on leveraged derivatives. Futures trading can lead to **total loss of capital**. Nothing here is financial advice. Run on testnet first; use at your own risk.

---

## 🏗 Architecture

```mermaid
flowchart TD
    subgraph Data["Market Data"]
        EX["Binance USDT-M\n(CCXT)"]
    end
    subgraph Core["Deterministic Core"]
        ORCH["SafeOrchestrator\n(run_cycle)"]
        SMC["SMC Engine\nBoS / CHoCH / OB / FVG / OTE"]
        SIG["Signal + Confluence\nscoring"]
        RISK["Risk / Sizing"]
        SAFE["Safety Stack\nbreaker · guards · orphan"]
        OM["OrderManager\n+ SL/TP verify"]
    end
    subgraph Advisory["LLM Advisory (fail-safe, shadow)"]
        AT["Agent Team\nSignal · Risk · Regime · Overseer"]
    end
    subgraph Surface["Surface"]
        API["FastAPI\n/healthz · /api/*"]
        DB["PostgreSQL\n+ JSONL journal"]
    end
    EX --> ORCH --> SMC --> SIG --> AT
    SIG --> RISK --> SAFE --> OM --> EX
    AT -. advisory verdict .-> SIG
    OM --> DB
    API --> ORCH
    API --> DB
```

The agent team sits **beside** the pipeline as an advisor. The trade decision always flows through the deterministic `can_trade` gate and the safety stack — the LLM layer can be disabled at any time with zero behavioural change.

---

## 🔁 Trade Lifecycle

```mermaid
sequenceDiagram
    participant C as Cycle
    participant E as SMC Engine
    participant A as Agent Team
    participant G as Safety Gate
    participant X as Binance
    C->>E: HTF bias → MTF confirm → 15m entry
    E->>E: confluence score ≥ threshold? R:R ≥ min?
    E->>A: STEP 3.5 — advisory review (shadow)
    A-->>E: verdict (logged, non-blocking by default)
    E->>G: can_trade? (breaker / regime / stale / guards)
    G->>X: open position + SL + TP
    X-->>G: fills
    G->>X: verify SL/TP landed (re-query + repair)
    Note over G,X: SL unconfirmable → market-close (never hold bare)
    X-->>C: realized PnL (exchange-truth reconcile)
```

---

## 🛡 The Safety Stack

| Layer | What it does |
|---|---|
| **Circuit Breaker** | Daily / weekly loss limits + consecutive-loss pause → HALT |
| **Position Guards** | Per-trade notional cap, total exposure cap, SL-distance bounds, max holding, pyramid cap |
| **Orphan Protection** | Detects exchange positions unknown to local state; can place protective SL |
| **Reverse-on-Profit Guard** | Blocks flip into an opposite signal unless current position is in profit beyond a fee/slippage buffer |
| **Entry-Drift Guard** | Rejects entries where live price has drifted past the signal anchor (or already passed TP1) |
| **SL/TP Post-Placement Verify** | Re-queries after entry; repairs missing legs; market-closes if SL can't be confirmed |
| **Margin Isolation + One-Way** | ISOLATED margin + one-way mode enforced at startup; flat-book preflight `[5/5]` gate before any mode change |

Every layer **fails safe**: the worst outcome of a misconfiguration is an *aborted startup* (no trading), never an unguarded live position.

---

## 🤖 Agent System

Two independent layers, both **additive and fail-safe**:

```mermaid
flowchart LR
    subgraph RT["Runtime Advisory Team (Gemini, shadow)"]
        SV["Signal-Validator"]
        RR["Risk-Reviewer"]
        RG["Regime"]
        OV["Overseer"]
        PM["Post-Mortem"]
    end
    subgraph DEV["Dev-time Maintenance + Quant Team (.claude/agents)"]
        SMCR["smc-strategy-reviewer"]
        RSA["risk-safety-auditor"]
        QSA["quant-strategy-analyst"]
        FMO["fund-manager-overseer"]
        MME["market-microstructure-expert"]
        LOS["live-ops-sentinel"]
    end
    SV & RR & RG --> OV --> PM
```

- **Runtime team** (`engine/agents/`) reviews every signal in **shadow mode** (`gating: false`). Verdicts are logged to `state/agent_disagreements.jsonl` and surfaced at `GET /api/ai/agents`. With no `GEMINI_API_KEY`, every agent returns `NEUTRAL` and the bot is unaffected.
- **Dev-time team** (`.claude/agents/`) is a panel of specialists for code maintenance **and** trading expertise — from SMC review and risk auditing to a fund-manager-grade portfolio overseer and a live-ops sentinel. All are **advisory**; none can weaken the deterministic guards or flip gating.

---

## 🧰 Tech Stack

`Python 3.11` · `CCXT` · `pandas` / `numpy` · `FastAPI` + `uvicorn` · `asyncpg` (PostgreSQL) · `pytest` (1261 tests) · `anthropic` / Gemini (advisory) · Docker / Railway · GitHub Actions CI.

---

## 🚀 Quick Start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure (testnet first!)
cp .env.example .env          # set BINANCE_API_KEY / SECRET
# edit config.yaml: testnet: true, dry_run: true

# 3. Run
python main.py                # CLI (reads config.yaml)

# 4. Dashboard / API
uvicorn backend.api:app --reload   # /healthz, /api/*
```

> **Going live** requires `EFLOUD_ALLOW_MAINNET=1` and a passing pre-flight:
> `EFLOUD_ALLOW_MAINNET=1 EFLOUD_CONFIG_PATH=configs/config.phase2_1k.yaml python preflight.py` → `[5/5]` must pass on a **flat book**.

---

## ⚙️ Configuration

- `config.yaml` — CLI default profile.
- `configs/config.phase2_1k.yaml` — **production-active** profile (FastAPI/Railway reads this via `EFLOUD_CONFIG_PATH`).
- Key blocks: `exchange` (margin/leverage/mode), `risk`, `safety` (the stack above), `agent_team` (advisory LLM; `gating: false` by default).

---

## ✅ Testing & CI

```bash
python -m pytest -q              # full suite (1261 passed)
```

GitHub Actions runs the whole suite on every PR (Python 3.11, hermetic — no secrets, agent layer falls back to NEUTRAL). CI is a hard gate: claims of “tests pass” are re-verified on the actual pushed commit.

---

## 📦 Deployment

Containerised (`Dockerfile`) and deployed on **Railway** (`/healthz` healthcheck, restart-on-failure). Live margin/mode changes follow a **flat-book maintenance-window runbook** (stop → flatten → deploy → preflight `[5/5]` → start → confirm).

---

## 🗂 Project Structure

```
engine/            SMC core, orchestrator, safety/, risk/, regimes/, agents/
exchange/          CCXT client + OrderManager (entry, SL/TP, reconcile, PnL)
backend/           FastAPI app, bot_runner, db, tests/
preflight.py       mainnet readiness + flat-book gate
config.yaml        default profile   · configs/   production profiles
.claude/agents/    dev-time maintenance + quant agent team
.github/workflows/ CI
```

---

## 🗺 Roadmap

- 2-pass risk review (post-sizing notional) · gating arbitration (score / majority) · shadow-data correlation report
- CI hermeticity (mock live-exchange tests) · expanded backtest analytics
- Quant agent team: portfolio-level allocation + correlation-aware sizing

---

## 💛 Sponsorship

Efloud Bot is privately developed. Sponsorship / collaboration enquiries are welcome — please open a discussion or contact the maintainer. _(Public GitHub Sponsors can be enabled later; this repository is currently private.)_

---

## 📄 License

Proprietary — all rights reserved. Not for redistribution. **Trading involves substantial risk of loss.**
