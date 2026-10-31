# efloud-bot

Binance USDT-M Futures üzerinde **Smart Money Concepts (SMC)** doktriniyle çalışan otonom trade botu.
Python (CCXT + FastAPI) backend, Next.js dashboard, TradingView Pine Script v6 göstergeleri.

> Bu yazılım finansal tavsiye değildir. Kaldıraçlı işlemler sermayenin tamamını kaybettirebilir.
> Önce **testnet + dry_run** ile çalıştırın.

## Nasıl çalışır (v2)

1. **HTF bias** (4h) belirlenir — yalnızca trend yönünde işlem.
2. **LTF (15m) CHoCH veya BOS** kırılımı beklenir.
3. Kırılımı başlatan **OB/BB bölgesi** ve impulsun **OTE (0.618–0.786)** bandı hedef bölge olur.
4. Fiyat bölgeye geri çekilince **engulfing teyidi** → limit emir.
5. **SL**: impulsun başlangıç swing'inin (likidite çizgisi) ötesi; **TP**: likidite / RR hedefleri.
6. Güvenlik katmanı: günlük %10 / haftalık %25 kayıp breaker'ı, kill-switch, reconcile, SL repair.

## Hızlı başlangıç (Docker — önerilen)

```bash
git clone https://github.com/Leblepito/efloud-bot.git
cd efloud-bot
cp .env.example .env          # API key, DASHBOARD_PASSWORD, SESSION_SECRET doldur
docker compose up -d --build  # tek bot + dashboard
```

Dashboard: http://localhost:8080 → şifreyle giriş → **Start**.
Varsayılan config `configs/config.testnet.yaml` (testnet + dry_run). Canlıya geçmek için `.env` içinde:

```bash
EFLOUD_CONFIG_PATH=configs/config.phase2_1k.yaml
EFLOUD_ALLOW_MAINNET=1
```

## Lokal geliştirme (Docker'sız)

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -c constraints.txt
npm ci && npm run build --workspace efloud-frontend  # dashboard → frontend/out
uvicorn backend.main:app --port 8080
```

## Dashboard

| Sekme | İçerik |
|---|---|
| Overview | Bot durumu, breaker, bakiye, canlı grafik (SMC overlay), equity eğrisi |
| Positions | Açık pozisyonlar, açık emirler, son işlemler |
| History | Tüm kapanmış işlemler (500'e kadar), win-rate, net PnL, equity |
| Research | Piyasa göstergeleri (funding, OI), sosyal araştırma |
| Config | Aktif risk/engine ayarları |

Geçmiş işlemler `DATABASE_URL` varsa Postgres'ten, yoksa config'teki `state_dir/trade_journal.jsonl` dosyasından okunur.

## VPS (Hetzner) üretim kurulumu

```bash
bash deploy/setup-server.sh                 # ilk kurulum (Docker, UFW, kullanıcı)
cp deploy/.env.production.example .env.production && nano .env.production
bash deploy/deploy.sh                       # git pull + build + up -d + healthcheck
```

`docker-compose.prod.yml` çoklu bot (mid/long/scalp), Caddy (otomatik HTTPS), autoheal,
alerter, overseer ve rutin servislerini içerir. Alan adlarını `deploy/Caddyfile` içinde düzenleyin.
Ayrıntılar: `docs/OPERATOR_GUIDE.md`, `deploy/HETZNER_GUIDE.md`, `docs/runbooks/`.

## Proje yapısı

```
backend/     FastAPI API, bot runner, auth, DB, sosyal içerik kuyruğu
engine/      SMC analiz, v2 pipeline (engine/smc_v2), orchestrator, safety (breaker)
exchange/    Binance emir yönetimi (OrderManager, reconcile, SL/TP repair)
frontend/    Next.js dashboard (static export, backend tarafından servis edilir)
configs/     Bot config'leri (phase2_1k = canlı, testnet = deneme)
deploy/      Caddy, deploy/setup scriptleri, .env örnekleri, yedekleme
ops/         Alerter (Telegram), overseer, günlük rapor
scripts/     Rutinler (scripts/routines), sosyal medya pipeline'ı, yardımcı araçlar
u2algo-site/ Pazarlama sitesi (Railway servisi `u2algo-site`, root dir /u2algo-site)
pine/        TradingView Pine Script v6 göstergeleri
tests/, backend/tests/   pytest testleri
```

## Test

```bash
python -m pytest tests backend/tests -q --import-mode=importlib
cd frontend && npx vitest run
```

## Belgeler

- `docs/OPERATOR_GUIDE.md` — günlük operasyon, config, incident
- `HERMES.md` — operatör/agent kılavuzu
- `AGENTS.md`, `CLAUDE.md` — AI agent bağlamı
- `CHANGELOG.md` — değişiklik geçmişi
