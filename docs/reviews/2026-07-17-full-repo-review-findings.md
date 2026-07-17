# 2026-07-17 Tam Repo Review — Bulgular ve Düzeltmeler

3 paralel review ajanı (backend / routines+alerting / engine-core) + manuel
doğrulama (ccxt/pandas empirik probe'ları, RED→GREEN testler). Ortam: cloud
container, Python 3.11 + pandas 3.0.2 + ccxt 4.5.66 (prod'la aynı 3.11; deps
pinlenmemiş `>=` olduğu için drift prod rebuild'de aktifleşir).

**Baseline:** `tests/` 600 passed · `backend/tests` 2 FAILED (url-routing +
stale-cache) / 1534 passed.
**Sonuç:** `tests/` **623 passed** · `backend/tests` **1542 passed / 0 failed**
(15 skip = DATABASE_URL yok; resmi gate hâlâ Windows Docker
`scripts/run_tests_docker.ps1`).

**Commit'ler (origin/master `d9d4cef` önünde — PUSH Windows'tan):**
`d7219cc` routines+alerting+drift · `2a307d0` exchange+engine · `2888ac2` backend.

Bu tur `docs/reviews/2026-07-11-*` içindeki ERTELENEN kalemlerden değil — yeni
bulgulardır. Grup A/C (tighten-stops, intent, dedup-quantize, smc_v2 axis,
data/fetcher) master plan gereği backtest-gate + operatör onayı beklediğinden
KASITLI OLARAK ELLENMEDİ.

## Canlı-para etkili (critical/high)

| # | Yer | Bulgu → Sonuç | Fix |
|---|-----|---------------|-----|
| B-1 | exchange/__init__.py reconcile TP1/TP2 | "kayıp" tespiti `algo_fetch_ok` gate'siz. Canlı TP'ler algoId; geçici algo-fetch hatası (5xx) → her TP "kayıp" → id temizlenir → aynı cycle repair CANLI orijinallerin yanına duplicate TAKE_PROFIT_MARKET basar (2026-05-08 stacking sınıfı; SL korunuyordu, TP değildi) | İki blok da `algo_fetch_ok` ile gate'lendi. RED→GREEN: `test_reconcile_algo_fetch_guard` |
| E-1 | exchange `_persist` + safety/state `save` | Sabit `.tmp` adı; _persist hem bot executor hem FastAPI loop thread'inden (kill-switch/close) çağrılır → eşzamanlı yazım birbirini truncate/rename → bozuk state terfi → restart'ta quarantine → 0 pozisyonla açılış (reconcile körlüğü) | Yazar-özel `pid+tid` tmp adı |
| B-2 | backend/social/queue_storage `save_draft` | `$(name)` placeholder + `execute(**kwargs)` asyncpg'de geçersiz → gerçek DB'ye her yazım TypeError (mock'la geçiyordu) → approve/reject 500; publish sonrası status persist edilemeyince draft 60sn'de bir YENİDEN yayınlanır | Pozisyonel `$1..$11` |
| R-1 | routines/breaker_watch + alerter | Mainnet breaker HALT alarmı ÜÇ kanalda da ölü: watch yanlış state_dir + StateStore zarfı açılmıyor; healthz `breaker_halted` imzasını eşleyen kural yok | `resolve_state_dir`/`unwrap_state` + `HealthBreakerHaltedRule` |
| R-3 | routines/position_audit | Aynı path/zarf hatası → her açık pozisyonda kalıcı false "Position Drift" CRITICAL; gerçek drift ayırt edilemez | Aynı helper'lar |
| R-4/R-8 | routines/resolve_signals | Genç sinyal (horizon dolmadan) kalıcı `timeout`/`unresolved_data` TERMİNALİNE yazılıyordu → edge örneklemi ~%100 timeout'a çökerdi | Wall-clock horizon guard |
| R-6 | alerter dedup + telegram | Dedup teslimattan ÖNCE tüketiliyordu (başarısız gönderim tek-atım transition alert'ini yutar) + HTML-mode'da ham `<` (breaker "balance $X < $Y") Telegram 400 veriyordu | `would_fire`/`mark_fired` + `html.escape` |

## Orta / düşük

| # | Yer | Bulgu | Fix |
|---|-----|-------|-----|
| E-2 | engine/journal `_persist` | truncate-in-place → crash tail loss | tmp+fsync+os.replace |
| E-3 | safe_orchestrator ×2 + backend/api close | canlı `positions` RAW iterate → cross-thread `list.remove` eleman atlatıp canlı pozisyonu logical-only kapatır → duplicate-guard körleşir | `_positions_snapshot()` |
| E-4 | safe_orchestrator leblep-reject | erken-return SMC-v2 setup persist'ini atlıyor | gated save |
| E-5 | safe_orchestrator corrections drain | mid-raise → `clear()` atlanır → çift apply | `finally` |
| E-6 | instance_manager `sync_release_symbol` | `CancelledError` (BaseException) `except Exception`'ı aşıp cycle hatasını maskeler | açık dal |
| B-3 | social/xurl_client | worker `post_draft` çağırır, XurlClient'ta yoktu → 'x' sonsuz retry | `post_draft` adapter |
| B-4 | backend/api close | idempotency key deneme-öncesi → başarısızda pozisyon açıkken `dedup:true` | başarı-sonrası kayıt |
| B-6 | backend/bot_runner `start` | TOCTOU → çift start iki loop task → SL kaybı breaker'a 2× | `_starting` guard + `_start_impl` |
| B-8 | backend/api `/media` | tek auth'suz veri endpoint'i (cache/ anonim) | `require_auth` |
| B-11 | bot_runner record_trade_open | `confluence` hep NULL | `confluence_details.score` |
| R-7 | routines/config_drift | watch key'leri `/api/config` şemasıyla uyumsuz (2 kör, 2 kalıcı false) | şemaya hizalandı |
| R-9 | routines/resolve_signals alert | `AlertRouter()` tg=None | `from_env()` |
| R-10 | routines/equity_report | DB `{ts,balance}` şeması okunmuyor → metrikler 0.00 | normalize |
| R-12 | routines/runner | sessiz `except ImportError: pass` → dep-drift'te rutin sessizce düşer | yüksek sesli log |
| ccxt≥4.5 | _base + preflight | symbol'süz `fetch_open_orders` SPOT'a düşüyordu | method-scoped `fetchOpenOrders` swap |
| pandas-3 | data/cache | `astype('int64')` us→ms yerine saniye (manifest max_ts ~1970 → BT-15 false stale) | `as_unit('ns')` |

## Doğrulama kanıtı

Her fix cerrahi diff; canlı-para etkili olanlar RED→GREEN testli
(`test_reconcile_algo_fetch_guard`, `test_persist_crash_safety`,
`test_content_queue` positional, `test_xurl_client` post_draft, routine +
resolver + alerter regresyonları). Commit blob'ları grep'le doğrulandı; working
tree == HEAD (fark yalnız CRLF). Guard/breaker/orphan koruması zayıflatılmadı;
yeni davranış toggle'ı eklenmedi (hepsi bug-fix). `requirements.txt` hâlâ
pinlenmemiş — ayrı bir sertleştirme kalemi olarak önerilir.

## Tur 2 (aynı gün, ek 7 fix)

| # | Yer | Bulgu | Fix |
|---|-----|-------|-----|
| R-2+ | routines/position_audit | (a) Botun TP/SL'leri ALGO emirleri — audit yalnız regular emirlere bakıyordu → her korumalı pozisyon false "Bare Position" CRITICAL; (b) sembol formatları (ccxt `X/Y:Y` ↔ ledger `X/Y` ↔ raw `XY`) normalize edilmeden drift map'leri HİÇ eşleşmiyordu → pozisyon başına 2 false CRITICAL daha | `fapiPrivateGetOpenAlgoOrders` merge (+fail-safe skip) + `_norm_sym` |
| B-9 | backend/events EventBus | asyncio.Queue thread-safe değil; bot-thread publish loop'u uyandırmıyordu → WS event'i 30 sn'ye dek gecikir, iptal yarışında sessiz düşer | loop-dışı publish `call_soon_threadsafe` ile teslim |
| B-10 | backend/audit/journal | senkron `requests.get` event loop ÜZERİNDE → her kapanışta 5-10 sn tüm FastAPI/WS/healthz donması | `run_in_executor` |
| R-11 | telegram_notifier + telegram_digest | Gate EN metni denetliyor, kanala TR metin gidiyordu; TR kopya `getiri %` ile CMP-3 ihlaliydi | TR kopya EN'in uyumlu yüzeyine ("Net K/Z") + gönderilen render'a gate |
| R-14 | routines/market_collect | weight_warn/alert/critical eşikleri türetilip hiç değerlendirilmiyordu → ilk belirti canlı -1003 ban | `_weight_breach` (1200/dk bütçesi) |
| B-5 | Dockerfile CMD | uvicorn proxy-headers'sız → login rate-limit tek global kovaya çöküyor, anonim biri operatörü dashboard'dan kilitleyebiliyordu | `--proxy-headers --forwarded-allow-ips '*'` |
| deps | constraints.txt + Dockerfile | `>=` aralıkları her rebuild'de drift çekiyordu (bu review'un 2 bug'ının kökü) | Pinlenmiş kapanış; temiz venv'de tam suite ile doğrulandı |
| ops | docker-compose.prod.yml | routines container'ları `EFLOUD_STATE_DIR` bilmiyordu → R-1/R-3 fix'i prod'da etkisiz kalırdı | `/app/state_1k` env (watcher + scheduled) |

Tur-2 sonrası: `tests/` **628** / `backend/tests` **1550**, 0 failed — hem
serbest sürümlerle hem constraints.txt pinleriyle (temiz venv) birebir.

## Sonraki adımlar (operatör / Claude Code)

Devir listesi + yapıştır-kullan prompt:
`docs/handoff/2026-07-17-vscode-claude-code-handoff.md`.
Kısaca: (1) push — 7 commit; (2) Docker gate + backend/tests; (3) VPS'te
**build + up -d** (Dockerfile değişti — rebuild zorunlu) + 24h gözlem;
(4) kalan tasarım işleri: B-7 pubsub gate, R-13 overseer kuralları, E-5
breaker id-match, W2 backtest-gate kalemleri, W5 güvenlik.
