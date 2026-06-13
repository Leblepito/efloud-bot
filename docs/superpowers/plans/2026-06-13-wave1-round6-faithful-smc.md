# Wave-1 Round-6 Faithful SMC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pine Wave-1 strategy'yi engine-sadık SMC'ye çevir — near-edge zone-pullback entry + Breaker Block setup zone + likidite/FVG hedefli TP — ve 5-sembol backtest'le pozitif edge'i doğrula.

**Architecture:** Validation-first iki faz. **Faz 0** prototipi `wave1_strategy.pine`'a inşa eder + diagnostik tabloyla 5 sembolde backtest'ler → **karar gate'i** (PF>1 + iyi fill → GO). **Faz 1** sadece GO'da: diagnostik'i sök, indicator SENKRON, spec, final G-T3 + GATE_RUN_4. Edge yoksa Faz 0 sonunda DUR (kontenjans).

**Tech Stack:** Pine Script v6 (TradingView), TV Desktop MCP (`pine_set_source`/`pine_smart_compile`/`pine_get_errors`/`data_get_pine_tables`/`chart_set_symbol`), izole worktree `c:/tmp/wt-t003`, branch `feat/p001-t003-strategy` (PR #194).

**Spec:** `docs/superpowers/specs/2026-06-13-wave1-round6-faithful-smc-design.md`
**Engine fidelity refs (repo `engine/`):** `safe_orchestrator.py:1648-1697` (zone-pullback), `smc_v2/tp_calc.py:38-127` (TP), `smc.py:200-256` (OB+breaker), `smc.py:38-44` (FVG), `smc.py:91-101,318-364` (EqLevel).

**Pine "test" tanımı (her kod adımı):** `pine_set_source` → `pine_smart_compile` → `pine_get_errors` = **0 hata 0 marker** (= G-T3). Davranış değişen adımlarda ayrıca diagnostik `table.new` → `data_get_pine_tables` ile metrik okunur.

**Ön-koşul:** TV Desktop `--remote-debugging-port=9222` ile açık + `tv_health_check` yeşil (reçete: `[[reference_tradingview_mcp_launch]]`). Chart 15m. Diagnostik prototip TV editöründe geliştirilir; kaynak `wave1_strategy.pine`'da tutulur.

---

## FAZ 0 — Prototip & Doğrula (erken kill-switch)

> Detektörler (FVG/EQH-EQL/Breaker) önce eklenir (sadece tracking; trade değiştirmez → compile-only). Sonra entry+TP yeniden yazılır (trade değişir → compile + backtest). Faz sonunda 5-sembol karar gate'i.

### Task 0.1: FVG detektörü (array tracking)

**Files:**
- Modify: `pine/u2algo/wave1_strategy.pine` (OB tespit bloğundan sonra, confluence'tan önce)

- [ ] **Step 1: FVG array + tespit kodunu ekle**

`smc.py:38-44` portu. 3-bar gap. Mitigation: karşı taraf gap'i doldurunca işaretle (Wave-1: basit fill kontrolü).

```pine
// ═══ FVG DETECTION (engine smc.py:38-44 portu) ═══
// BULL FVG: low > high[2] (boşluk yukarı) · BEAR FVG: high < low[2] (boşluk aşağı)
var array<float> fvg_top = array.new<float>()
var array<float> fvg_bot = array.new<float>()
var array<int>   fvg_dir = array.new<int>()   // 1=BULL, -1=BEAR
var array<bool>  fvg_mit = array.new<bool>()
int FVG_CAP = 40
if barstate.isconfirmed
    if low > high[2]
        array.push(fvg_top, low), array.push(fvg_bot, high[2]), array.push(fvg_dir, 1), array.push(fvg_mit, false)
    if high < low[2]
        array.push(fvg_top, low[2]), array.push(fvg_bot, high), array.push(fvg_dir, -1), array.push(fvg_mit, false)
    // cap: en eski FVG'leri at
    while array.size(fvg_top) > FVG_CAP
        array.shift(fvg_top), array.shift(fvg_bot), array.shift(fvg_dir), array.shift(fvg_mit)
    // mitigation: fiyat gap içine girince doldu say
    for i = 0 to array.size(fvg_top) - 1
        if not array.get(fvg_mit, i) and low <= array.get(fvg_top, i) and high >= array.get(fvg_bot, i)
            array.set(fvg_mit, i, true)
```

- [ ] **Step 2: Compile testi**

`pine_set_source` (tüm dosya) → `pine_smart_compile` → `pine_get_errors`.
Expected: `error_count: 0` (FVG sadece tracking; trade değişmez).

- [ ] **Step 3: Commit**

```bash
git add pine/u2algo/wave1_strategy.pine
git commit -m "feat(T-003 r6): FVG detector (array tracking, engine smc.py:38-44)"
```

---

### Task 0.2: EQH/EQL likidite detektörü (pairwise cluster)

**Files:**
- Modify: `pine/u2algo/wave1_strategy.pine` (swing tracking bloğundan sonra)

- [ ] **Step 1: Swing fiyat array'leri + EQH/EQL pairwise tespiti**

`smc.py:318-364` Wave-1 sadeleştirmesi: tam greedy-cluster yerine son N swing'de eq_thr(%0.1) içindeki çiftler → EQH/EQL @ ortalama.

```pine
// ═══ EQH/EQL LIQUIDITY (engine smc.py:91-101,318-364 — Wave-1 pairwise) ═══
var array<float> sh_arr = array.new<float>()   // son swing high fiyatları
var array<float> sl_arr = array.new<float>()
int SW_CAP = 30
float eq_thr = 0.001  // %0.1 (engine eq_thr default)
if barstate.isconfirmed and new_swing_high
    array.push(sh_arr, swing_high_val)
    if array.size(sh_arr) > SW_CAP
        array.shift(sh_arr)
if barstate.isconfirmed and new_swing_low
    array.push(sl_arr, swing_low_val)
    if array.size(sl_arr) > SW_CAP
        array.shift(sl_arr)
// EQH/EQL = eq_thr içindeki swing çiftlerinin ortalaması (en son hesaplanır, TP'de kullanılır)
f_eq_levels(arr) =>
    res = array.new<float>()
    n = array.size(arr)
    if n >= 2
        for i = 0 to n - 2
            for j = i + 1 to n - 1
                a = array.get(arr, i)
                b = array.get(arr, j)
                if math.abs(a - b) / math.max(a, 1e-10) <= eq_thr
                    array.push(res, (a + b) / 2)
    res
```

- [ ] **Step 2: Compile testi** → `error_count: 0`.

- [ ] **Step 3: Commit**

```bash
git add pine/u2algo/wave1_strategy.pine
git commit -m "feat(T-003 r6): EQH/EQL liquidity detector (pairwise, engine smc.py:318-364)"
```

---

### Task 0.3: Breaker Block tracking (OB array + mitigation flip)

**Files:**
- Modify: `pine/u2algo/wave1_strategy.pine` (OB tespit bloğunu array'e çevir)

- [ ] **Step 1: OB'leri array'de tut + breaker flip**

`smc.py:250-255` portu. OB tespit edilince array'e push; her bar close OB içinden geçti mi → `mitigated=true` + yönü flip. Zone = `[bot, top]`, `dir` (1=demand/LONG, -1=supply/SHORT). Breaker'da `dir` flip'lenir.

```pine
// ═══ OB + BREAKER ZONE ARRAY (engine smc.py:200-256) ═══
var array<float> ob_top = array.new<float>()
var array<float> ob_bot = array.new<float>()
var array<int>   ob_dir = array.new<int>()    // güncel yön: 1=demand(LONG), -1=supply(SHORT)
var array<int>   ob_bar = array.new<int>()
var array<bool>  ob_brk = array.new<bool>()   // became_breaker
int OB_CAP = 30
// OB tespiti (mevcut bullish/bearish bloklardan: ob_bot/ob_top/ob_bar hesaplandıktan sonra push)
// bullish OB → dir=1; bearish OB → dir=-1
// [mevcut OB tespit döngüleri burada; tespit edilen her OB için:]
//   array.push(ob_top, hi), array.push(ob_bot, lo), array.push(ob_dir, <1|-1>), array.push(ob_bar, bar_index-cnt), array.push(ob_brk, false)
//   while array.size(ob_top) > OB_CAP: array.shift(... hepsi ...)
// Mitigation → breaker flip (her bar):
for i = 0 to array.size(ob_top) - 1
    d = array.get(ob_dir, i)
    if not array.get(ob_brk, i) and bar_index - array.get(ob_bar, i) >= 2
        if d == 1 and close < array.get(ob_bot, i)        // bullish demand kırıldı ↓ → bearish breaker
            array.set(ob_dir, i, -1), array.set(ob_brk, i, true)
        else if d == -1 and close > array.get(ob_top, i)  // bearish supply kırıldı ↑ → bullish breaker
            array.set(ob_dir, i, 1), array.set(ob_brk, i, true)
```

> NOT: Mevcut `bullish_ob_bar`/`bearish_ob_bar`/`near_swing` skalerleri confluence için KORUNUR; bu array zone-evrenini (entry seçimi) sağlar.

- [ ] **Step 2: Compile testi** → `error_count: 0`.

- [ ] **Step 3: Commit**

```bash
git add pine/u2algo/wave1_strategy.pine
git commit -m "feat(T-003 r6): OB+Breaker zone array (mitigation flip, engine smc.py:250-255)"
```

---

### Task 0.4: Near-edge zone-pullback entry (OB|BB + timeout)

**Files:**
- Modify: `pine/u2algo/wave1_strategy.pine` (sinyal + entry blokları; round-5 market entry'yi değiştir)

- [ ] **Step 1: En yakın geçerli zone seç + near-edge limit + timeout**

Sinyal: conf≥thresh + 1h bias + yön için en yakın geçerli zone (OB|BB). Entry: LONG → `limit=zone_high` (near edge yukarıdan), SHORT → `limit=zone_low` (near edge aşağıdan). `pullback_timeout_bars` (input, default 40) içinde dolmazsa cancel. `process_orders_on_close`, `allow_ob_less`, market-entry KALDIRILIR.

```pine
pullback_timeout_bars = input.int(40, "Pullback Timeout (bars)", minval=10, maxval=100, group="T-003 R6")
// f_nearest_zone(direction): aktif/breaker zone'lardan, doğru yönde, fiyata en yakın olanın [near_edge] döner
f_nearest_zone(want_dir) =>
    float best_edge = na
    float best_dist = 1e20
    for i = 0 to array.size(ob_top) - 1
        if array.get(ob_dir, i) == want_dir
            zt = array.get(ob_top, i)
            zb = array.get(ob_bot, i)
            edge = want_dir == 1 ? zt : zb        // LONG near edge = top; SHORT near edge = bot
            // sadece fiyatın "pullback ettiği taraf" (LONG: edge < close; SHORT: edge > close)
            ok = want_dir == 1 ? (edge < close) : (edge > close)
            d = math.abs(close - edge)
            if ok and d < best_dist
                best_dist := d
                best_edge := edge
    best_edge
```

Sinyal bloğunda (round-5'in `ln_entry = close` yerine):
```pine
if long_precondition and confluence_score_long >= conf_thresh and htf_bias_up
    ln_entry = f_nearest_zone(1)
    if not na(ln_entry)
        ln_sl = f_calc_sl("LONG", ln_entry)
        [ln_tp1, ln_tp2, ln_t1src, ln_t2src] = f_engine_tp("LONG", ln_entry, ln_sl)  // Task 0.5
        valid = not na(ln_sl) and not na(ln_tp1) and ln_sl < ln_entry and ln_tp1 > ln_entry
        if valid
            sig_entry_long := ln_entry ... (sig state set, sig_active_long := true, sig_entry_bar_long := bar_index)
```
(SHORT simetrik: `f_nearest_zone(-1)`, near edge = zone_low.)

Entry bloğunda: `strategy.entry("LONG", strategy.long, limit=sig_entry_long, qty=risk_qty)` (limit GERİ GELDİ — near edge) + pullback timeout cancel (round-4'ün `sig_entry_bar` + expiry mantığı GERİ GELİR, ama `limit_expiry_bars` yerine `pullback_timeout_bars`).

- [ ] **Step 2: Compile testi** → `error_count: 0`.

- [ ] **Step 3: Davranış kontrolü (tek sembol)**

Diagnostik tabloyu Task 0.6'da ekleyeceğiz; şimdilik chart BTCUSDT.P 15m'de trade üretiyor mu — `data_get_trades` kırık olduğundan Task 0.6'ya bırak. Compile yeterli.

- [ ] **Step 4: Commit**

```bash
git add pine/u2algo/wave1_strategy.pine
git commit -m "feat(T-003 r6): near-edge zone-pullback entry (OB|BB, limit @ near edge + timeout)"
```

---

### Task 0.5: Engine-sadık TP algoritması

**Files:**
- Modify: `pine/u2algo/wave1_strategy.pine` (`f_calc_tp` yerine `f_engine_tp`)

- [ ] **Step 1: `f_engine_tp` — likidite+FVG precedence, min_rr-gate, single-target**

`tp_calc.py:38-127` portu. TP1 = doğru taraftaki {EQH/EQL + HTF swing + FVG_NEAR} en yakını ≥ min_dist; yoksa RR_PROJECTION; aday var ama yetersiz → `na` döndür (REDDET). TP2 = FVG_FAR / FIB_EXT (>TP1) / NONE.

```pine
// dönüş: [tp1, tp2, tp1_src, tp2_src]  (tp1=na → trade reddedilir; tp2=na → single-target)
f_engine_tp(direction, entry, sl) =>
    risk = math.abs(entry - sl)
    min_dist = min_rr * risk
    // --- adayları topla (doğru tarafta) ---
    cands = array.new<float>()       // fiyat
    csrc  = array.new<int>()         // 0=LIQUIDITY, 1=FVG_NEAR
    eqh = f_eq_levels(sh_arr)        // Task 0.2
    eql = f_eq_levels(sl_arr)
    if direction == "LONG"
        for i = 0 to array.size(eqh)-1
            if array.get(eqh,i) > entry
                array.push(cands, array.get(eqh,i)), array.push(csrc, 0)
        if not na(last_1h_swing_high) and last_1h_swing_high > entry
            array.push(cands, last_1h_swing_high), array.push(csrc, 0)
        for i = 0 to array.size(fvg_top)-1
            if not array.get(fvg_mit,i) and array.get(fvg_dir,i) == -1 and array.get(fvg_bot,i) > entry
                array.push(cands, array.get(fvg_bot,i)), array.push(csrc, 1)
    else
        for i = 0 to array.size(eql)-1
            if array.get(eql,i) < entry
                array.push(cands, array.get(eql,i)), array.push(csrc, 0)
        if not na(last_1h_swing_low) and last_1h_swing_low < entry
            array.push(cands, last_1h_swing_low), array.push(csrc, 0)
        for i = 0 to array.size(fvg_top)-1
            if not array.get(fvg_mit,i) and array.get(fvg_dir,i) == 1 and array.get(fvg_top,i) < entry
                array.push(cands, array.get(fvg_top,i)), array.push(csrc, 1)
    // --- en yakın ≥ min_dist (LIQUIDITY>FVG_NEAR tie precedence) ---
    float tp1 = na
    int   t1src = 2   // 2=RR_PROJECTION
    float best = 1e20
    for i = 0 to array.size(cands)-1
        p = array.get(cands, i)
        dist = direction == "LONG" ? p - entry : entry - p
        if dist >= min_dist and dist < best
            best := dist
            tp1 := p
            t1src := array.get(csrc, i)
    bool has_cands = array.size(cands) > 0
    if na(tp1) and has_cands
        // aday var ama hiçbiri ≥min_dist → REDDET (InsufficientTPDistance)
        [float(na), float(na), -1, -1]
    else
        if na(tp1)
            tp1 := direction == "LONG" ? entry + min_dist : entry - min_dist
            t1src := 2
        // --- TP2: FVG_FAR (>TP1) / FIB_EXT / NONE ---
        float tp2 = na
        int t2src = 2   // 2=NONE
        float ff = na
        for i = 0 to array.size(fvg_top)-1
            if not array.get(fvg_mit,i)
                if direction == "LONG" and array.get(fvg_dir,i)==-1 and array.get(fvg_top,i) > tp1
                    ff := na(ff) ? array.get(fvg_top,i) : math.min(ff, array.get(fvg_top,i))
                if direction == "SHORT" and array.get(fvg_dir,i)==1 and array.get(fvg_bot,i) < tp1
                    ff := na(ff) ? array.get(fvg_bot,i) : math.max(ff, array.get(fvg_bot,i))
        if not na(ff)
            tp2 := ff
            t2src := 0   // 0=FVG_FAR
        else
            fib = direction == "LONG" ? entry + fib_tp2 * risk : entry - fib_tp2 * risk
            if (direction == "LONG" and fib > tp1) or (direction == "SHORT" and fib < tp1)
                tp2 := fib
                t2src := 1   // 1=FIB_EXT
        [tp1, tp2, t1src, t2src]
```

Sinyal bloğunda `valid`: `not na(tp1)` da gerektir (reddedilen trade girmez). Exit: `tp2` na ise single-target (TP1 %100); değilse TP1 %50 + TP2 kalan (mevcut yapı).

- [ ] **Step 2: Compile testi** → `error_count: 0`.

- [ ] **Step 3: Commit**

```bash
git add pine/u2algo/wave1_strategy.pine
git commit -m "feat(T-003 r6): engine-faithful TP (liquidity+FVG precedence, min_rr-gate, single-target)"
```

---

### Task 0.6: Diagnostik tablo + GATE_RUN_4-prelim (5 sembol) → KARAR GATE'İ

**Files:**
- Modify: `pine/u2algo/wave1_strategy.pine` (geçici diagnostik `table.new` — Faz 1'de sökülür)

- [ ] **Step 1: Diagnostik tabloyu ekle** (gate-run-3 tekniği)

`barstate.islastconfirmedhistory`'de `table.new` ile: closedlegs, orders, fill estimate, win%, PF, net%, maxDD%, Sharpe(trade), subRR, invert, + `rejected` sayacı (InsufficientTPDistance), + `single_tgt` sayacı (tp2=NONE). gate-run-3 raporundaki tablo şablonunu kullan.

- [ ] **Step 2: Compile** → `error_count: 0`.

- [ ] **Step 3: 5-sembol backtest oku**

Her sembol: `chart_set_symbol("BINANCE:<SYM>USDT.P")` → 6sn bekle → `data_get_pine_tables(study_filter="Wave 1")`. Semboller: BTC, ETH, SOL, BNB, XRP. `bt_segment=Full`, default config.

- [ ] **Step 4: 🚦 KARAR GATE'İ**

Hesapla: agg PF (Σgprofit/Σgloss), toplam closedlegs, fill, kaybeden sembol sayısı.
- **GO** (→ Faz 1): agg PF > 1.0 **VE** fill round-4'ten (%41) belirgin iyi **VE** toplam closedlegs ≥ ~100 (veya makul frekans).
- **NO-GO** (→ kontenjans, DUR): agg PF ≤ 1.0 veya frekans çok düşük. Raporla; spec §7 kontenjansına git (FVG/OTE-entry Wave-2 veya gate-eşik revizyonu); operatör/konsensüse taşı. **Faz 1'e GEÇME.**

- [ ] **Step 5: GATE_RUN_4-prelim sonucunu raporla + commit**

```bash
# LLTODO/reports/REPORT-T-003-gate-run-4-prelim.md yaz (per-sembol tablo + GO/NO-GO kararı)
git add pine/u2algo/wave1_strategy.pine LLTODO/reports/REPORT-T-003-gate-run-4-prelim.md
git commit -m "test(T-003 r6): GATE_RUN_4-prelim diagnostic + 5-symbol decision gate"
```

---

## FAZ 1 — Finalize (YALNIZCA Faz 0 = GO ise)

### Task 1.1: Diagnostik'i sök + committed strateji final

**Files:**
- Modify: `pine/u2algo/wave1_strategy.pine`

- [ ] **Step 1:** Diagnostik `table.new` + sayaçları kaldır (gate metrikleri ölçüm-amaçlıydı). Görsel SL/TP plot + bias table + alert (kaynak etiketli: tp1_src/tp2_src mesajda) KALIR.
- [ ] **Step 2: Final G-T3** — `pine_set_source` (tam committed) → `pine_smart_compile` → `pine_get_errors` = **0 hata 0 marker**.
- [ ] **Step 3: Commit**
```bash
git add pine/u2algo/wave1_strategy.pine
git commit -m "feat(T-003 r6): finalize strategy (strip diagnostic, G-T3 PASS)"
```

---

### Task 1.2: SENKRON indicator (`wave1_signals.pine`)

**Files:**
- Modify: `pine/u2algo/wave1_signals.pine`

- [ ] **Step 1:** Aynı detektörleri (FVG/EQH-EQL/Breaker array'leri) + near-edge entry görselini + engine-TP'yi indicator'a uygula. Input isimleri + default'lar + group'lar strategy ile BİREBİR (SENKRON kuralı). Indicator emir vermez; entry/SL/TP'yi `line.new`/`label.new`/`box.new` ile çizer (kaynak etiketli). Round-5'in `f_entry_price→close` yerine `f_nearest_zone`.
- [ ] **Step 2: G-T2 compile** — indicator inject → compile → `error_count: 0`.
- [ ] **Step 3: SENKRON doğrula** — strategy ↔ indicator input isimleri/default'ları `grep` ile karşılaştır (ob_body_mult, conf_thresh, sl_lb, sl_atr_m, min_rr, fib_tp2, pullback_timeout_bars, ...).
- [ ] **Step 4: Commit**
```bash
git add pine/u2algo/wave1_signals.pine
git commit -m "feat(T-003 r6): SENKRON indicator (OB+BB zones + engine TP visual)"
```

---

### Task 1.3: WAVE1_SPEC §7 round-6 + §8

**Files:**
- Modify: `pine/u2algo/WAVE1_SPEC.md`

- [ ] **Step 1:** §7'ye round-6 alt-bölümü: OB+BB zone evreni, near-edge zone-pullback entry, engine-TP (likidite/FVG precedence, single-target), yeni detektörler + Wave-1 sadeleştirmeleri (EQH/EQL pairwise, 15m FVG, array cap). §1 input tablosuna `pullback_timeout_bars` ekle, kaldırılan input'ları (allow_ob_less, limit_expiry, extended_expiry) işaretle. §8 revizyon geçmişine round-6 satırı.
- [ ] **Step 2: Lint** — `python LLTODO/scripts/lltodo_lint.py` = 8/8.
- [ ] **Step 3: Commit**
```bash
git add pine/u2algo/WAVE1_SPEC.md
git commit -m "docs(T-003 r6): WAVE1_SPEC round-6 (zone-pullback + engine TP + breaker)"
```

---

### Task 1.4: Tam GATE_RUN_4 (Full + IS/OOS) + rapor + STATE/task

**Files:**
- Create: `LLTODO/reports/REPORT-T-003-gate-run-4.md`
- Modify: `LLTODO/STATE.md`, `LLTODO/tasks/IN_PROGRESS/T-003-strategy-backtest.md`

- [ ] **Step 1: Tam gate** — diagnostik build'i geçici geri ekle (veya ayrı), 5 sembol × {Full, IS, OOS} oku. Gate'ler: G-T3 ✅, G-T4a count≥100 (veya revize eşik), G-T4b OOS-Sharpe ≥ IS×0.7 (bt_segment ile), G-T5 inverted=0, G-T6 subRR=0, PF/MaxDD. Limit-fill + rejected-trade oranını raporla.
- [ ] **Step 2: Rapor yaz** — gate-run-3 formatında: per-sembol Full + IS/OOS tablosu, round-4/5/6 PF karşılaştırması, NET verdict (PASS → IMPL_READY / FAIL → kontenjans).
- [ ] **Step 3: STATE.md + task log** — append-only GATE_RUN_4 satırı; PASS ise P-001 durumu `IMPL_READY` → FAZ 4 UR-001, FAIL ise kontenjans.
- [ ] **Step 4: Lint 8/8 + commit + push**
```bash
git add LLTODO/reports/REPORT-T-003-gate-run-4.md LLTODO/STATE.md LLTODO/tasks/IN_PROGRESS/T-003-strategy-backtest.md
git commit -m "test(T-003 r6): GATE_RUN_4 full (5-symbol Full+IS/OOS) + report"
git push origin feat/p001-t003-strategy
```

- [ ] **Step 5: PR #194 yorumu** — GATE_RUN_4 özeti + verdict (`gh pr comment 194 --body-file ...`).

---

## Faz 0 NO-GO Kontenjansı (kill-switch)

Faz 0 Task 0.6 NO-GO verirse:
- `REPORT-T-003-gate-run-4-prelim.md`'de NO-GO + sebep (PF/frekans) belgele.
- STATE.md'ye append: round-6 zone-pullback de geçmedi → spec §7 kontenjansı.
- Operatör/konsensüse seçenekler: (a) FVG/OTE-entry zone'unu spec'e al (Wave-2 erken), (b) gate "min 100 trade" + "WR≥%50" eşiklerini SMC-runner gerçeğine revize, (c) indicator-only ship.
- **Faz 1'e GEÇME** — boşuna finalize etme.

---

## Self-Review (plan ↔ spec)

- **Kapsam:** §3.1 OB+BB → Task 0.3 ✓ · §3.2 near-edge entry → 0.4 ✓ · §3.4 engine TP → 0.5 ✓ · §3.5 FVG/EQH-EQL/Breaker → 0.1/0.2/0.3 ✓ · §3.6 bt_date/bt_segment → round-5'ten korunur (Task 0'da mevcut) ✓ · §7 validation-first → Faz 0 + 0.6 karar gate ✓ · §8 SENKRON → 1.2 ✓.
- **Placeholder:** Detektör/TP/entry kodu gösterildi; OB-array push satırı (0.3 Step 1) mevcut OB döngüsüne entegre (yorum-işaretli) — implementasyonda mevcut bullish/bearish bloklara eklenecek.
- **Tip tutarlılığı:** `f_nearest_zone`/`f_engine_tp`/`f_eq_levels` + array isimleri (`ob_top/bot/dir/bar/brk`, `fvg_top/bot/dir/mit`, `sh_arr/sl_arr`) tüm task'larda tutarlı.
