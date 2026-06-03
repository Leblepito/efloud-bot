# 02 — Code Audit Findings (efloud-bot)

> Phase 2 deliverable. Kaynak: 4 paralel uzman subagent (risk-safety-auditor [opus], smc-strategy-reviewer [opus], agent-team-engineer, general-purpose). Tüm bulgular dosya:satır + kod alıntısı ile doğrulandı. HEAD `93e2652`.
> Tarih: 2026-06-02. ⚠️ Bu kod CANLI gerçek para ile işlem yapıyor (Binance USD-M, ISOLATED, one-way, 5x).
>
> **Önemli çerçeve:** Bot şu an çalışıyor ve PARA KAZANMIYOR/KAYBETMIYOR demek değil — bu bulgular *koşullu* risklerdir (çoğu API-degraded / restart / hızlı churn anlarında tetiklenir). Hiçbiri "deterministik guard zayıf" demiyor; aksine breaker/guard matematiği şaşırtıcı derecede tutarlı (bkz. §6). Sorun: **sessiz başarısızlık sınıfları** ve **forming-bar repaint**.

---

## 0. Severity özeti

| Sev | # | Başlıklar |
|---|---|---|
| **BLOCKER** | 1 | C1: Tüm engine forming (kapanmamış) bar üzerinde çalışıyor → canlıda repaint, backtest'te görünmez |
| **MAJOR** | 11 | C2 breaker PnL çift-sayım (restart), C3 persist-before-verify bare-pozisyon penceresi, C4 balance-fetch yutma→$10k fabrikasyon, C5 çift+yanlış-satır trade close, C6 v2 since_ts birim uyuşmazlığı, C7 v2 CONFIRMED→order re-validation yok, C8 Gemini blocking gate+stale entry, C9 near_swing future-leak, A1 gemini-3.5-flash advisory layer inert, A2 sessiz DEBUG-only LLM hata |
| **MINOR** | 8 | sentiment stale-registry, htf_slope_pct phantom, notional-blind risk review, CustomRiskCalculator 80% cap (inert), swing_lb=5 vs docs=4, OB 1-candle invariant, except:pass triage, vb. |
| **REFUTED/SAFE** | — | breaker state restore, mainnet guard (triple), reverse-on-profit buffer, orphan mode, verdict coercion, gating advisory-only kontratı |

**Tek cümlelik kanaat:** Deterministik sermaye-koruma matematiği SAĞLAM; risk **forming-bar repaint (C1)** + **restart/degraded anlardaki sessiz state bozulmaları (C2–C5)** + **advisory katmanının sessizce ölü olması (A1)**'nda.

---

## BLOCKER

### C1 — Tüm SMC pipeline kapanmamış (forming) bar üzerinde çalışıyor
**Severity: BLOCKER** · `exchange/__init__.py:75-83` (kök), `safe_orchestrator.py:618-643`, `signals.py:347-357`, callers `bot_runner.py:418-420` / `main.py:423-425`

`BinanceClient.fetch_ohlcv` CCXT klines'ı olduğu gibi döndürür — **son satır = oluşmakta olan mum**. Hiçbir yerde `iloc[:-1]`, `barstate.isconfirmed` eşdeğeri veya "son bar kapandı mı" kapısı YOK.

```python
raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
df = pd.DataFrame(raw, columns=[...])
return df   # last row = IN-PROGRESS candle
```
- `safe_orchestrator.py:618-620`: `current_price/bar_high/bar_low = df_entry[...].iloc[-1]` (forming bar)
- `signals.py:348`: `structure()` → CHoCH `close > last_sh.price` (`smc.py:155`) forming bar close'unda — **tick içinde seviyeyi geçip geri çekilebilir** → sinyal belirip kaybolur (repaint)
- SL local-low (`low.iloc[brk.idx-20:brk.idx]`) ve ATR de tick-tick kayar

**Neden BLOCKER:** İki `run_cycle` arası, aynı 15m mum içinde LONG emit→emir→sonraki tick'te close seviyenin altına döner. **Backtest'te GÖRÜNMEZ** (`backtest/engine.py:149` her zaman kapanmış slice besler) → strateji backtest'te temiz görünür, sadece canlıda repaint eder. Spec ihlali: `PINE_SPEC.md:41-44`, `CLAUDE.md` "sadece kapanmış bar [1]".

**Fix (tek choke point):** `fetch_ohlcv`'de `tf_ms` hesapla, `now_ms - last_open_ms < tf_ms` ise son satırı düş. Exchange katmanında uygula → tüm caller (live+CLI) miras alır; backtest'e dokunma.
**Test:** 60 kapalı bar + bar[-2] close=100 (<swing 101, sinyal yok) + forming bar[-1] close=101.5 (geçer) → `generate_signals` `[]` dönmeli. Sonra barı "kapat" → sonraki cycle'da sinyal çıkmalı. İkinci fixture: wick 101.5 ama close 100.5 → sinyal yok, emir yok.

---

## MAJOR — Safety / State / Reconcile

### C2 — Breaker PnL restart'ta çift-sayım (`_reported_to_breaker` persist edilmiyor)
**Severity: MAJOR (BLOCKER-bitişik)** · `safe_orchestrator.py:778-782`, `lifecycle.py:182-210`
STEP5 TÜM pozisyonları (açık+kapalı) tarar; dedup flag'i runtime attribute, `to_full_dict`'te YOK → restart sonrası kapalı pozisyon flag'siz yüklenir → PnL ikinci kez breaker'a yazılır. Kapalı pozisyonlar `lifecycle.positions`'tan asla prune edilmiyor + restore `is_open` filtresi yok.
**Senaryo:** close→record→persist(flag düşer)→restart(autoheal/deploy/crash — incident geçmişi)→reload→STEP5 aynı pnl'i tekrar yazar. Sonuç: bir kazancın `current_balance`/`peak` şişirmesi gerçek weekly-DD HALT'ı **maskeleyebilir** = 2026-05-14 bare-pozisyon sınıfı.
**Fix:** `to_full_dict`/`from_full_dict`'e `_reported_to_breaker` ekle + STEP5 yalnız bu-process'te kapanan pozisyonları saysın (`closed_this_session` set).
**Test:** open→close→STEP5 (balance pnl kadar 1x oynar) → round-trip dict → STEP5 tekrar → `record_trade` 2. kez çağrılmamalı.

### C3 — Persist-before-verify/rollback penceresi (bare-pozisyon yolu)
**Severity: MAJOR** · `exchange/__init__.py:1121-1130`
```python
self.positions.append(pos)
self._persist()                 # <-- korumalı varsayılarak diske yazılır
verify_result = self._verify_and_repair_protection(pos)  # ≤ 2.5s×3 = 7.5s
if verify_result.get("rolled_back"): self._emit(...); return None
```
Pozisyon, SL doğrulanmadan ÖNCE diske yazılıyor. Verify penceresinde (≤7.5s) process ölürse (deploy/OOM/autoheal) disk "açık+korumalı" der ama SL hiç inmemiş olabilir. Rollback dalında re-`_persist()` görülmedi → disk geçici olarak rollback'li (market-closed) pozisyonu açık tutar; o boşlukta crash → ghost pozisyon reload.
**Fix:** persist'i verify ÇÖZÜLDÜKTEN sonra yap; rollback dalında `_persist()` çağır.
**Test:** verify `rolled_back=True` → persist edilen state dosyası pozisyonu İÇERMEMELI.

### C4 — Balance-fetch sessiz yutma → fabrike $10.000
**Severity: MAJOR** · `backend/bot_runner.py:431` + `safe_orchestrator.py:916`
```python
try: balance = self.client.get_balance()
except Exception: pass        # balance=None kalır
# safe_orchestrator: actual_balance = balance if balance is not None else 10000.0
```
Tek geçici balance hiccup → sizing & PositionGuard gerçek ~$2.000 yerine **$10.000**'e göre çalışır → `max_position_notional_pct=2.0` $200 yerine $200(of $10k)= **5× over-notional**. Ayrıca o cycle'da `breaker.sync_balance` atlanır → drawdown/emergency kontrolü tam da API titrek anında körleşir.
**Fix:** canlı cycle'da balance fetch başarısızsa o cycle yeni giriş YOK (stale gibi davran); fabrike değer kullanma.
**Test:** `get_balance` raise → o cycle `open_position` çağrısı yok, `sync_balance` fabrike değerle çağrılmıyor.

### C5 — Reconciled close: çift `record_trade_close` + trace_id'siz yanlış-satır
**Severity: MAJOR (çift)** · `bot_runner.py:565` + `:645`, `backend/db.py:121-125`
İki bağımsız DB write aynı close için: Path A `_on_position_change` fire-and-forget (`bot_runner.py:565`), Path B awaited `_persist_close` (`:645`). Üstüne `record_trade_close` satırı `symbol AND closed_at IS NULL ORDER BY opened_at DESC LIMIT 1` ile seçiyor — **trace_id var ama WHERE'de kullanılmıyor** (`db.py:110-113` yorumu kabul ediyor). Reverse-on-profit (aynı sembolde close+open) veya hızlı SL→re-entry'de iki açık satır → close EN YENİ `opened_at`'i seçer = yeni pozisyonu eski PnL ile kapatır; gerçekten kapanan satır `closed_at IS NULL` kalır → DB'de canlı pozisyon kapalı görünür, Binance'te bare.
**Fix:** trace_id varsa onunla eşle (fallback symbol); reconcile-kaynaklı close'da Path A DB write'ını bastır.
**Test:** aynı sembol 2 trace_id → `record_trade_close(trace_id=first)` → SADECE birinci satır kapanmalı; `db.record_trade_close` pozisyon başına 1x çağrılmalı.

### (latent) C-risk — CustomRiskCalculator 80% cap, leverage çift-uygulama
**Severity: MINOR (şu an inert) / MAJOR (aktive olursa)** · `engine/risk/custom_calculator.py:56-61`
`max_allowed = available_balance*0.80` PositionGuard `max_position_notional_pct=2.0`'dan ~40× kopuk; ayrıca validate yolunda leverage iki kez uygulanıyor. Şu an `position_size_calculation: legacy` olduğu için devre dışı, ama `reverse_from_risk`'e geçiş notional guard'ı sessizce 40× gevşetir.
**Fix:** cap'i aynı notional envelope'a bağla veya hesabı tamamen PositionGuard'a bırak; construct-time assertion ekle.

---

## MAJOR — SMC Correctness

### C6 — `confirm_entry` since_ts birim uyuşmazlığı → "trigger sonrası" guard ölü kod
**Severity: MAJOR** · `smc_v2/triggers.py:117`, `confirmation.py:57-61`, `safe_orchestrator.py:1329`
`trigger_bar_ts=brk.idx` (ordinal ~487) saklanıyor; confirmation onu ms-epoch (~1.7e12) ile kıyaslıyor: `if cur_ts <= since_ts` → `1.7e12 <= 487` → **asla True** → guard hiç çalışmaz. `confirm_entry` tüm 15m frame'i tarar, CHoCH'tan ÖNCE kapanmış engulfing'leri de kabul eder → geriye-bakan onay. Docstring "only AFTER the CHoCH trigger" sessizce yanlış.
**Fix:** eksenleri tutarla — trigger'ın ms timestamp'ini `since_ts` olarak geç (anchor için `brk.idx`'i ayrı tut); tip wrapper ile ordinal→ms karışmasın.
**Test:** bar 5-6 (trigger öncesi) + bar 40-41 (sonrası) engulfing; trigger bar 30 → `confirm_entry` bar-41 dönmeli, bar-6 DEĞİL.

### C7 — v2 IN_ZONE→CONFIRMED→order, canlı-fiyat re-validation yok (TOCTOU)
**Severity: MAJOR** · `safe_orchestrator.py:1320-1341`
Confirm True olan tick'te `state=CONFIRMED` + hemen `_place_v2_entry_order(entry_price=engulfing bar close)`. Engulfing bar = forming 15m bar (C1). Confirm ile borsa emri arasında fiyat re-check yok; tek backstop entry-drift guard (PR #111). C1+C6 ile birleşince CONFIRMED, kapanışta gerçek olmayan bir bar üzerinde ateşlenebilir.
**Fix:** IN_ZONE→CONFIRMED geçişini yalnız KAPANMIŞ bar[-2]'de değerlendir; emir öncesi drift guard/live-price re-read zorunlu.
**Test:** forming son bar "sahte" bullish engulfing → CONFIRMED geçişi OLMAMALI.

### C8 — Senkron Gemini çağrısı signal loop içinde: stale entry + blocking gate (advisory ihlali)
**Severity: MAJOR** · `signals.py:665-685` (çağrı), `236-237` (timeout 10s)
`validate_signal_with_gemini` per-`brk` loop İÇİNDE senkron; `entry` çağrıdan önce sabitlenir; `confidence<0.70` veya `valid=False`'da `continue` ile **sinyali düşürür** = blocking gate, advisory değil. `CLAUDE.md`/hard-rule "agents advisory only, trade mantığına dokunmaz" ihlali. Çağrı 10s'ye kadar bloklar → entry order anında stale. (Şu an A1 nedeniyle 404→no-op, ama key çalışınca canlı blocking gate olur.)
**Fix:** yapı validasyonunu post-signal advisory path'e taşı (`Signal.meta["agent_review"]` zaten var) — annotate et, bloklama; gate edecekse async/cached + emir anında live-price.
**Test:** `validate_signal_with_gemini` 5s sleep + `valid:False` → `generate_signals` sinyali yine de meta'da verdict ile dönmeli, bloklamamalı.

### C9 — `near_swing` gelecek-bar leak (confluence backtest/live divergence) + OB invariant gevşek
**Severity: MAJOR** · `smc.py:199-243`
`for s in sl if abs(s.idx - i) < 30` — `abs()` OB breakout bar `i`'ye göre **+30 bara kadar GELECEK** swing ile `near_swing=True` etiketler (forward-looking metadata → confluence +5). Canlıda gelecek swing yok → live skoru backtest'ten farklı. Ayrıca `cnt>=1` → tek-mum OB geçer; `ob_sequential:5` invariant'ı zorlanmıyor (CLAUDE.md ile çelişki).
**Fix:** `0 < i - s.idx < 30` (yalnız geçmiş swing). OB-seq floor/ceiling belirsizliğini spec'le netleştir + guard.
**Test:** OB'den 10 bar SONRA oluşan swing → `near_swing=False` olmalı (şu an True).

---

## MAJOR — Agents / Advisory Layer

### A1 — `gemini-3.5-flash` geçersiz model → TÜM advisory katmanı sessizce ölü
**Severity: CRITICAL (data integrity)** · `gemini_client.py:36`, `team.py:75`, `ai/sentiment.py:56`, `signals.py:236`, `config.yaml:222`, `backend/api.py:584`, `ops/alerter/formatter.py:73`, `main.py:247`
Google API'de `gemini-3.5-flash` YOK (geçerli: 1.5/2.0/2.5-flash). Her çağrı 404 → `raise_for_status` → `except Exception` → `{}` → `AgentVerdict(NEUTRAL, 0.0)`. **PR #112 (`aa0aeda`, 2026-06-01) merge'ünden beri advisory + sentiment + Gemini-signal-validation tamamen no-op.** `agent_disagreements.jsonl` "model çalıştı ve nötr" gibi görünen ÇÖPLE doluyor → shadow PnL korelasyonu için kullanılamaz.
**Fix:** tüm call-site'ları atomik `gemini-2.0-flash`'a çevir; `formatter.py` raw httpx → GeminiClient; `main.py`/validate_config'e model allow-list kontrolü.
**Test:** httpx 404 patch → log WARNING (DEBUG değil) emit edilmeli.

### A2 — LLM hatası yalnız DEBUG log → operatör görünürlüğü sıfır
**Severity: HIGH** · `gemini_client.py:76,80-81`
Timeout VAR (20s default — loop hang YOK, fail-safe tutuyor). Ama hata `log.debug` → INFO prod'da görünmez; dashboard `team_verdict:NEUTRAL` "model nötr düşünüyor" gibi okunur, "model kırık" değil. JSONL'de `error` alanı yok → kırık-NEUTRAL ↔ gerçek-NEUTRAL ayırt edilemez.
**Fix:** DEBUG→WARNING; N ardışık hatada tek WARNING; JSONL'e `error` alanı.

### A3 — Sentiment stale-registry freshness guard yok (restart bias)
**Severity: MEDIUM** · `ai/sentiment.py`, `safe_orchestrator.py:589`, `signals.py:436-452`
Şu an A1 nedeniyle fallback NEUTRAL → ±5 bonus = 0 (GÜVENLI). Ama `load_ai_sentiment` `last_updated` kontrol etmiyor: restart sonrası 12h eski `RISK_ON` süresiz ±5 bias enjekte edebilir (4h refresh + startup 5s pencere).
**Fix:** `load_ai_sentiment`'a yaş kontrolü (>4h15m → NEUTRAL'e dön).

### A4 — `htf_slope_pct` orchestrator'dan hiç gönderilmiyor (phantom context)
**Severity: MEDIUM** · `roles.py:115-116`, `safe_orchestrator.py:828-839`
RegimeAgent `htf_slope_pct` bekliyor (whitelist) ama orchestrator ctx'e koymuyor → `if k in ctx` sessizce düşürür. Regime context'in 1/3'ü phantom.
**Fix:** df_htf'ten slope hesapla + ctx'e ekle, veya docstring/fixture'dan kaldır.

### A5 (CONFIRMED-known) — notional-blind risk review
**Severity: MEDIUM** · `safe_orchestrator.py:838`, `roles.py:82-84,94`
`size_notional_pct=0.0` hardcoded → RiskReviewer "notional>8%→REJECT" kuralı asla ateşlemez. `risk_review_was_notional_blind=True` flag'i yazılıyor (doğrulandı). 2-pass review (F1 follow-up) doğru çözüm.

---

## REFUTED / SAFE (denetlendi, sağlam — bunlara dokunma)

- **Breaker state restore** (`breaker.py:253-296`): HALTED restart'ta korunuyor, timestamps serialize. (Prod DB-less → DB-mirror fallback inert; file StateStore tek yol — state_dir kaybı = HALT kaybı, kabul edilebilir.)
- **Mainnet guard**: triple (`main.py:183`, `guard.py:213`, `bot_runner.py:169`), zayıflatılmamış.
- **Reverse-on-profit buffer** `reverse_min_profit_pct=0.2` enforced; partial-close hard-block.
- **Orphan protector**: prod `place_missing_sl`+enabled operatör-onaylı; kod doğru guard'lı (1 SL/cycle, reduceOnly, min-distance, lifecycle'a import yok, TP koymaz); default `warn_only`.
- **Verdict coercion** (`base.py:103-119`): {}/None/garbage → NEUTRAL, clamp; crash yok.
- **Gating advisory-only kontratı** (`safe_orchestrator.py:860-873`): gating=false → veto etkisiz; gating=true REJECT yalnız EKLER, breaker/guard'ı KALDIRMAZ. Kontrat tam.
- **Swing window** (`smc.py:130-140`): simetrik, sağ-confirmed, future-leak yok (C1 hariç).
- **smc_v2 setup_state/swing_anchor/zones/tp_calc/sl_calc**: tek-yön geçiş, atomic write, future-structure anchor yok.

---

## 6. Production risk envelope — matematik tutarlılığı (risk-safety-auditor)

Girdi (`config.phase2_1k.yaml`): balance=2000, leverage=5, ISOLATED, risk_per_trade=1.0%, max_open=10, max_notional_pct=2.0, max_total_exposure=1.0x, daily=10%, weekly_dd=25%, emergency=1800.

1. **Per-trade notional:** sizer $200 notional = guard $40 margin ($200/5). ✔ Tutarlı — ama tesadüfen (ikisi de 2% & 5×'e bağlı); leverage değişip notional_pct sabit kalırsa diverge eder. **Kırılgan ama şu an doğru.**
2. **10×$200 = $2.000 notional = tam 1.0× exposure.** ✔ İki cap aynı noktada bağlar. Toplam margin $400 (cüzdanın %20'si).
3. **1% risk × 10 = $200 = %10 daily limit = emergency ($2000−$200=$1800).** ✔ Üçlü hizalı — tam stop-out kitabı breaker'ı tam limitinde tetikler. **Temiz.**
4. ⚠️ **Advertised 1% vs enforced 5%:** PositionGuard hard cap `risk_pct>5%→reject` (`position_guard.py:318`); tight SL'de notional cap bağlarsa gerçek risk 1%'i aşabilir, tavan 5%. 10×5%=%50/gün ama daily(10%)+emergency önce keser → defense-in-depth tutarlı, yine de operatör notu.
5. ⚠️ **`max_sl_atr=5.0` ≥ ISOLATED-5× likidasyon mesafesi (~19%):** yüksek-ATR sembolde 5×ATR=20% SL → SL tetiklenmeden likidasyon; guard yalnız WARN (`position_guard.py:309-313`), reject değil. **Tek gerçek cap çelişkisi.** Fix: SL mesafesi ≥ likidasyon mesafesi ise reject.

**Matematik kanaati:** Dört başlık cap ($200 notional / 1.0× / %10 daily / $1800 emergency) $200/$2000 sınırında üçlü hizalı — etkileyici tutarlı. İki yumuşak nokta: (a) 1%-advertised vs 5%-enforced, (b) max_sl_atr=5.0 likidasyonu aşabilir (warn→reject olmalı).

---

## 7. Test integrity / CI hermeticity / config drift / prod-vs-CLI

> Kaynak: general-purpose subagent (background resume sonrası). İYİ HABER: test suite kalitesi **tipik üstü** — çoğu spy testi gerçek arg/effect doğruluyor; gerçek fake-handoff/stub-success YOK (kod kendi inert path'leri hakkında dürüst).

### 7.1 Test fakeness (genel kalite YÜKSEK)
- **T1 (MINOR)** `test_breaker_db_mirror.py:96,110-112`: `assert True in args` / `False in args` / `None in args` — pozisyonel-kör; `halted`↔`auto_resume` kolon swap'i hâlâ geçer. Tek gerçek hollow assertion. Fix: index/isimle bağla (`args[IDX_HALTED] is True`).
- T2-T4 (MINOR): bare `.called` satırları ama hemen ardından derin snapshot assertion'lar var → test'in kendisi güçlü, satır gereksiz.
- **GÜÇLÜ kapsama (dokunma):** `test_tp_order_reliability.py` (gerçek OrderManager, TP1-fail→TP2-continue, retry backoff, repair stopPrice), `test_reconcile_algo_orders_visibility.py` (2026-05-09 algo-order bug pin), `test_healthz.py` (200-vs-503 kontrat), `test_cli_reconcile_parity.py` (`_reported_to_breaker` dedup, `assert_called_once_with(logical,2000.0,"TP1")`), `test_safe_orchestrator_client_attr.py`.

### 7.2 CI hermeticity excludes — H1 / H2 spec'leri
Tam exclude satırları: **`.github/workflows/ci.yml:85-86`**:
```yaml
--ignore=backend/tests/test_binance_client_url_routing.py            # H1
--deselect "tests/test_alerter_heartbeat.py::test_heartbeat_writes_alerter_heartbeat_ts_to_json_file"   # H2
```
CI yorumu (ci.yml:60-77): ikisi de **pre-existing non-hermetic**, agent-team ile ilgisiz, "lokalde environment varsayımı maskelediği için geçiyordu". pytest.ini/pyproject deselect YOK — sadece CLI flag, yani lokalde ÇALIŞIR+düşebilir.

**H1 SPEC (MAJOR) — `test_binance_client_url_routing.py` (geo-451):**
Root cause `test:16-21`: `shared_markets` fixture `ccxt.binance(...).load_markets()` → CANLI HTTP `api.binance.com/exchangeInfo` → GitHub US runner **HTTP 451**. Test sadece markets metadata'ya ihtiyaç duyar (FIL/USDT vs FIL/USDT:USDT fapi-vs-spot URL sınıflandırması); `_capture_fetch_open_orders_url` zaten gerçek HTTP'den önce intercept ediyor.
> Bu, memory `binance_ccxt_conditional_orders.md`'deki FIL/USDT defaultType spot-vs-fapi bug'ının regression guard'ı — CI'da kapalı = MAJOR.

Blind fix:
1. Statik markets fixture'ı bir kez lokalde yakala → `backend/tests/fixtures/binance_markets.json`'a vendor et (FIL/USDT + FIL/USDT:USDT + gerekli base metadata; küçük tut).
2. `shared_markets`'i JSON yükleyecek şekilde değiştir, `boot.markets/markets_by_id/symbols/ids` attr'larını set et — **network YOK**. (`_client_with_markets` zaten bu 4 attr'ı enjekte ediyor.)
3. Assertion'lar aynı kalır (fapi `/fapi/v1/openOrders` var, spot `/api/v3/openOrders` yok, `symbol=FILUSDT`).
4. `ci.yml:85`'ten `--ignore=...` kaldır. **Kabul:** internetsiz runner'da geçer.

**H2 SPEC (MAJOR) — `test_alerter_heartbeat.py::...heartbeat...` (`/app` path):**
Test DOSYASI zaten düzeltilmiş (`tmp_path` + `mock.patch("ops.alerter.alerter.HEARTBEAT_FILE", ...)`). Offending = prod modülündeki `HEARTBEAT_FILE` hardcode (`/app/state/...`); muhtemelen `__init__` veya import-time'da dizini resolve/create ediyor → patch öncesi `/app` dokunur → bare runner'da `PermissionError`.
Blind fix:
1. `ops/alerter/alerter.py`'de `HEARTBEAT_FILE = "..."` bul.
2. Env-config + relative default, **call-time resolve**:
   ```python
   HEARTBEAT_FILE = os.environ.get("EFLOUD_ALERTER_HEARTBEAT_FILE",
       os.path.join(os.environ.get("EFLOUD_STATE_DIR","./state"), "alerter_heartbeat.json"))
   ```
3. `_write_heartbeat`'te path'i taze oku + `path.parent.mkdir(parents=True, exist_ok=True)`; `__init__` `/app/state` yaratmasın.
4. `ci.yml:86`'dan `--deselect` kaldır. **Kabul:** non-root, `/app`'siz box'ta geçer.

### 7.3 Config drift / dead config
- **F3.6 (MAJOR)** — `preflight.py:105` + `backend/bot_runner.py:33` default `configs/config.phase2_micro.yaml`'a işaret ediyor ama dosya **orada YOK** (arşivde: `configs/archive/config.phase2_micro.yaml`). `EFLOUD_CONFIG_PATH` set değilse: preflight `except:pass`→`starting_balance=100` yanlış banda; `bot_runner.start()` "Config not found"→başlamayı reddeder (fail-safe ama sessiz landmine). Fix: ikisini de `configs/config.phase2_1k.yaml`'a (veya arşiv tam yoluna) hizala.
- **F3.2 (MAJOR)** — `configs/config.aggressive_v1.yaml` = **CROSSED + hedge_mode:true**, `dry_run:false`/`testnet:false`. PR A doktrini (ISOLATED+one-way) ile çelişir; memory `binance_isolated_hedge_off_autoflip.md`'deki FIL auto-flip incident config'i. `EFLOUD_CONFIG_PATH` buna işaret ederse PR A güvenlik duruşunu sessizce geri alır. Fix: ARŞIV/DO-NOT-DEPLOY banner veya `configs/archive/`'a taşı.
- **F3.1 (MAJOR)** — kök `config.yaml` divergent near-dead: `swing_lookback:4` (diğer hepsi 5), `smc_version:v1`, `starting_balance:10000`, `weekly_dd:8%`, `risk:2.0`. `python main.py` (argsız) bunu alır. Fix: sil veya testnet/dry_run template'e indir + swing_lookback→5.
- **F3.5 (MINOR)** — `sizing_balance_source` yalnız aggressive_v1'de set; prod default `"total"` (unrealized dahil), aggressive `"available"` → iki live config arası sessiz davranış farkı.
- **F3.3/3.4 (MINOR)** — `agent_team.min_team_score` ölü (0 okuyucu, kaldırma notu var); `post_mortem.schedule` YAML'da inert (sadece API query-param). Diğer şüpheli key'ler (`body_mode`, `eq_threshold_pct`, `adx_*`, `volatile_atr_mult`, `max_pyramid_adds`, `dynamic_top_n`, `sl_atr_buffer`...) hepsi CANLI okunuyor.

### 7.4 Prod (bot_runner) vs CLI (main.py) divergence
- **F4.1 (MAJOR)** — Margin-mode başarısızlığı: prod FATAL (`bot_runner.py:36-69` `_enforce_margin_setup`→startup ABORT), CLI **swallowed warning** (`main.py:628-633` `except: log.warning`, devam eder). **ISOLATED garantisi sadece prod yolunda.** Fix: ortak helper'a çıkar, CLI de abort etsin.
- **F4.3 (MAJOR)** — DB writes / equity snapshot / AuditEngine: **PROD ONLY**. CLI'da 0 `db.*` çağrısı.
- **F4.4 (MAJOR)** — Crash-loop guard / RuntimeState / healthz: **PROD ONLY**. CLI'da hiç yok.
- **F4.5 (MAJOR)** — Telegram bildirim + breaker DB-mirror HALT fallback (2026-05-15 VPS-rebuild guard): **PROD ONLY**.
- **F4.2 (MINOR)** — margin vs position-mode setup sıralaması farklı + failure semantics tutarsız (prod structured (ok,err), CLI `sys.exit(1)`/swallow).
- **PARITE DOĞRULANDI (iyi):** `_build_setup_state_store` v2 wiring artık HER İKİSİNDE (bot_runner `from main import` ediyor — eski prod-only hotfix çözülmüş); reconcile→breaker dedup byte-eşdeğer; `resolve_timeframes`/`validate_config`/`MainnetGuard`/PR-B/PR-C wiring her iki yolda.

### 7.5 Re-fabrication / fake-handoff taraması — TEMİZ
- **F5.1 RESOLVED** — `safe_orchestrator.py:1247` eski "placeholder returning (False,None)" artık gerçek `smc_v2.confirmation.confirm_entry` proxy'si; `test_orchestrator_confirm_wiring.py` gerçek engulfing kanıtlıyor. Yorum dürüst tarih.
- **F5.4 INFO** — Gerçek "TODO says done" / kritik-path `return True` stub YOK. `guard.py:206 return True # Testnet her zaman güvenli` gerçek guard mantığı. `main.py:483 sync_orders` ölü ama açıkça disabled + gerekçeli ("duplicate SL/TP yarattı"), sessiz stub değil.
- **Kanaat:** Bu oturumda korkulan "defer-commit/sahte handoff" sınıfı kodda YOK. Tek "yalan" doc-vs-code çelişkisi: A1 (`gemini-3.5-flash` 6 yerde hardcoded ama docstring 1.5/2.0 diyor) — bu da fabrikasyon değil, model-pin hatası.

---

## Ranked — ilk 5 (canlı-sermaye riskine göre, tüm kategoriler)

1. **C1 (BLOCKER)** — forming-bar repaint, backtest'te görünmez, tek-nokta fix.
2. **C2 (MAJOR)** — breaker PnL restart çift-sayım → weekly-DD HALT maskeleme = bare-pozisyon sınıfı.
3. **C3 (MAJOR)** — persist-before-verify penceresi → restart'ta "korumalı sanılan bare" pozisyon.
4. **A1 (CRITICAL/data)** — advisory katmanı sessizce ölü; shadow verisi çöp; gating prerequisite'i sıfırlandı.
5. **C4 + C5 (MAJOR)** — balance-yutma $10k fabrikasyon + çift/yanlış-satır trade close (journal/PnL/operatör görünürlüğü bozulması).
