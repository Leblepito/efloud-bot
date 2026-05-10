# Efloud-bot — Claude Project Memory

> Bu dosya her oturumda otomatik yüklenir. Bot mimarisi, ops kuralları ve güncel
> durum burada. Değişiklikten önce **mutlaka** ilgili bölümü oku.

---

## 1. Proje Amacı

Efloud SMC (Smart Money Concepts) trade bot + **Ualgo Telegram sinyal entegrasyonu**.
- Bugün: Binance USDT-M futures üzerinde kripto trade.
- Yarın: aynı motorla forex (MT5/OANDA) — `/exchange` katmanı pluggable hale getirilecek.

Yardımcı projeler:
- **Ualgo_bot** (aktif odak): Telegram sinyal toplayıcı/dispatcher.
- **U2algo_bot**: şimdilik rafta.

---

## 2. Mimari Hızlı Referans

```
main.py
  └── SafeOrchestrator (engine/__init__.py)
        ├── BinanceClient + OrderManager (exchange/__init__.py)
        ├── SMC engine + signals (engine/smc.py, engine/signals.py)
        ├── Regime detector (engine/regimes/__init__.py)
        ├── Confluence scoring (engine/confluence.py)
        ├── Lifecycle / position state (engine/lifecycle.py)
        └── Safety layer (engine/safety/breaker.py, position_guard.py, mainnet_guard.py)

backend/main.py     → FastAPI :8080 + WebSocket
frontend/           → Next.js 15 dashboard (static export)
backtest/engine.py  → walk-forward simulation
ops/                → Telegram alerter, daily reports
```

**Anahtar dosya:satır referansları** *(yaklaşık — düzenleme öncesi `grep`/`rg`
veya doğrudan dosya okuyarak gerçek satır numarasını ve fonksiyon konumunu
mutlaka doğrula)*

| Sembol | Yer |
|--------|-----|
| `BinanceClient` | `exchange/__init__.py:27` |
| `OrderManager.place_order` | `exchange/__init__.py:200` |
| reconcile loop | `exchange/__init__.py:346` |
| `Position` dataclass | `engine/lifecycle.py:40` |
| circuit breaker | `engine/safety/breaker.py` |
| signal generation | `engine/signals.py:68` |
| SMC indicators | `engine/smc.py` |
| regime detection | `engine/regimes/__init__.py:71` |
| FastAPI endpoints | `backend/api.py` |
| Telegram notifier | `backend/notifications/__init__.py:39` |
| migrations runner | `backend/migrate.py` |

**Konfig**: `config.yaml` (root). Env > file precedence. Anahtar env var'lar:
`BINANCE_API_KEY`, `BINANCE_API_SECRET`, `EFLOUD_ALLOW_MAINNET=1` (mainnet için zorunlu),
`DATABASE_URL`, `EFLOUD_TELEGRAM_TOKEN`, `EFLOUD_TELEGRAM_CHAT_ID`.

---

## 3. Live Ops Uyarısı (KRİTİK)

- **Production canlı çalışıyor — Hetzner VPS, docker-compose.prod.yml.**
- Canlı deploy, risk parametresi değişikliği, mainnet aç/kapa **Hermes veya Utku onayı olmadan yapılmaz.**
- Mainnet guard: `EFLOUD_ALLOW_MAINNET=1` env yoksa testnet'e zorlanır.
- `dry_run: true` default — false'a çekmeden önce backtest + onay.

### Rol Ayrımı: Hermes vs Claude Code

**Hermes** (insan onay/aksiyon zinciri):
- Canlı production yönetimi: deploy, VPS/SSH erişimi, `docker compose up -d`, `backend.migrate up`.
- Risk kararları: risk/safety config değişiklikleri, mainnet aç/kapa, leverage/sizing.
- Merge/deploy onayı: PR sign-off, production rollout.
- Incident response: canlı sistem teşhis ve düzeltme.

**Claude Code** (repo içi non-critical iş):
- Docs, tests, refactor önerisi, PR hazırlığı.
- Code review yardımcıları (efloud-code-reviewer, efloud-risk-ops-reviewer agent'ları).
- Backtest analizi, kod araştırma, yeni feature taslağı.
- **Yapmaz**: production komutu çalıştırmak, canlı risk/config değiştirmek, merge/deploy etmek, mainnet guard'ı bypass etmek.

---

## 4. PR & Review Disiplini

- **Atomik PR**: bugfix + refactor + feature aynı PR'a karıştırılmaz. Her concern ayrı PR.
- Değişiklikten **önce**: ilgili pytest dosyasını çalıştır.
- Değişiklikten **sonra**: diff özeti + etkilenen modüller + test sonucu yaz.
- Risk/safety dosyaları değişiyorsa `efloud-risk-ops-reviewer` agent'ını çağır.
- Genel review için `efloud-code-reviewer` agent'ını çağır.

---

## 5. Known Ops Notları

### Docker Compose
- **Env değişikliği** (`docker-compose.prod.yml` veya `.env`) → `docker restart` **YETMEZ**.
  Doğru komut: `docker compose -f docker-compose.prod.yml up -d` (recreate eder).

### Database Migrations
- Yeni `.sql` veya yeni migration eklendiyse production'da **manuel** çalıştır:
  ```bash
  docker exec efloud-bot python3 -m backend.migrate up
  ```
- Çıktıyı log'a kopyala, başarısız adımı PR description'a ekle.

### CCXT Order Reconcile Tuzağı
- `ccxt.fetch_open_orders` Binance'in **conditional/algo TP-SL order'larını göremeyebilir**.
- Reconcile sırasında: Binance algo endpoint (`fapiPrivateGetOpenOrders` + `algo`) veya
  Binance UI ile cross-check zorunlu. Bkz. 2026-05-08 reconcile-blindspot incident
  (`exchange/__init__.py:36-38` yorumu).

### Symbol Format (Futures)
- Local Position state: `BTC/USDT` (slash-only).
- CCXT futures call'ları: `BTC/USDT:USDT` suffix gerekir, aksi halde spot endpoint'e düşer.
- `to_ccxt_symbol()` ve `_strip_contract_suffix()` bu köprüyü kurar — bypass etme.

---

## 6. Güncel Durum (2026-05-10)

| Item | Durum |
|------|-------|
| **PR #30** | Deployed — WEAKNESS churn fix + `log_audit` JSONB cast fix |
| **PR-B daily brief** | Audit tamamlandı |
| **U2algo_bot** | Rafta |
| **Aktif odak** | Ualgo_bot + Efloud-bot |
| **Forex broker kararı** | Açık (MT5 vs OANDA — TR/TH banka uyumu kriter) |
| **UI/UX kapsamlı analiz** | Sıradaki büyük iş |

---

## 7. Custom Agents & Skills (proje içi)

`.claude/agents/`
- **efloud-code-reviewer** — diff/PR review, atomik PR & simplicity guard.
- **efloud-risk-ops-reviewer** — `engine/safety/`, `exchange/`, `config.yaml` (risk:/safety:),
  `docker-compose.prod.yml`, migrations değişikliklerinde **zorunlu**.
- **efloud-test-engineer** — pytest yazımı, mock disiplini, smoke set'i çalıştırma.

`.claude/skills/`
- **efloud-bugfix-workflow** — repro → lokalize → fix → test → PR akışı.
- **efloud-deploy-safety** — Hetzner/compose deploy guard'ları.
- **efloud-trading-risk-checklist** — `risk:`/`safety:` config değişiklikleri için kontrol listesi.

> Ek opsiyonel agent/skill'ler (efloud-explorer, efloud-uiux-audit,
> efloud-forex-adapter-research, /review komutu) ayrı PR'da
> (`docs: add optional efloud Claude extras`) önerilmiştir.

`.claude/settings.local.json` ve `.env` **gitignore'da** — secret commit edilmez.

---

## 8. Forex Roadmap (Teaser — Detay Sonra)

- `/exchange/__init__.py` bugün Binance-bound (`set_leverage` Binance-spesifik
  `fapiPrivatePostLeverage`, order tipleri Binance naming).
- Hedef: pluggable adapter pattern (`ExchangeAdapter` protocol + concrete
  `BinanceAdapter`, `MT5Adapter`, `OandaAdapter`).
- Broker kararı kriterleri: TR/TH banka kabul yaygınlığı, Linux/Docker uyumu,
  Python SDK kalitesi. Detaylı analiz ayrı PR'da.

---

## 9. Yapma Listesi (DON'T)

- ❌ `EFLOUD_ALLOW_MAINNET=1` set edip dry_run=false bırakıp deploy etme.
- ❌ Compose env değiştirip sadece `docker restart` çekme.
- ❌ Risk/safety değişikliğini test eklemeden veya backtest'siz mergelama.
- ❌ Birden fazla concern'i tek PR'da karıştırma.
- ❌ Secret/API key'i repo'ya commit etme (`.gitignore` + `.env.example` kullan).
- ❌ Live API'ye gerçek istek atan default test yazma.
