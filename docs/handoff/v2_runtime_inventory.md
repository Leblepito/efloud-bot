# Efloud-bot v2 — Runtime Dosya Envanteri

> SMC v2 bot'unun **canlıda çalışması için gerekli olan tüm dosyalar**, eskimiş/silinebilir olanlar ve env/Supabase/Hetzner bağlantıları.
> Tarih: 2026-05-24 | Master HEAD: `c88f23a` | Repo: https://github.com/Leblepito/efloud-bot

---

## 🚨 ÖNCE BUNU OKU — Güvenlik Alarmı

`.env` dosyasında (local, gitignore'da ama diskte plaintext) **gerçek canlı API key'ler** var:
- `BINANCE_API_KEY` + `BINANCE_API_SECRET` (mainnet, fon erişimi olan)
- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `KIMI_API_KEY`, `MINIMAX_API_KEY`, `OLLAMA_API_KEY`, `MANUS_API_KEY`

**Aksiyon (öncelikli)**:
1. Binance → API Management → bu key'i **disable + delete** → yeni key oluştur → IP whitelist'e sadece Hetzner VPS IP (`<VPS_IP>`)
2. Anthropic console → key revoke + yeni key
3. Diğer 6 LLM provider → aynı işlem
4. Yeni key'leri **sadece** VPS'teki `.env.production`'a yaz, local `.env`'i sil veya placeholder yap

`.env` git'e commit edilmemiş ama paylaşılan log/snapshot'larda görünmüş olabilir → rotate **zorunlu**.

---

## 1. Production Runtime için ZORUNLU Dosyalar

> Bot Hetzner VPS'te (`/opt/efloud-bot`, repo clone) bu dosyalarla ayakta. `docker compose up -d` bu set'i kullanır.

### 1a. Root — Build & Orchestration

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `Dockerfile` | `Dockerfile` | Multi-stage build: Next.js frontend export + Python backend |
| `docker-compose.prod.yml` | `docker-compose.prod.yml` | 6 servis: efloud-bot, caddy, autoheal, alerter, daily-report (profile), overseer + 2 overseer-scheduled |
| `requirements.txt` | `requirements.txt` | Python deps (ccxt, fastapi, asyncpg, anthropic vb.) |
| `.dockerignore` | `.dockerignore` | Build context filtering |
| `config.yaml` | `config.yaml` | **Ana config** — SMC v2 engine flag + risk + safety bloğu |
| `pyproject.toml` | `pyproject.toml` | Python project metadata |
| `main.py` | `main.py` | Bot CLI entrypoint + `_build_setup_state_store` (v2 wiring) |

### 1b. Backend (FastAPI + dashboard + DB)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `backend/main.py` | `backend/main.py` | FastAPI app, CORS, session, lifespan'de bot_runner spawn |
| `backend/api.py` | `backend/api.py` | REST endpoint'leri (status, positions, orders, history, bot/start, bot/stop) |
| `backend/auth.py` | `backend/auth.py` | Session-based dashboard login (DASHBOARD_PASSWORD) |
| `backend/bot_runner.py` | `backend/bot_runner.py` | SafeOrchestrator'ı async worker olarak çalıştırır |
| `backend/db.py` | `backend/db.py` | asyncpg pool, trade telemetry insert/query |
| `backend/events.py` | `backend/events.py` | In-process event bus (frontend WS broadcast) |
| `backend/healthz.py` | `backend/healthz.py` | `/healthz` (autoheal + Caddy + alerter probe target) |
| `backend/migrate.py` | `backend/migrate.py` | DB migration runner (`python -m backend.migrate up`) |
| `backend/ws.py` | `backend/ws.py` | WebSocket endpoint (live position/order/trade stream) |
| `backend/audit/{__init__,journal,klines,scorer}.py` | `backend/audit/` | Trade audit log + scoring |
| `backend/notifications/__init__.py` | `backend/notifications/__init__.py` | Telegram notifier (None-safe tp2 dahil) |
| `backend/migrations/001..008_*.sql` | `backend/migrations/` | 8 migration. **007 = SMC v2 telemetry**, **008 = tp2 nullable** |

### 1c. Engine (SMC core + safety + v2 modülleri)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `engine/__init__.py` | `engine/__init__.py` | (legacy SafeOrchestrator re-export) |
| `engine/safe_orchestrator.py` | `engine/safe_orchestrator.py` | **Ana orkestratör** — v1 + v2 dispatch, `_place_v2_entry_order`, shadow log |
| `engine/signals.py` | `engine/signals.py` | v1 signal generation |
| `engine/smc.py` | `engine/smc.py` | SMC indicators (FVG, OB, swings, EqHL) |
| `engine/lifecycle.py` | `engine/lifecycle.py` | Position dataclass + partial_close + single-target branch |
| `engine/confluence.py` | `engine/confluence.py` | Multi-TF confluence scoring |
| `engine/regimes/__init__.py` | `engine/regimes/__init__.py` | TRENDING/RANGING/VOLATILE detector |
| `engine/adaptive.py` | `engine/adaptive.py` | Adaptive risk sizing |
| `engine/intent.py` | `engine/intent.py` | Signal intent enrichment |
| `engine/journal.py` | `engine/journal.py` | Trade journal writer |
| `engine/levels.py` | `engine/levels.py` | S/R levels |
| `engine/memory.py` | `engine/memory.py` | Cross-run memory cache |
| `engine/postmortem.py` | `engine/postmortem.py` | Closed trade analysis |
| `engine/report.py` | `engine/report.py` | Run reports (None-safe tp2) |
| `engine/scenarios.py` | `engine/scenarios.py` | Scenario evaluation |
| `engine/universe.py` | `engine/universe.py` | Symbol universe (20 coin) |
| `engine/notifications/{__init__,null_manager}.py` | `engine/notifications/` | Engine-side notifier wrapper |
| `engine/permissions/__init__.py` | `engine/permissions/__init__.py` | Trading permissions matrix |
| `engine/risk/{__init__,custom_calculator}.py` | `engine/risk/` | Risk sizing |
| `engine/safety/__init__.py` | `engine/safety/__init__.py` | Safety layer entry |
| `engine/safety/breaker.py` | `engine/safety/breaker.py` | **Circuit breaker** (daily/weekly DD limit) |
| `engine/safety/position_guard.py` | `engine/safety/position_guard.py` | Pre-trade gating (size, exposure, anti-flip) |
| `engine/safety/guard.py` | `engine/safety/guard.py` | mainnet_guard + dry_run gate |
| `engine/safety/orphan_protection.py` | `engine/safety/orphan_protection.py` | Orphan position handling |
| `engine/safety/runtime_state.py` | `engine/safety/runtime_state.py` | Runtime state persistence |
| `engine/safety/state.py` | `engine/safety/state.py` | Safety state machine |
| **`engine/smc_v2/__init__.py`** | `engine/smc_v2/__init__.py` | **v2 modül paketi** |
| `engine/smc_v2/zones.py` | `engine/smc_v2/zones.py` | OTE + FVG zone calc |
| `engine/smc_v2/swing_anchor.py` | `engine/smc_v2/swing_anchor.py` | HTF swing anchor selection |
| `engine/smc_v2/triggers.py` | `engine/smc_v2/triggers.py` | Setup candidate emit |
| `engine/smc_v2/setup_state.py` | `engine/smc_v2/setup_state.py` | SetupStateStore (atomic persist) |
| `engine/smc_v2/confirmation.py` | `engine/smc_v2/confirmation.py` | LTF engulfing confirm |
| `engine/smc_v2/sl_calc.py` | `engine/smc_v2/sl_calc.py` | SL = swing + ATR buffer + clamp |
| `engine/smc_v2/tp_calc.py` | `engine/smc_v2/tp_calc.py` | TP1 = liquidity, TP2 = FVG fill (Optional) |
| `engine/smc_v2/exceptions.py` | `engine/smc_v2/exceptions.py` | v2 custom exceptions |

### 1d. Exchange (Binance CCXT köprüsü)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `exchange/__init__.py` | `exchange/__init__.py` | **BinanceClient + OrderManager + reconcile loop** (tp2 Optional, single-target sibling cleanup) |

### 1e. Ops (alerter + daily report + overseer sidecar)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `ops/__init__.py` | `ops/__init__.py` | (package marker) |
| `ops/alerter/{__init__,alerter,dedup,rules,telegram_client}.py` | `ops/alerter/` | Log tail → Telegram alert |
| `ops/daily_report/{__init__,aggregate,heartbeat,render,report,smtp_client}.py` | `ops/daily_report/` | Günlük performans raporu |
| `ops/overseer/{__init__,__main__,dedup,phase0_runner,rules,state,summarizer,watch}.py` | `ops/overseer/` | **24/7 observer sidecar** (rule engine + Haiku LLM summarizer) |
| `ops/overseer/ingestors/{healthz_poller,journal_tail,log_tail}.py` | `ops/overseer/ingestors/` | Veri kaynakları |
| `ops/overseer/sinks/{email,telegram}.py` | `ops/overseer/sinks/` | Alert hedefleri |

### 1f. Utils + risk + data

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `utils/{__init__,logging}.py` | `utils/` | Structured logging |
| `risk/__init__.py` | `risk/` | Legacy risk package (orchestrator hâlâ import edebilir) |
| `data/{__init__,cache,fetcher,manifest,timeframes}.py` | `data/` | OHLCV cache + Binance fetch (backtest + live warmup) |

### 1g. Deploy (Hetzner)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `deploy/Caddyfile` | `deploy/Caddyfile` | HTTPS reverse proxy → `bot.ualgotrade.com` + `<VPS-IP>.nip.io` |
| `deploy/HETZNER_GUIDE.md` | `deploy/HETZNER_GUIDE.md` | VPS kurulum kılavuzu |
| `deploy/deploy.sh` | `deploy/deploy.sh` | Pull + build + recreate + healthcheck script |
| `deploy/setup-server.sh` | `deploy/setup-server.sh` | İlk VPS provision script |
| `deploy/.env.production.example` | `deploy/.env.production.example` | **VPS env template** |

### 1h. Frontend (Next.js dashboard)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `frontend/package.json` + `package-lock.json` | `frontend/` | npm deps |
| `frontend/next.config.ts` | `frontend/next.config.ts` | Static export config |
| `frontend/tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs` | `frontend/` | Build config |
| `frontend/app/{layout,page,login/page,globals.css}.tsx` | `frontend/app/` | Pages |
| `frontend/components/*.tsx` (13 dosya) | `frontend/components/` | UI (PositionsTable, BotControl, EquityChart, KillSwitch vb.) |
| `frontend/hooks/use*.ts` (7 hook) | `frontend/hooks/` | Data fetching + WS |
| `frontend/lib/{api,format}.ts` | `frontend/lib/` | API client + helpers |
| `frontend/vercel.json` | `frontend/vercel.json` | (artifact, Hetzner build kullanmıyor) |

### 1i. Config dosyaları (aktif)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `config.yaml` | `config.yaml` | **Root config** (env > file precedence) |
| `configs/config.phase2_1k.yaml` | `configs/config.phase2_1k.yaml` | **Mainnet 1k profile** — `.env.production` `EFLOUD_CONFIG_PATH` bunu gösterir |

### 1j. Backtest (offline, prod runtime'da çağrılmaz ama gerekli)

| Local Path | GitHub Path | Ne Yapar |
|---|---|---|
| `backtest/{__init__,engine,cli,compare_live,comparison,funding,grid,intrabar,metrics,reproducibility,slippage}.py` | `backtest/` | Walk-forward sim + v1/v2 comparison harness |

### 1k. Dokümantasyon (runtime'da çağrılmaz, sen okuyorsun)

| Local Path | GitHub Path | Ne |
|---|---|---|
| `CLAUDE.md` | `CLAUDE.md` | Claude Code için proje memory + kurallar |
| `HERMES.md` | `HERMES.md` | **Senin runbook'un** (12 bölüm) |
| `README.md` | `README.md` | Proje overview |

---

## 2. Eskimiş / Silinebilir Dosyalar (v2 için gereksiz)

> Bu liste **silinecek** öneri — sadece commit-edilmiş eskimiş dosyalar. Worktree/cache/state gibi runtime artifactları ayrı bölümde.

### 2a. Root'taki eskimiş Python dosyaları (legacy testler)

| Dosya | Neden eskimiş |
|---|---|
| `test_backtest.py` | Eski standalone test, `backend/tests/` altına taşındı |
| `test_backtest_multi.py` | Aynı |
| `test_doge_diagnose.py` | One-off DOGE debug script (29 Nisan) |
| `test_offline.py` | Eski offline smoke |
| `test_real_backtest.py` | Eski |
| `test_real_data.py` | Eski |
| `test_regime.py` | Eski |
| `test_safety.py` | Eski (yeni: `backend/tests/test_breaker_*.py`) |
| `test_smoke.py` | Eski |
| `test_v2_2_0.py` | "v2.2.0" eski versiyon prototip — şu anki v2 ile alakasız |
| `superagentv3.py` | 66 KB tek-dosya proto, kullanılmıyor |
| `preflight.py` | Eski preflight script — yerini `scripts/pre_deployment_checklist.py` aldı |

### 2b. Railway artifactları (terk edildi — Hetzner'a geçildi)

| Dosya | Neden eskimiş |
|---|---|
| `railway.json` | Railway konfig — bot artık Hetzner'da, Railway hesabı kapatıldı |
| `railway.toml` | Aynı |

### 2c. Eskimiş dokümanlar

| Dosya | Neden eskimiş |
|---|---|
| `MAINNET_GECIS_REHBERI.md` | Nisan'da yazıldı, mainnet geçişi tamamlandı — referans değer kayboldu |
| `PR_BODY.md` | Belirli bir PR'ın gövdesi (commit'lendi unutuldu) |
| `RISK_MAP.md` | Nisan'da yazıldı, `HERMES.md` + `engine/safety/` güncel kaynak |

### 2d. Eski/alternatif config'ler

| Dosya | Neden eskimiş |
|---|---|
| `configs/archive/*.yaml` (6 dosya) | Zaten archive klasöründe |
| `configs/config.aggressive_v1.yaml` | "aggressive" profile — 2026-05 sonrasında kullanılmıyor |
| `configs/config.phase2_1k_h1c_conf80.yaml` | Tuning grid sonucu, tek-seferlik |
| `configs/config.phase2_1k_h2a2_risk2_notional6.yaml` | Aynı |
| `configs/config.testnet.yaml` | Testnet artık config_path env var ile aktive ediliyor |
| `configs/grids/confluence_x_notional.yaml` | Grid search artifact |

### 2e. Untracked / local-only artefactlar (commit edilmeli veya silinmeli)

| Yol | Ne | Aksiyon |
|---|---|---|
| `Efloud-bot/archive/` | Boş klasör (root'ta tuhaf konum) | **Sil** |
| `__write_test_2/` | Boş test klasörü | **Sil** |
| `__pycache__/` (root) | Python bytecode | **Sil** (gitignore'da ama disk'te) |
| `.pytest_cache/` | Test cache | **Sil** |
| `cache/` (root) | OHLCV parquet cache (~150 MB, gitignored) | **Sakla** — backtest için gerekli |
| `cache/ohlcv/` | Backtest OHLCV verileri | Sakla |
| ~~`data/` (root)~~ | **DÜZELTME**: Bu eski dump değil — `data/__init__.py + cache.py + fetcher.py + manifest.py + timeframes.py` = **production modülü** (Bölüm 1f). **SİLME.** | — |
| `logs/` | Local log dump | Periyodik temizle |
| `reports/` | Local rapor dump | Periyodik temizle |
| `state/`, `state_1k/` | Local state dumps | Sakla (gitignore'da, prod state ayrı) |
| `frontend/node_modules/` | **390 MB**, gitignored, npm deps | Disk dolarsa: `rm -rf` → `npm install` ile geri gelir |
| `frontend/.next/` | **133 MB**, gitignored, Next.js dev cache | `rm -rf` ile sil — Dockerfile build kullanmaz |
| `frontend/out/` | 1.5 MB, gitignored, static export çıktısı | Dockerfile multi-stage içinde regenerate edilir, local kopya opsiyonel |

### 2f. Bot çalışması için **GEREKSİZ** ama meta-dosya

| Yol | Açıklama |
|---|---|
| `.claude/` | Claude Code agent + skill tanımları (dev-only) |
| `.hermes/` | Hermes plan klasörü (1 eski plan) |
| `.mcp.json` | GitHub MCP server config (dev-only) |
| `docs/` | Spec + plan + handoff dokümanları (dev-only, prod runtime'da okumaz) |
| `scripts/` | Backtest + audit yardımcı script'leri (manuel çağrılır, prod runtime'da otomatik değil) |

---

## 3. ENV Dosyaları & Infra Bağlantıları

### 3a. Env dosyaları — nerede, ne içerir

| Dosya | Konum | Amaç | Git tracked? |
|---|---|---|---|
| `.env` | `c:\Users\utkuc\Downloads\efloud-bot\.env` | **Local dev** (smoke, backtest) | ❌ (gitignore) |
| `.env.example` | repo root | Local dev template | ✅ |
| `.env.production` | **VPS:** `/opt/efloud-bot/.env.production` | **Prod runtime** — `docker-compose.prod.yml` `env_file:` bunu okur | ❌ (gitignore, sadece VPS'te var) |
| `deploy/.env.production.example` | repo root | VPS template | ✅ |
| `frontend/.env.example` | `frontend/` | Frontend dev template | ✅ |

### 3b. Production env var'ları — ne, neden

`/opt/efloud-bot/.env.production` (Hetzner VPS) içermesi gerekenler:

| Variable | Tip | Değer | Açıklama |
|---|---|---|---|
| `BINANCE_API_KEY` | secret | Mainnet futures key | Binance → API Mgmt → Futures + IP whitelist (<VPS_IP>) |
| `BINANCE_API_SECRET` | secret | Mainnet secret | Aynı |
| `EFLOUD_ALLOW_MAINNET` | flag | `1` | mainnet_guard bypass'ı için zorunlu |
| `EFLOUD_CONFIG_PATH` | path | `configs/config.phase2_1k.yaml` | Aktif profile |
| `EFLOUD_AUTOSTART` | flag | `0` | İncident-recovery posture (operator dashboard'dan Start) |
| `EFLOUD_AUTO_MIGRATE` | flag | `0` | DB pooler sorunu çözülünce `1` |
| `DASHBOARD_PASSWORD` | secret | 32+ char | `bot.ualgotrade.com` login |
| `SESSION_SECRET` | secret | 32 hex | Cookie imzalama |
| `DATABASE_URL` | url | (şu an commented out) | Supabase pooler — bkz. 3c |
| `ALLOWED_ORIGINS` | csv | `https://bot.ualgotrade.com,https://<VPS-IP>.nip.io` | CORS |
| `ENV` | string | `production` | Secure cookie açar |
| `LOG_LEVEL` | string | `INFO` | |
| `ANTHROPIC_API_KEY` | secret | Claude Haiku key | Overseer LLM summarizer |
| `ANTHROPIC_MODEL` | string | `claude-haiku-4-5-20251001` | (compose override'dan geliyor da) |
| `EFLOUD_TELEGRAM_TOKEN` | secret | (opsiyonel) | Telegram alert (alerter container) |
| `EFLOUD_TELEGRAM_CHAT_ID` | secret | (opsiyonel) | Aynı |

### 3c. Supabase bağlantısı (DB persistence — şu an KAPALI)

- **Status**: `EFLOUD_AUTO_MIGRATE=0`, `DATABASE_URL` commented out. Supabase pooler "Tenant or user not found" hatası veriyor (Supavisor routing, password değil).
- **Tablolar sağlıklı** (MCP üzerinden doğrulandı), sadece async bot bağlanamıyor.
- **Bağlantı URL formatı**:
  ```
  postgresql://postgres.<PROJECT_REF>:<PASSWORD>@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
  ```
  - `<PROJECT_REF>`: Supabase dashboard → Project Settings → Reference ID (örn: `okimvywmhcwbtwtegyjm`)
  - Port `6543` = Transaction pooler (asyncpg-uyumlu); `5432` = direct (Hetzner'dan blocked)
  - Region: `eu-central-1`
- **Çalıştırma sırası** (pooler düzeldiğinde):
  1. `.env.production`'da `DATABASE_URL` uncomment + doğru credentials
  2. `EFLOUD_AUTO_MIGRATE=1` (ilk sefer için)
  3. `docker compose -f docker-compose.prod.yml up -d`
  4. İlk start'ta `backend/migrations/001..008_*.sql` otomatik uygulanır
  5. Sonradan `EFLOUD_AUTO_MIGRATE=0` yap (manuel `docker exec efloud-bot python3 -m backend.migrate up` ile çalıştır)

### 3d. Hetzner bağlantısı

| Item | Değer |
|---|---|
| **Provider** | Hetzner Cloud (CPX22 #128829260) |
| **Host IP** | `<VPS_IP>` |
| **OS** | Ubuntu 22.04 |
| **SSH alias** | `ssh efloud-bot` (local `~/.ssh/config`) |
| **SSH key** | `~/.ssh/id_ed25519` (label `efloud-bot-hetzner`) |
| **Repo path** | `/opt/efloud-bot` (clone via deploy key) |
| **User** | `efloud` (docker group member) |
| **Ports** | 80 (HTTP→HTTPS), 443 (HTTPS), 22 (SSH) — UFW |
| **Domain** | `bot.ualgotrade.com` (Caddy + Let's Encrypt) |
| **Fallback** | `<VPS-IP>.nip.io` |
| **Docker volumes** | `efloud_state`, `efloud_state_1k`, `efloud_state_aggressive`, `efloud_logs`, `efloud_reports`, `caddy_data`, `caddy_config` |
| **Compose dosyası** | `/opt/efloud-bot/docker-compose.prod.yml` |
| **Env dosyası** | `/opt/efloud-bot/.env.production` (VPS-local, gitignored) |

### 3e. Binance bağlantısı

- **Tip**: USDT-M Futures (mainnet, isolated margin, hedge mode OFF)
- **Key permissions**: Futures Read + Trade (Spot Trade KAPALI, Withdraw KAPALI)
- **IP whitelist**: **Sadece** `<VPS_IP>` (Hetzner VPS IP'si)
- **Symbol format**: Local Position `BTC/USDT`, CCXT call `BTC/USDT:USDT` (`to_ccxt_symbol()` köprüsü)
- **Tuzak**: `defaultType` mutlaka `future` (singular). `futures` (plural) spot'a düşer — bkz. `binance_ccxt_conditional_orders` memory

### 3f. Anthropic bağlantısı (Overseer sidecar)

- **Model**: `claude-haiku-4-5-20251001`
- **Env**: `ANTHROPIC_API_KEY` (compose `overseer` servisi okur)
- **Cap**: `EFLOUD_OVERSEER_LLM_DAILY_CAP=500` (compose'da set)
- **Dry-run**: `EFLOUD_OVERSEER_DRY_RUN=1` (Week 1, log-only) — Hermes manuel olarak `0` yapar

---

## 4. Bağlantı Şeması (Üst Bakış)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Hetzner Cloud (CPX22)                       │
│                       <VPS_IP>                            │
│                       /opt/efloud-bot                           │
│                                                                 │
│  ┌──────────┐    ┌────────────────┐    ┌──────────────────┐   │
│  │  caddy   │───▶│   efloud-bot   │◀──▶│ Binance Futures  │   │
│  │  :80/443 │    │     :8080      │    │  (USDT-M, IP WL) │   │
│  └──────────┘    │  FastAPI +     │    └──────────────────┘   │
│       │          │  SafeOrch +    │                            │
│       │          │  SMC v1/v2     │    ┌──────────────────┐   │
│       │          └────────────────┘    │ Supabase Pooler  │   │
│       │                  │             │  (eu-central-1)  │   │
│       │                  ├─── DB ─────▶│  port 6543       │   │
│       │                  │             │  (şu an KAPALI)  │   │
│       │          ┌───────┴────────┐    └──────────────────┘   │
│       │          │   overseer     │                            │
│       │          │   alerter      │    ┌──────────────────┐   │
│       │          │   daily-report │───▶│  Anthropic API   │   │
│       │          │   autoheal     │    │  (Claude Haiku)  │   │
│       │          └────────────────┘    └──────────────────┘   │
│       │                                                        │
│       │                                ┌──────────────────┐   │
│       │                                │  Telegram Bot    │   │
│       │                                │  (alerter sink)  │   │
│       │                                └──────────────────┘   │
└───────┼────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────┐
│ bot.ualgotrade.com  │  (Cloudflare DNS → Caddy → bot)
│  + nip.io fallback  │
│  (HTTPS, Let's Enc) │
└─────────────────────┘
```

---

## 5. Senin Aksiyon Listen (Bu Bölümü Çıktı Olarak Hermes'e Ver)

### Acil
1. **Binance API key'i rotate et** (gerçek key `.env`'de görünmüş, IP whitelist'le yeni key oluştur)
2. **Anthropic + 6 LLM key rotate et** (`.env`'de plaintext)
3. Local `.env`'i ya sil ya da gerçek değerleri placeholder yap

### Repo temizliği (Claude tarafı, Hermes onayı sonrası)
4. PR: 12 root test dosyası + `superagentv3.py` + `preflight.py` sil → tek atomik PR
5. PR: `railway.{json,toml}` sil → "Railway artifact removal"
6. PR: `MAINNET_GECIS_REHBERI.md`, `PR_BODY.md`, `RISK_MAP.md` archive klasörüne taşı veya sil
7. PR: `configs/config.aggressive_v1.yaml` + 3 grid-tuning yaml → `configs/archive/`'a taşı
8. Local: `Efloud-bot/`, `__write_test_2/`, root `__pycache__` sil (commit gerekmez)

### Prod readiness
9. Hermes: `ssh efloud-bot` + `cd /opt/efloud-bot` + `git pull` + `docker compose -f docker-compose.prod.yml up -d` (zero-risk, v2 inert)
10. Hermes (sonra): Supabase pooler düzelt → `EFLOUD_AUTO_MIGRATE=1` ile bir recreate → telemetry persist açılır

---

## 6. Hızlı Doğrulama Komutları

```bash
# Local: hangi dosyalar prod runtime'da gerçekten gerekli (Dockerfile COPY scope)
git ls-files | grep -v -E '^(backend/tests/|tests/|docs/|.claude/|.hermes/|configs/archive/|configs/grids/)' | wc -l

# Local: hangi dosyalar gitignored
git status --ignored --short | head -20

# VPS: deploy'dan sonra container hangi dosyaları kullanıyor
ssh efloud-bot 'docker exec efloud-bot ls /app | head -30'

# Local: hangi config'ler tracked
git ls-files configs/

# Local: hangi env dosyaları diskte
ls -la .env* deploy/.env*
```
