# Entry-Slippage Fix - Gemini Hand-off (ultracode review)

> 2026-06-08. Claude (Opus 4.8) ultracode multi-agent review (4 mapper + 3 critic + 1 synth) of
> Gemini's uncommitted async-AgentTeam-review + zone-touch-entry draft.
> Source plan: .gemini/antigravity-ide/brain/460adf75-.../implementation_plan.md

---

## Yonetici Ozeti (TR)

Gemini'nin taslağının yönü kısmen doğru ama mevcut haliyle MERGE EDİLEMEZ. İyi parçalar: AgentTeam review'ını bloklayan pre-trade yolundan post-entry daemon thread'e taşımak (gerçek latency kazancı, gating zaten prod'da kapalıydı), TradeJournal'a RLock + update_agent_review eklemek, ve require_confirmation bayrağı fikri. Ancak dört doğrulanmış kusur var. (1) KRİTİK: sticky IN_ZONE dalı (safe_orchestrator.py:1527-1535) require_confirmation=false iken is_price_in_zone yeniden kontrolü YAPMADAN current_price'ta giriyor; fiyat bölgeyi terk etmişse bile giriyor (test 95500'de giriyor, bölge [96000,97000]) ve entry=current_price olduğu için entry-drift guard yapısal olarak reddedemiyor — bu, kapatılmak istenen entry-vs-zone boşluğunu BÜYÜTÜYOR. SL/TP hâlâ bölgeye sabitli olduğundan R:R bozuluyor. (2) YÜKSEK: V2 canlı yolda _run_agent_review_async ana thread'de float(pos.avg_entry_price) ve pos.id okuyor; OrderManager.open_position EXCHANGE Position döndürüyor (.entry/.order_id var, .avg_entry_price/.id YOK) → ana cycle thread'inde AttributeError. Bugün sadece phase2_1k'da smc_v2_shadow:true olduğu için maskeli; shadow kapanınca patlar. (3) YÜKSEK: require_confirmation hem config.yaml hem live phase2_1k'da false yapılmış — CLAUDE.md'nin PR+testnet-önce kuralını çiğniyor; commit edilen şablonda güvenli varsayılan (true) kalmalı. (4) ORTA: telemetri YOK — slippage exchange/__init__.py:1092'de hesaplanıp atılıyor, lifecycle Position sinyal fiyatıyla açılıyor, journal'da slippage alanı yok; yani düzeltme ÖLÇÜLEMEZ ve muhtemel baskın sebep (market-order spread/impact) hiç ele alınmıyor. Ek: sınırsız thread fan-out (Kronos audit'inin düzelttiği OOM sınıfı), her girişte O(n) journal yeniden-yazımı, gating yeteneğinin sessizce silinmesi (if False: pass) ve risk_review_was_notional_blind veri-kontratının kaybı. Tavsiye: ÖNCE telemetri-only PR, sonra ölç, sonra davranış değişikliği — ve require_confirmation canlıya yalnızca backtest geçişi + testnet/shadow + operatör onayı ile.

## Dogrulanmis Kok Nedenler

- BLOKLAYAN PRE-TRADE LLM LATANSI (V1 için gerçek): run_cycle V1 dalı, market emrinden ÖNCE AgentTeam.review_trade'i SENKRON çalıştırıyordu — engine/agents/team.py:109-117'de 4 ardışık senkron httpx LLM çağrısı, her biri 30s timeout (minimax_client.py:52), MiniMax reasoning ~5-19s/çağrı → pre-trade yola onlarca saniye eklenebilir. enabled:true (config.yaml:220) olduğu için takım gating:false olsa bile her sinyalde çalışıyordu. Gemini'nin async'e taşıması bu latansı kaldırır (gerçek kazanç).
- MARKET-ORDER SLIPPAGE (muhtemelen BASKIN, taslakta hiç ele alınmıyor): girişler MARKET emri (exchange/__init__.py:1072 create_order 'market'). Latans sıfır olsa bile yarı-spread + market impact ödenir; 10 sembollük (bazıları az likit) evrende muhtemel ana katkı. slip_pct exchange/__init__.py:1092'de HESAPLANIYOR ama sadece loglanıp atılıyor.
- SİNYAL-vs-FILL DRIFT + KAYIT UYUMSUZLUĞU: lifecycle Position SİNYAL fiyatıyla (latest.entry, safe_orchestrator.py:1289) açılıyor, exchange Position ise gerçek fill (actual_entry, exchange/__init__.py:1197) ile; journal lifecycle'ı okuduğu için ölçülmek istenen sapma kayda hiç girmiyor. Kapanmış 15m barda hesaplanan sinyal ile sonraki canlı fill arasında doğal drift var; entry-drift guard bunu yalnızca SINIRLAR, iyileştirmez.
- V2 CONFIRMATION/CANDLE-CLOSE BEKLEMESİ (yalnızca V2 yolu, bugün dormant/shadow): IN_ZONE iken confirm_entry 15m engulfing kapanışı bekliyor (confirmation.py:59-84). Bu gecikme gerçek ama yalnızca V2'yi etkiliyor ve commit edilen iki config'de de inert (config.yaml=v1; phase2_1k=v2 ama smc_v2_shadow:true → _place_v2_entry_order shadow gate'te None döner, satır 1807-1814). Yani contributor (b) şu an canlıyı etkileyemiyor.

## Bloklayici Sorunlar

### [CRITICAL] Sticky IN_ZONE dalı, require_confirmation=false iken is_price_in_zone(current_price, cand.target_zone) YENİDEN kontrolü olmadan CONFIRMED'e geçip _place_v2_entry_order(entry_price=current_price) çağırıyor. Bir aday IN_ZONE olduktan sonra fiyat bölgeyi terk etse bile bir sonraki tick'te bölge DIŞI current_price'ta giriyor. entry=current_price olduğundan entry-drift guard (|live-entry|/entry≈0) yapısal olarak reddedemez. SL/TP hâlâ bölgeye sabitli (calc_sl satır 1680, calc_tp_targets 1697) → R:R sessizce bozuluyor. Bu, görevin amacının TAM TERSİ: entry-vs-zone boşluğunu büyütür.
- **FIX:** Not-require_confirmation IN_ZONE dalında, CONFIRMED'e geçmeden önce is_price_in_zone(current_price, cand.target_zone) ile gate'le; fiyat bölge dışındaysa aday IN_ZONE kalsın (timeout'ta EXPIRE etsin), GİRME. Tercihen entry_price'ı en yakın bölge kenarına clamp et (LONG: min(max(current_price, zone.low), zone.high); SHORT ayna). AWAITING_PULLBACK dalı (satır 1516) zaten is_price_in_zone ile gate'li, dokunma.
- **LOC:** engine/safe_orchestrator.py:1527-1535

### [CRITICAL] test_sticky_in_zone_advances_directly_on_require_confirmation_false bölge-dışı giriş hatasını 'beklenen davranış' olarak sabitliyor: target_zone=[96000,97000], current_price=95500 (bölgenin ALTINDA), assert state==CONFIRMED ve entry_price=95500. Bu test yukarıdaki düzeltmeyi AKTİF olarak bloklar.
- **FIX:** Testi yeniden yaz: IN_ZONE adayı fiyat bölge DIŞINDAYKEN CONFIRMED OLMAMALI ve mock_place.assert_not_called() olmalı; ayrı bir case fiyat bölge İÇİNE döndüğünde girişi doğrulasın. test_immediate_entry_on_zone_touch_when_require_confirmation_false (bölge içi, satır 48-74) geçerli, korunur.
- **LOC:** tests/engine/test_zone_touch_entry.py:100-125

### [HIGH] V2 CANLI yolda (_place_v2_entry_order, order_manager set) pos = self.order_manager.open_position(...) EXCHANGE Position döndürür (alanları: .entry, .order_id — exchange/__init__.py:332-360). Ardından satır 1856 _run_agent_review_async(pos=pos) çağırır; bu metot ana thread'de (thread.start()'tan ÖNCE) satır 551'de float(pos.avg_entry_price) ve task() içinde pos.id (satır 564,571) okur. Exchange Position'da .avg_entry_price ve .id YOK → ana cycle thread'inde AttributeError. _advance_setup_state_tick run_cycle:840'tan try/except'siz çağrıldığı için cycle'a sızar. Bugün yalnızca phase2_1k smc_v2_shadow:true (satır 1814 None döner) olduğu için maskeli; shadow kapanınca ilk canlı v2 girişinde patlar. V1 ve V2-paper yolları lifecycle Position (id + avg_entry_price var) kullandığı için güvenli.
- **FIX:** _run_agent_review_async'te fill fiyatını savunmacı oku: getattr(pos, 'avg_entry_price', None) or getattr(pos, 'entry', None); trade_id için getattr(pos, 'id', None) or getattr(pos, 'order_id', None). Tüm ctx-build + thread.start()'ı try/except ile sar ki advisory katman deterministik giriş yoluna ASLA exception atmasın. _place_v2_entry_order'ın canlı dalını (order_manager mocklu, shadow off) sürerek hiçbir exception'ın kaçmadığını doğrulayan test ekle.
- **LOC:** engine/safe_orchestrator.py:543-561 (ctx build), 564/571 (pos.id), 1856-1864 (v2 call site); exchange/__init__.py:332-360

### [HIGH] require_confirmation hem config.yaml:38 hem canlı configs/config.phase2_1k.yaml'da true→false yapılmış. Bu, deterministik giriş-zamanlaması yolunu değiştiren bir davranış değişikliği (sadece additive-advisory değil); CLAUDE.md/AGENTS.md ve feedback_live_bot_change_workflow PR+testnet-önce kuralını çiğniyor. Kod varsayılanı true (satır 1493) ve PINE_SPEC §9 varsayılanı true; commit edilen şablonda güvenli varsayılan korunmalı.
- **FIX:** İKİ commit edilen config'de de require_confirmation: true'ya geri al (veya satırı kaldır). Deneyi yalnızca testnet/shadow config üzerinden sür. Canlı flip için backtest kanıtı (fill-vs-zone mesafe iyileşmesi) + smc_v2_shadow=true testnet aşaması + operatör/Hermes onayı ZORUNLU. config.yaml:38'deki yanıltıcı yorum da düzeltilmeli.
- **LOC:** config.yaml:38; configs/config.phase2_1k.yaml (yeni smc_v2 bloğu)

### [MEDIUM] Slippage'ı ölçecek HİÇBİR telemetri kalıcı değil. slip_pct exchange/__init__.py:1092'de hesaplanıp log satırında atılıyor; lifecycle Position SİNYAL fiyatıyla açılıyor (safe_orchestrator.py:1289), journal onu okuyor; TradeSnapshot'ta (journal.py:34) slippage/signal-vs-fill/ts_signal/ts_fill alanı yok. Sonuç: değişikliğin işe yarayıp yaramadığı ÖLÇÜLEMEZ ve baskın katkı (market-order slippage) ele alınmıyor.
- **FIX:** TradeSnapshot'a alanlar ekle: signal_entry_price, actual_fill_price, slippage_pct (yön-işaretli: + = aleyhte), zone_mid, ts_signal, ts_fill, latency_ms. OrderManager.open_position zaten actual_entry hesaplıyor (exchange/__init__.py:1091) — onu Position.entry üzerinden journal'a kadar taşı; lifecycle Position'a signal_entry'yi ayrıca geçir. Bunu BAĞIMSIZ ilk PR olarak gönder, davranış değişikliğinden önce baseline topla.
- **LOC:** exchange/__init__.py:1090-1096; engine/safe_orchestrator.py:1288-1290; engine/journal.py:34-35

### [MEDIUM] _run_agent_review_async her açılan pozisyon için ham threading.Thread(daemon=True) spawn ediyor (satır 575) — pool/semaphore/in-flight cap/dedup yok. Her thread 4 ardışık 30s-timeout LLM çağrısı (~120s) çalıştırıyor. max_open_positions 20'ye kadar; bir rejim-değişim burst'ünde ~20 thread x 4 = ~80 eşzamanlı LLM isteği → MiniMax rate-limit + OOM/socket birikmesi. Bu, Kronos audit'inin bounded-executor ile düzelttiği tam fan-out sınıfı (o hardening engine/ai/'de, engine/agents/team.py'de YOK). Ayrıca team.py:172-192 _log_disagreement kilitsiz 'a' modunda append ediyor, artık eşzamanlı thread'lerden çağrılıyor.
- **FIX:** Orchestrator'da tek paylaşımlı concurrent.futures.ThreadPoolExecutor(max_workers=1-2) (veya Semaphore) kullan; review'lar kuyruğa girsin. trade_id başına in-flight dedup ekle. _log_disagreement ve AgentTeam._history'yi kilitle. Shutdown'da kısa timeout'lu drain ekle VEYA verdict'in 'best-effort, restart'ta None kalabilir' kontratını açıkça dokümante et.
- **LOC:** engine/safe_orchestrator.py:562-575; engine/agents/team.py:172-192; engine/agents/minimax_client.py:52

### [MEDIUM] record_entry artık her girişte O(n) tam-dosya yeniden-yazımı yapıyor (journal.py:130-158 upsert+persist, _persist 242-247 tüm _cache'i open('w') ile yeniden yazar) — latency-hassas cycle thread'inde. Journal rotasyonu/cap'i yok; ömür boyu trade sayısıyla maliyet monoton büyür ve arka plan review thread'lerinin update_agent_review _persist'iyle aynı RLock için yarışır. 'latency azalt' amacını kısmen kendi kendine baltalıyor.
- **FIX:** Ya append-on-exit modelini koru ve yalnızca dayanıklılık gereken alanları anında persist et, ya da journal rotasyonu/cap ekle. En azından canlı journal boyutunda per-cycle _persist maliyetini benchmark et. Upsert'in kendisi doğru (trade_id ile eşleşir, mükerrer satır yok) — korunur.
- **LOC:** engine/journal.py:133-158, 242-247

### [MEDIUM] Pre-trade gating bloğu tamamen silinip `_agent_veto = False; if False: pass` ile değiştirilmiş (satır 1053-1058). Bu, gating yeteneğini KALDIRIYOR (gating=true ayarlayan operatör artık veto alamaz; prod'da gating:false olduğundan canlı etki düşük ama yetenek gitti) ve latest.meta['risk_review_was_notional_blind']'ın tek yazıcısını siliyor (grep ile başka yazıcı yok) → bu alanı okuyan warehouse/post-mortem tüketicileri artık hep absent görür. V1 journal satırı da artık girişte hep agent_review=None kaydediyor.
- **FIX:** gating'i config-tabanlı opsiyonel senkron dal olarak koru (cfg['gating'] oku, true ise async-review'dan önce senkron review+veto; default false), VEYA kaldırımı PR'da açıkça dokümante edip risk_review_was_notional_blind veri-kontratını migrate et ve operatör onayı al. `if False: pass` ölü kodunu temiz silme ile değiştir.
- **LOC:** engine/safe_orchestrator.py:1051-1060, 1295-1300

### [LOW] pullback_timeout_bars = smc_v2_cfg.get('pullback_timeout_bars', pullback_timeout_bars) (satır 1494) fonksiyon parametresini kendisiyle yeniden bağlıyor. Param default 8, run_cycle çağırıcısı (satır 840) argümanı geçmiyor, yani config 8 == default 8 (bugün zararsız). Ama config'in gelecekteki herhangi bir explicit call-site argümanını sessizce ezmesine yol açar. NameError/logic bug DEĞİL.
- **FIX:** Ayrı bir yerel isme ata: effective_pullback_timeout_bars = smc_v2_cfg.get('pullback_timeout_bars', pullback_timeout_bars) ve aşağıda onu kullan. Fonksiyonel zorunluluk yok, okunabilirlik.
- **LOC:** engine/safe_orchestrator.py:1494

### [LOW] V2 async review df_htf=None ve adx=0.0 ile çağrılıyor (satır 1860-1861) → htf_slope_pct=0.0 ve adx=0.0 RegimeAgent'e ulaşıyor; V2 verdict'i V1'den düşük fidelity. Advisory-only, trade etkisi yok.
- **FIX:** İsteğe bağlı: gerçek df_htf/adx'i _place_v2_entry_order'a thread'le, ya da V2 verdict'lerinin kısmi context kullandığını dokümante et.
- **LOC:** engine/safe_orchestrator.py:1856-1864

---

# Improved & Extended Plan — Entry-zone-vs-fill slippage reduction (efloud-bot)

## Guiding principle: MEASURE FIRST, then change behavior, behind testnet/shadow.
The current draft changes live entry-timing behavior before establishing a baseline and ships an unverifiable, partially-counterproductive change. Re-sequence into 4 phases. Each phase is an atomic PR, TDD-first, with the full engine suite green before merge.

---

## Phase 0 — Slippage & latency TELEMETRY (standalone PR, ships FIRST, no behavior change)
The single most important missing piece: the gap cannot be reduced or even verified without persisting it.

1. Add fields to `TradeSnapshot` (engine/journal.py:25-99):
   - `signal_entry_price: float = 0.0` — the intended SMC entry (closed-bar break/zone-clamp price).
   - `actual_fill_price: float = 0.0` — exchange fill (`order['average']`).
   - `slippage_pct: float = 0.0` — direction-signed: LONG `(fill-signal)/signal*100`, SHORT `(signal-fill)/signal*100`; `+` = adverse.
   - `zone_mid: float = 0.0` — v1: OB/OTE clamp target; v2: `(target_zone.low+high)/2`.
   - `ts_signal: Optional[str] = None`, `ts_fill: Optional[str] = None`, `latency_ms: float = 0.0`.
2. Plumb the fill out of `OrderManager.open_position`: `actual_entry` already exists (exchange/__init__.py:1091) and the exchange `Position.entry = actual_entry` (1197). Surface `actual_entry` AND the signal entry to the journal. In safe_orchestrator.py:1288-1290, keep opening the lifecycle Position as today (cost-basis math depends on it), but pass `signal_entry` and `actual_fill` (read from `exchange_pos.entry`) separately into `_journal_record_entry`.
3. `record_entry` already upserts+persists (keep — but see Phase 3 latency note). Persist the new fields.
4. EXCLUDE pyramiding adds from the slippage metric — `lifecycle.add_to_position` legitimately shifts avg_entry; slippage is computed only on the FIRST entry per trade_id.
5. TDD: test that a known signal+fill pair yields the correct signed `slippage_pct` and `latency_ms`.
6. Deploy telemetry-only to live/testnet; collect 3-5 days; compute mean/median `slippage_pct` and `latency_ms` per symbol. This baseline DECIDES which lever (async-LLM, confirmation-bypass, or limit-order) actually matters.

---

## Phase 1 — Async post-entry AgentTeam review (keep Gemini's good idea, harden it)
Keep: moving review off the blocking pre-trade path; RLock journal; `update_agent_review`. FIX the defects.

1. **Bounded concurrency (mandatory).** Replace the raw `threading.Thread(daemon=True)` per entry (safe_orchestrator.py:575) with a SINGLE shared `concurrent.futures.ThreadPoolExecutor(max_workers=2)` created in `__init__` (mirror the Kronos hardening in engine/ai/). Reviews QUEUE instead of fanning out. Add a per-`trade_id` in-flight set (guarded by a lock) so duplicate submissions for the same trade are deduped.
2. **Defensive attribute reads (fixes the HIGH AttributeError).** In `_run_agent_review_async`, read `entry = getattr(pos, 'avg_entry_price', None) or getattr(pos, 'entry', None)` and `trade_id = getattr(pos, 'id', None) or getattr(pos, 'order_id', None)`. Wrap the ENTIRE ctx-build + submit in `try/except` so the advisory layer can NEVER raise into the deterministic entry path. (Exchange Position has `.entry`/`.order_id`; lifecycle Position has `.avg_entry_price`/`.id`.)
3. **Thread-safe AgentTeam sinks.** Add a lock around `AgentTeam._log_disagreement` (team.py:172-192) and `AgentTeam._history` append — both now run from multiple worker threads.
4. **Preserve an OPTIONAL gate (do not hard-delete the veto).** Do NOT leave `if False: pass`. Instead: if `agent_team.cfg.get('gating', False)` is True, run the review SYNCHRONOUSLY pre-trade and veto on REJECT (the old behavior, default-off); otherwise run it ASYNC post-entry. This keeps the documented safety lever configurable while defaulting to the latency win.
5. **Data-contract continuity.** Keep writing `risk_review_was_notional_blind` (in the sync gating branch) and document that on the async path it is N/A. Audit `scripts/bigquery_archive.py` / warehouse consumers for `agent_review`-at-entry and migrate if needed.
6. **Shutdown contract.** Either drain the executor with a short timeout on orchestrator shutdown, OR explicitly document verdicts as best-effort (may stay None after a container restart — acceptable for advisory-only).
7. TDD: (a) async path is non-blocking (<50ms) and updates journal; (b) LIVE v2 path (order_manager mocked, shadow off) raises NO exception out of `_place_v2_entry_order` even with an exchange Position; (c) gating=true → synchronous veto still blocks; (d) concurrency cap respected under a burst.

---

## Phase 2 — `require_confirmation` flag: CORRECT the entry logic, keep default safe
1. **Fix the sticky IN_ZONE bug (CRITICAL).** In the not-`require_confirmation` IN_ZONE branch (safe_orchestrator.py:1527-1535), gate on `is_price_in_zone(current_price, cand.target_zone)` before CONFIRMED. If price has left the zone: leave the candidate IN_ZONE (let it EXPIRE on timeout) — do NOT enter at an off-zone price. **Clamp** the entry to the nearest favorable zone edge so `entry ∈ zone` holds by construction (LONG: `min(max(current_price, zone.low), zone.high)`; SHORT mirror). This keeps SL/TP (anchored to zone) coherent and R:R intact.
2. **Rewrite the bad test** (tests/engine/test_zone_touch_entry.py:100-125): assert an IN_ZONE candidate with price OUTSIDE the zone does NOT confirm/enter (`mock_place.assert_not_called()`); add a case where price returns into the zone and entry fires at the clamped price.
3. **Config-default policy.** Keep `require_confirmation: true` in BOTH committed templates (config.yaml + configs/config.phase2_1k.yaml). The flag is config-driven (code default true at :1493). Drive the experiment ONLY via a separate testnet/shadow config. Fix the misleading inline comment.
4. **pullback_timeout_bars** (safe_orchestrator.py:1494): rename to `effective_pullback_timeout_bars` to avoid in-place parameter rebind (cosmetic, low priority).
5. **PINE_SPEC parity.** If/when the flip is approved, update PINE_SPEC.md §9 default + §0/§4 contract and re-sync the Pine indicator+strategy in the SAME change. Until then, spec stays `requireConfirmation: true`.

---

## Phase 3 — The real slippage lever (decide AFTER Phase 0 baseline)
If Phase-0 data shows market-order spread/impact dominates (likely on the 10-symbol universe), latency removal alone won't help. Evaluate, against the SAME backtest gates:
1. **Marketable-limit at zone edge** with a `max_entry_drift_pct` cap: limit price = signal ± max_entry_drift_pct. Guarantees a bounded worst-case fill, rejects catastrophic slippage, and makes `entry == zone edge` by construction. Trade-off: miss-risk → use a TTL (= `pullback_timeout_bars`) then optional market fallback.
2. If immediate-on-touch is wanted but full engulfing is too slow, prefer a WEAKER-but-structural gate (wick-rejection close back inside zone, or 1m/5m micro-engulfing) over NO confirmation — preserves the "zone held" proof the confluence score assumes.
3. Journal latency note: if Phase-0 benchmark shows per-cycle `_persist` O(n) cost is material at live journal size, add journal rotation/cap or revert to append-on-exit for non-durable fields.

---

## Phase 4 — Backtest gate + live rollout (MANDATORY before any mainnet flip)
1. Run `backtest/evaluate_backtest_gates.py` WITH confirmation (baseline) vs WITHOUT on the SAME universe/window. Report: win_rate, profit_factor, expectancy (R), Sharpe, max_drawdown, trade_count, AND mean/median signal-vs-fill `slippage_pct` (now persisted). The flag may go live ONLY if expectancy/PF/Sharpe are not materially worse.
2. Rollout order per CLAUDE.md/AGENTS.md live-change rules: PR → testnet (`smc_v2_shadow=true`) → operator/Hermes sign-off → live flip as a SEPARATE, explicitly-gated commit. Never bundle the config flip with code.

## DO-NOT-TOUCH (deterministic pipeline integrity)
- breaker / pos_guard / orphan-protection / lifecycle cost-basis / entry-drift guard logic: unchanged.
- engine/agents/* stays ADDITIVE advisory; it must never raise into or block the deterministic entry path.
- No live mainnet config change without PR + testnet first.

---

# === GEMINI ICIN GOREV + TALIMAT PROMPT (kopyala-yapistir) ===

# Gemini: FINISH & FIX the slippage / async-review work. Follow these instructions exactly.

You previously made uncommitted changes to make AgentTeam review async post-entry and to add `smc_v2.require_confirmation`. A multi-reviewer audit (4 mappers + 3 critics, verified against the code) found CRITICAL and HIGH bugs. Your task: fix every item below, TDD-first, full engine suite green, split into atomic PRs, and DO NOT touch the deterministic trade pipeline. Keep your good parts (async review, RLock journal, `update_agent_review`, the flag concept).

## Hard rules (read first)
- engine/agents/* is an ADDITIVE advisory layer. It must NEVER raise into or block the deterministic entry path, and must never gate trades unless `agent_team.gating=true`.
- DO NOT modify breaker, pos_guard, orphan-protection, lifecycle cost-basis math, or the entry-drift guard logic.
- Live mainnet config changes require PR + testnet first. The committed config templates MUST keep the SAFE default. No bundling a config flip with code.
- TDD: write/adjust the failing test FIRST, then implement. Run `python -m pytest tests/engine/ -q` (the WHOLE engine suite, not just your new files) and it must be green before you claim done. Also run `python -m pytest tests/ -q` if time permits.

## BUG 1 (CRITICAL) — Sticky IN_ZONE enters off-zone. File: engine/safe_orchestrator.py:1527-1535
Current code: when `require_confirmation` is false and `cand.state == "IN_ZONE"`, you unconditionally set `CONFIRMED` and call `_place_v2_entry_order(entry_price=current_price)` with NO zone re-check. If price has left the zone, you enter arbitrarily far from it; the entry-drift guard cannot reject because `entry == current_price` (drift ≈ 0). SL/TP are anchored to the zone, so R:R silently breaks. This WIDENS the gap you are trying to shrink.
FIX:
- In the not-`require_confirmation` IN_ZONE branch, gate on `is_price_in_zone(current_price, cand.target_zone)` BEFORE confirming. If price is NOT in the zone, leave the candidate IN_ZONE (let it EXPIRE on timeout) — do not enter.
- When entering, CLAMP the entry to the nearest favorable zone edge so `entry ∈ zone` holds: LONG `entry_price = min(max(current_price, cand.target_zone.low), cand.target_zone.high)`; SHORT mirror. Pass this clamped value to `_place_v2_entry_order`.
- The AWAITING_PULLBACK fast-path branch (line 1516, already gated by `is_price_in_zone`) is correct — leave it, but apply the same zone-edge clamp to its entry_price.

## BUG 2 (CRITICAL) — The test codifies the bug. File: tests/engine/test_zone_touch_entry.py:100-125
`test_sticky_in_zone_advances_directly_on_require_confirmation_false` asserts entry at 95500 for zone [96000,97000] (price BELOW zone). This pins the bug as expected and will block your fix.
FIX: Rewrite it so an IN_ZONE candidate with price OUTSIDE the zone does NOT confirm/enter (`mock_place.assert_not_called()`, `assert cand.state == "IN_ZONE"`). Add a separate case where price is back inside the zone and assert entry fires at the clamped price. Keep `test_immediate_entry_on_zone_touch_when_require_confirmation_false` (in-zone, valid).

## BUG 3 (HIGH) — AttributeError on the LIVE v2 path. File: engine/safe_orchestrator.py:543-561, 564, 571, 1856-1864
On the live v2 path `pos = self.order_manager.open_position(...)` returns the EXCHANGE Position (exchange/__init__.py:332-360) which has `.entry` and `.order_id` — NOT `.avg_entry_price` and NOT `.id`. But `_run_agent_review_async` reads `float(pos.avg_entry_price)` (line 551, on the MAIN thread, before `thread.start()`) and `pos.id` (lines 564,571). This raises AttributeError on the main cycle thread and propagates up through `_advance_setup_state_tick` (called from run_cycle:840 with no try/except). It is masked today only because phase2_1k has `smc_v2_shadow:true`. (V1 and v2-paper use the lifecycle Position, which has both attributes.)
FIX:
- `entry = getattr(pos, "avg_entry_price", None)`; if None, `entry = getattr(pos, "entry", None)`.
- `trade_id = getattr(pos, "id", None) or getattr(pos, "order_id", None)`; use `trade_id` everywhere instead of `pos.id`.
- Wrap the ENTIRE ctx-build + thread submit in `try/except Exception` and log+swallow, so the advisory layer can NEVER raise into the entry path.
- Add a test: drive `_place_v2_entry_order` with a mocked `order_manager` returning an exchange-style Position (has `.entry`/`.order_id`, NOT `.avg_entry_price`/`.id`), shadow OFF, agent_team enabled — assert NO exception escapes and a Position is returned.

## BUG 4 (HIGH) — Unbounded thread fan-out. File: engine/safe_orchestrator.py:562-575
You spawn a raw `threading.Thread(daemon=True)` per entry. Each runs 4 sequential 30s-timeout LLM calls (~120s). A burst (max_open_positions up to 20) → ~80 concurrent LLM requests → rate-limit/OOM. This is the exact class the Kronos audit fixed.
FIX:
- Create ONE shared `concurrent.futures.ThreadPoolExecutor(max_workers=2)` in `SafeOrchestrator.__init__`; submit reviews to it instead of spawning threads.
- Add a per-`trade_id` in-flight set guarded by a lock; skip submit if already in flight (dedup).
- Make `engine/agents/team.py` thread-safe: add a lock around `_log_disagreement` (lines 172-192, currently lock-free append) and `_history`.
- On orchestrator shutdown, `executor.shutdown(wait=False)` and document verdicts as best-effort (may stay None after a restart — acceptable for advisory-only).

## BUG 5 (MEDIUM) — Don't hard-delete the gating capability. File: engine/safe_orchestrator.py:1051-1060
`_agent_veto = False; if False: pass` removes the operator's veto lever and the only writer of `latest.meta['risk_review_was_notional_blind']`.
FIX: Replace the dead block with: if `self.agent_team and self.agent_team.cfg.get("gating", False)` → run `review_trade` SYNCHRONOUSLY pre-trade and veto on `team_verdict == "REJECT"` (old behavior, default OFF), still writing `agent_review` and `risk_review_was_notional_blind` to `latest.meta`. Otherwise run the review ASYNC post-entry (your new path). No `if False`. Default stays async (gating false in prod).

## TELEMETRY (NEW, ship as the FIRST standalone PR before any behavior change)
Add to `TradeSnapshot` (engine/journal.py:25-99): `signal_entry_price`, `actual_fill_price`, `slippage_pct` (direction-signed: LONG `(fill-signal)/signal*100`, SHORT `(signal-fill)/signal*100`; `+`=adverse), `zone_mid`, `ts_signal`, `ts_fill`, `latency_ms` — all with safe defaults.
- Plumb the fill: `OrderManager.open_position` already computes `actual_entry` (exchange/__init__.py:1091) and sets `Position.entry = actual_entry` (1197). Pass both the signal entry (latest.entry) and `exchange_pos.entry` (fill) into `_journal_record_entry` and persist them. Do NOT change how the lifecycle Position is opened (cost-basis depends on it).
- Compute slippage only on the FIRST entry per trade_id (exclude pyramiding adds).
- TDD: a known signal+fill pair → correct signed `slippage_pct` and `latency_ms`.

## CONFIG-DEFAULT + ROLLOUT POLICY (mandatory)
- Revert `require_confirmation` to `true` in BOTH config.yaml:38 AND configs/config.phase2_1k.yaml (the new smc_v2 block). The code default is already true. Fix the misleading inline comment.
- Do the experiment ONLY on a separate testnet/shadow config (`smc_v2_shadow: true`).
- A live flip is a SEPARATE, explicitly-gated commit, allowed ONLY after: (1) telemetry baseline collected, (2) `backtest/evaluate_backtest_gates.py` run WITH vs WITHOUT confirmation on the same universe/window showing win_rate/profit_factor/expectancy(R)/Sharpe/max_drawdown not materially worse plus the slippage metric, (3) operator/Hermes sign-off. If the flag is ever flipped, also update PINE_SPEC.md §9/§0/§4 and re-sync both Pine files in the same change.

## COSMETIC (MEDIUM/LOW)
- engine/safe_orchestrator.py:1494: rename the rebind to `effective_pullback_timeout_bars = smc_v2_cfg.get("pullback_timeout_bars", pullback_timeout_bars)` and use that local below (avoid in-place parameter rebind). Not a logic change.
- engine/safe_orchestrator.py:1856-1864 (v2 async review): df_htf=None, adx=0.0 → degraded RegimeAgent context. Either thread the real df_htf/adx in, or add a code comment that v2 verdicts use partial context. Advisory-only.

## PR SPLIT (atomic)
1. PR-A: Telemetry-only (slippage/latency fields). 2. PR-B: Async review hardening (bounded executor, defensive attrs, thread-safe sinks, optional gating preserved). 3. PR-C: require_confirmation logic fix + test rewrite, default stays true. Keep config flips out of code PRs.

## Verification (must pass, paste output in the PR)
- `python -m pytest tests/engine/test_zone_touch_entry.py tests/engine/test_async_agent_review.py -q` — green, with the rewritten sticky test.
- `python -m pytest tests/engine/ -q` — FULL engine suite green (a behavior-path change must not break adjacent existing tests).
- Confirm no AttributeError path remains: the new live-v2 test (BUG 3) passes.
- Confirm `require_confirmation` is `true` in both committed configs.