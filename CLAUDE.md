# Efloud-bot — Claude Project Memory

> Otomatik yüklenir. Bot mimari, ops kural, durum. Değişiklik öncesi oku.

---

## 1. Proje Amacı

Efloud SMC trade bot + **Ualgo Telegram sinyal entegrasyonu**.
- Bugün: Binance USDT-M futures kripto trade.
- Yarın: Forex (MT5/OANDA). `/exchange` katmanı pluggable yapılacak.

Yardımcı projeler:
- **Ualgo_bot** (aktif odak): Telegram sinyal toplayıcı/dispatcher.
- **U2algo_bot**: rafta.

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

**Anahtar dosya:satır referansları** *(Doğrulamak için `grep`/`rg` kullan)*

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

**Config**: `config.yaml` (root). Env > dosya önceliği. Anahtar env'ler:
`BINANCE_API_KEY`, `BINANCE_API_SECRET`, `EFLOUD_ALLOW_MAINNET=1` (mainnet zorunlu),
`DATABASE_URL`, `EFLOUD_TELEGRAM_TOKEN`, `EFLOUD_TELEGRAM_CHAT_ID`.

---

## 3. Live Ops Uyarısı (KRİTİK)

- **Prod canlı çalışıyor — Hetzner VPS, docker-compose.prod.yml.**
- Canlı deploy, risk config, mainnet aç/kapa **Hermes veya Utku onayı olmadan yapılmaz.**
- Mainnet guard: `EFLOUD_ALLOW_MAINNET=1` yoksa testnet'e zorlar.
- `dry_run: true` default. False öncesi backtest + onay.

### Rol Ayrımı: Hermes vs Claude Code

**Hermes** (insan onay/aksiyon):
- Prod yönetimi: deploy, VPS/SSH, `docker compose up -d`, `backend.migrate up`.
- Risk kararları: risk/safety config, mainnet aç/kapa, leverage/sizing.
- Merge/deploy onay: PR sign-off, prod rollout.
- Incident response: canlı sistem teşhis/düzeltme.

**Claude Code** (non-critical repo işleri):
- Docs, test, refactor, PR hazırlığı.
- Code review (efloud-code-reviewer, efloud-risk-ops-reviewer).
- Backtest analiz, kod araştırma, feature taslağı.
- **YASAK**: prod komutu, canlı risk/config değişimi, merge/deploy, mainnet guard bypass.

---

## 4. PR & Review Disiplini

- **Atomik PR**: Bugfix + refactor + feature karıştırılmaz. Ayrı PR'lar.
- Değişiklik öncesi: Pytest çalıştır.
- Değişiklik sonrası: Diff özeti + etkilenen modül + test sonucu yaz.
- Risk/safety değişimi: `efloud-risk-ops-reviewer` çağır.
- Genel review: `efloud-code-reviewer` çağır.

---

## 5. Known Ops Notları

### Docker Compose
- **Env değişimi** (`docker-compose.prod.yml` veya `.env`) → `docker restart` **YETMEZ**.
  Komut: `docker compose -f docker-compose.prod.yml up -d` (recreate).

### Database Migrations
- Yeni `.sql` / migration için prod'da **manuel** çalıştır:
  ```bash
  docker exec efloud-bot python3 -m backend.migrate up
  ```
- Çıktıyı loga yaz, fail adımı PR description'a ekle.

### CCXT Order Reconcile Tuzağı
- `ccxt.fetch_open_orders` Binance conditional/algo TP-SL order göremeyebilir.
- Reconcile: Binance algo endpoint (`fapiPrivateGetOpenOrders` + `algo`) veya Binance UI ile cross-check zorunlu. Bkz 2026-05-08 reconcile-blindspot incident (`exchange/__init__.py:36-38`).

### Symbol Format (Futures)
- Local Position: `BTC/USDT` (slash-only).
- CCXT futures call: `BTC/USDT:USDT` suffix gerekir. Spot'a düşmesini önler.
- `to_ccxt_symbol()` ve `_strip_contract_suffix()` köprüyü kurar, bypass etme.

### CLI vs FastAPI Wiring Parity (Kritik — 2026-05-28 Incident)
- `main.py` (CLI) ve `backend/bot_runner.py` (FastAPI) her ikisi de **bağımsız şekilde** `OrderManager` ve `SafeOrchestrator` oluşturuyor.
- Herhangi bir construction parametresi değişikliği (**hedge_mode**, **state_dir**, **orphan_protector**, **trade_journal**, **on_position_change**) **her iki dosyaya** yansımalı.
- Aksi halde CLI mode sessizce diverge olur — production doğru çalışırken CLI modu korumasız pozisyonlar açıyordu (2026-05-28 SL/TP delivery incident).
- Yeni param eklerken: `grep -n "OrderManager(" main.py backend/bot_runner.py` ile her iki yeri yakala.

---

## 6. Güncel Durum (2026-05-28)

| Item | Durum |
|------|-------|
| **fix/sltp-delivery-reliability** | ✅ Pushed — GitHub PR bekliyor (branch: `fix/sltp-delivery-reliability`) |
| **PR #92-#98 (Son merged)** | `6d784a2` — Social Learning + verdict badges + research guards |
| **PR-B daily brief** | Audit tamamlandı |
| **U2algo_bot** | Rafta |
| **Aktif odak** | Ualgo_bot + Efloud-bot |
| **Forex broker kararı** | Açık (MT5 vs OANDA — TR/TH banka uyumu kriter) |
| **UI/UX kapsamlı analiz** | Sıradaki büyük iş |

### SL/TP Delivery Fix (2026-05-28)

Branch `fix/sltp-delivery-reliability` şu an GitHub'da, review bekliyor:

- **BUG #1**: `main.py` OrderManager wiring eksik (hedge_mode, state_dir, orphan_protector)
- **BUG #2**: SL placement retry yoktu (TP'de vardı, SL'de yoktu)
- **BUG #3**: `_repair_missing_protection_orders` sadece TP1/TP2 tamir ediyordu (SL değil)
- **BUG #4**: `_move_sl_to_breakeven` SL placement başarısızlığında recovery yoktu

**Plan**: `.hermes/plans/2026-05-28_sltp-delivery-bugfixes.md`
**Testler**: 272 passed, 0 failed (13 yeni test)

---

## 7. Custom Agents & Skills (proje içi)

`.claude/agents/`
- **efloud-code-reviewer**: diff/PR review, atomik PR & simplicity guard.
- **efloud-risk-ops-reviewer**: `engine/safety/`, `exchange/`, `config.yaml` (risk/safety), `docker-compose.prod.yml`, migrations değişimlerinde **zorunlu**.
- **efloud-test-engineer**: pytest, mock, smoke run.

`.claude/skills/`
- **efloud-bugfix-workflow**: repro → localize → fix → test → PR.
- **efloud-deploy-safety**: Hetzner/compose deploy guard.
- **efloud-trading-risk-checklist**: `risk:`/`safety:` config değişim kontrol listesi.

> Ek opsiyonel agent/skill (efloud-explorer, efloud-uiux-audit, efloud-forex-adapter-research, /review) PR'da (`docs: add optional efloud Claude extras`) önerildi.

`.claude/settings.local.json` ve `.env` **gitignore'da**.

### Çoklu Ajan Yol Haritası & Kendini Geliştirme

- **`docs/ROADMAP_AI_INTEGRATION.md`**: AI entegrasyon yol haritası. Ajanlar sıradaki işi buradan seçer, biteni `✅` işaretler.
- **`docs/skill_log.md`**: Skill log. Sonuçlar yazılır, düşük performanslılar revize edilir.
- **`docs/prompt_changelog.md`**: Prompt evolution log.
- **`external_repos/`**: Klonlanmış referanslar (gitignore'd): `autoresearch`, `graphify`, `caveman`, `superpowers`, `system_prompts_leaks`.

### 🏛️ Opus Rolü: MİMAR (Architect)

Multi-model yapıda **Claude Opus** mimardır. Gemini Flash mühendistir.

- **Tasarım & Spec**: Yeni feature için spec yaz, API akış tasarımı, risk analizi. Spec'i `docs/handoff/` dizinine bırak.
- **Code Review**: Flash kodunu incele, güvenlik ve mimari uyum kontrolü.
- **Prompt Optimizasyonu**: Ajan prompt refinement (`system_prompts_leaks` ile).
- **Strateji Değerlendirme**: Backtest analiz, config öneri.
- **Kod yazmaz** — Kod Flash'ın işidir. Spec yazar, handoff bırakır.

Görev tablosu: `docs/ROADMAP_AI_INTEGRATION.md` §6.


## 8. Forex Roadmap (Teaser — Detay Sonra)

- `/exchange/__init__.py` Binance-bound (Binance leverage, order isimlendirmeleri).
- Hedef: Pluggable adapter (`ExchangeAdapter` protocol + `BinanceAdapter`, `MT5Adapter`, `OandaAdapter`).
- Broker kriterleri: TR/TH banka kabulü, Linux/Docker uyumu, Python SDK kalitesi.

---

## 9. Yapma Listesi (DON'T)

- ❌ `EFLOUD_ALLOW_MAINNET=1` + `dry_run: false` kontrolsüz deploy etme.
- ❌ Compose/env değişimi sonrası sadece `docker restart` yapma (recreate gerekir).
- ❌ Risk/safety değişimi test/backtest olmadan mergeleme.
- ❌ Çoklu konuyu tek PR'da karıştırma.
- ❌ Secret commit etme (`.gitignore` + `.env.example`).
- ❌ Live API çağrıları yapan default test yazma.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## autoresearch

This project has an autonomous trading strategy backtest optimizer at `scripts/autoresearch/` built on self-modifying parameters and backtest evaluation loop patterns.

When the user types `/optimize` or requests strategy optimization:
- Propose a branch `strategy-opt/<tag>` and run: `git checkout -b strategy-opt/<tag>`.
- Read and follow all instructions under `scripts/autoresearch/program.md`.
- Run the infinite self-optimizing training and backtest evaluation loop autonomously.
- Log results in `scripts/autoresearch/results.tsv`.

