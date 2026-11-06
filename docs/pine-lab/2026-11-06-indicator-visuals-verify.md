# EFloud Lab — indicator zone visuals: TradingView verification (2026-11-06)

Build: `pine/efloud_lab.pine`, kaynak build 9dad0ca (display-only layers: OB, BB/MB, FVG, liquidity, OTE). Chart BINANCE perpetuals, 15m.
Python reference: `scripts/pine_lab_parity.py visuals` on `data/lab/<S>_15m.csv` (closed bars, fetched right before each symbol's run).
Last closed bar in the CSV (ms): BTC 1793952900000, ETH 1793953800000, SOL 1793953800000. TradingView's forming bar at read time: 1793954700 s for all three
(Pine draws on it from state confirmed at the previous close). The BTC variant dumps spanned about one bar close; no object changed between dumps.
Tolerance = mintick (BTC 0.1, ETH 0.01, SOL 0.01). Python objects with `idx` < 100 are excluded.

## Sonuç / Verdict

- BTC ve ETH: §6 katman eşiklerinin tamamını hizalı 1000-bar penceresinde geçer.
- SOL: FVG recall 88.9 % ve likidite recall 85.7 % ham eşiğin altında kalır; kalan iki kayıp referans artefaktı olarak açıklandı → §6 gate "met with explained reference artefacts (SOL FVG/liquidity)" (aşağıda "Mismatches that remain").
- 750-bar spec penceresi OB/FVG/likidite precision'da kalır: Pine ~950 bar geçmiş görür, fazladan eski nesneleri çizer (pencere artefaktı; recall her yerde 100 %).
- Sinyal regresyonu geçti (60=60 x3, katmanlar ON/OFF aynı LONG/SHORT seti).
- 1m stres sağlıklı (hata yok, 61 girdi, 9 satır dashboard).

## Method

Each configuration is a compile-based source variant (never `indicator set`, see Incident). `scripts/pine_lab_variant.py` copies `pine/efloud_lab.pine`
and rewrites only the `input.bool` defaults of `showObs/showZones/showLevels/showBreakers/showFvg/showLiq/showOte`, `showHistory` and the `maxZonesPerSide` default.
Variants: signalsON (all layers, N=8), signalsOFF (OB/zones/levels only, N=8), isoOB, isoBB, isoFVG, isoLIQ, isoOTE (one layer, N=200).
After each compile: health check (61 inputs and 9-row dashboard) before reading boxes/lines/labels/tables.

## Signal regression (spec 6.6)

LONG/SHORT label multiset (text, price) with the new layers ON vs OFF:

| Symbol | LONG/SHORT ON | OFF | Identical | total labels ON / OFF |
|---|---|---|---|---|
| BTC | 60 | 60 | yes | 63 / 60 |
| ETH | 60 | 60 | yes | 63 / 60 |
| SOL | 60 | 60 | yes | 66 / 60 |

The extra 3 / 3 / 6 labels are the new layers' own labels. Signal output is unchanged.

## Layer parity, spec window (750 bars, warm-up 100)

| Symbol | Layer | Pine | Python | Precision % | Recall % | Verdict |
|---|---|---|---|---|---|---|
| BTC | OB | 3 | 2 | 66.7 | 100 | FAIL (window) |
| BTC | FVG | 5 | 4 | 80.0 | 100 | FAIL (window) |
| BTC | BB/MB | 4 | 4 | 100 | 100 | PASS |
| BTC | Liquidity | 3 | 2 | 66.7 | 100 | FAIL (window) |
| BTC | OTE box + 4 lines | 1 + 4 | 1 + 4 | 100 | 100 | PASS |
| ETH | OB | 5 | 5 | 100 | 100 | PASS |
| ETH | FVG | 6 | 5 | 83.3 | 100 | FAIL (window) |
| ETH | BB/MB | 4 | 4 | 100 | 100 | PASS |
| ETH | Liquidity | 3 | 2 | 66.7 | 100 | FAIL (window); SSL star 2172.85 also Pine-only |
| ETH | OTE box + 4 lines | 1 + 4 | 1 + 4 | 100 | 100 | PASS |
| SOL | OB | 6 | 3 | 50 | 100 | FAIL (window) |
| SOL | FVG | 8 | 4 | 50 | 100 | FAIL (window) |
| SOL | BB/MB | 6 | 5 | 83.3 | 100 | FAIL (window) |
| SOL | Liquidity | 6 | 3 | 50 | 100 | FAIL (window) |
| SOL | OTE box + 4 lines | 1 + 4 | 1 + 4 | 100 | 100 | PASS |

Recall is 100 % everywhere; every miss is a Pine-only object, i.e. Pine sees more history than the 750-bar Python window.
The extras are older than the window (BTC OB 81953.7/81591.2, FVG 81591.2/81436.2, BSL 81953.7; ETH SSL 2172.85; SOL MB 100.38/100.1 about 755 bars old).
With a longer Python `--window` they appear, so the 750 result is a reference-window limitation, not a drawing error.

## Layer parity, aligned window (`--window 1000`)

| Symbol | OB | FVG | BB/MB | Liquidity (+ stars) | OTE |
|---|---|---|---|---|---|
| BTC | 3/3 PASS | 5/5 PASS | 4/4 PASS | 3/3 PASS | PASS |
| ETH | 5/5 PASS | 6/6 PASS | 4/4 PASS | 3/3 PASS, stars 2/2 | PASS |
| SOL | 6/6 PASS | Pine 8 / Python 9, precision 100, recall 88.9 FAIL | 6/6 PASS | Pine 6 / Python 7, precision 100, recall 85.7 FAIL → 6/6 after the reference prune (see "Follow-up") | PASS |

Per-window sweep claims (BTC 900-1400, ETH 1000/1200, SOL 925-975) were made during the session, but the sweep outputs were not kept (only the 750 and 1000 results are recorded in the dumps), so they are not reproduced here; re-run `pine_lab_parity.py visuals --window N` to regenerate. Precision is 100 % in every aligned cell.

SOL does not meet the §6 thresholds at this window (FVG recall 88.9 %; liquidity recall was 85.7 % before the reference prune, 100 % after it).

1000 was chosen as the nearest round window at or above the ~950 bars Pine had loaded at read time, so Python sees at least as much history as Pine.

Dashboard row 8 (zone counts, N=200) equals the drawn counts (BTC 2/1, 3, 1, 5, 3; ETH 1/4, 3, 1, 6, 3; SOL 2/4, 5, 1, 8, 6) and the OTE row equals Python `ote`
(BTC SHORT H=80927.5 L=75158 0.705=79225.4975; ETH SHORT H=2444.02 L=2205.11 0.705=2373.54155; SOL SHORT H=97.08 L=88.24 0.705=94.4722).

### Mismatches that remain

- SOL FVG 96.07/95.88 (Python bar time 1793880900000, 81 bars old) appeared in Python only at larger windows (>= 975 in the session notes) and is absent in Pine (unrecorded sweep).
  Explained (verified against `data/lab/SOL_15m.csv` and the code): Pine's FVG auto threshold is a rolling 750-bar mean (`core.pine`, `math.sum(math.abs(fvgDelta), liveWindowBars) / fvgT * 2`), whereas Python's `lx.analyze` uses a cumulative mean from the window start (`engine/smc_v2/luxalgo.py`). For this FVG |delta| = 4.157e-5; thresholds are Python@1000 = 4.095e-5 (detected), Pine rolling-750 = 4.343e-5 (not detected), Python@750 = 4.423e-5 (not detected). So the mismatch is a windowing artefact of the reference, not a drawing error. OB/BB for SOL also flip between windows 925 and 975 for the same reason.
- SOL liquidity BSL 103.89 (bar time 1793217600000, about 818 bars old): Python only. Explained: its pivot bar is 818 bars old and `core.pine` prunes pivots older than `liveWindowBars = 750`, so Pine drops it; the Python reference did not apply that prune when `--window > 750`, so windows above 750 over-reported. RESOLVED: `expected_visuals` now applies the prune at the last bar (`live_window = 750`); at `--window 1000` the BSL is gone and the unswept liquidity set is 6 = Pine's 6.
- The 750-window precision misses (Pine-only extras, all >= ~755 bars old) are explained the same way: a 750-bar Python window cannot see pivots or OB candles before its start.
- No single window was found that gives 100 % on all SOL layers (session notes; sweep data not kept).
  Conclusion: no open operator decision. The live 750 window is the reference; the SOL FVG residual is an explained reference artefact (rolling vs cumulative FVG threshold); the liquidity residual was the missing 750-bar prune and is fixed in the reference. Section 6 gate: met with explained reference artefact (SOL FVG).

## Stress: 1m (SOL, variant signalsON)

Compile has_errors false; after 60 s the study is healthy (61 inputs, 9-row dashboard, 16 boxes, no runtime error badge). Screenshot:
`C:/Users/utkuc/tradingview-mcp/screenshots/tv_full_2026-11-06T09-00-20-708Z.png`.

## Screenshot checklist (1m SOL screenshot plus 15m controller screenshot)

- Zone and level texts (BSL, SSL, FVG, iOB, IN_ZONE) readable: yes.
- Z-order, zones behind candles and labels: yes.
- 15m visual checklist verified by the controller's screenshot: boxes with OB/BB/MB/FVG text, OTE SHORT band, BSL lines with labels, 9-row dashboard, signal labels present.
- Deferred (not checked): swept line ending at the sweep bar, bold star width (history EQ drawing was not run). → showHistory run: see "Follow-up".

## Incident: "Can't parse pine"

Earlier attempts left the study in an error state (no inputs, no tables, red badge). Cause: the MCP `indicator set` input round-trip makes TradingView answer "Can't parse pine"
and the study dies; a later compile only saves and never revives it. Recovery: `indicator remove <id>`, then add "EFloud Lab" again from "Komut dosyalarım" (new entity id, here XQrBO8), recompile.
Rule: change configuration only by compiling source variants; never use `indicator set`.

## Perf fix 9dad0ca

The breaker-copy check is O(P) and skipped when T2 (invalidation + breaker) is off.

## Follow-up (2026-11-06, deferred items)

### Reference prune (`scripts/pine_lab_visuals.py`)

`expected_visuals` now mirrors `core.pine` `f_prunePools` at the last bar (`live_window` = `liveWindowBars` = 750): OBs and BB/MB flips by
`created`, FVGs by `idx`, pivots and EQH/EQL by `bar`. Test: `tests/test_pine_lab_visuals.py` (prune helper + 900-bar integration). Regenerated at `--window 1000`:

| Symbol | OB (swing/internal) | FVG | unswept liquidity | flips | change vs the 1000 run above |
|---|---|---|---|---|---|
| BTC | 2/1 | 5 | 3 (BSL 81953.7 / 81188.0 / 80927.5) | 4 | none |
| ETH | 1/4 | 6 | 3 (BSL 2449.95 / 2444.02, SSL 2172.85) | 4 | none |
| SOL | 2/4 | 9 | 6 (BSL 103.16 / 98.54 / 98.16 / 97.08, EQH 98.52 / 90.53) | 6 | BSL 103.89 dropped → liquidity 6/6 |

SOL liquidity is derived from the recorded Pine set (6 levels, the only miss was BSL 103.89); the Pine side was not re-read, since the chart has moved past the CSV's last bar.
SOL FVG 96.07/95.88 (rolling vs cumulative threshold) is unchanged, 9 vs Pine 8. Oldest surviving objects are now ≤ 738 bars old on all three symbols.

### TradingView runtime checks (deferred variants, BTCUSDT.P 15m, study XQrBO8)

Method as in README §5: `pine set --file <variant>` + `pine compile` (CLI), health after ~40 s = no `RE1…` badge, `data indicator` lists the inputs (62 entries incl. meta),
`data tables -f "EFloud Lab"` 9 rows. `indicator set` was not used. Variants were built from the repo build with only the one default flipped
(`pine_lab_variant.py` for `showHistory`; a one-line `sed` on `obInvalidate` / `obBodyOnly`).

| Variant | Health | Dashboard zones row | Boxes | Screenshot (`C:/Users/utkuc/tradingview-mcp/screenshots/`) |
|---|---|---|---|---|
| Baseline (repo build dbf9d60) | OK | `2/1·4·0·5·3` | 13 | – |
| T2 on (`obInvalidate`), build dbf9d60 | **FAIL: RE10045** `Error on bar 12325: In 'array.get()' function. Index 2 is out of bounds, array size is 0. at f_collectObs():1052` | no table | no boxes | `lab_variant_t2ON_obsOnly_RE10045.png` |
| T2 on, all zone layers off | OK (`Variant B|T2`, `OB_INVALIDATED:5`) | `0/0·0·0·0·0` | – | – |
| T2 on, `showObs` only | FAIL: same RE10045 | no table | – | – |
| T2 on, `showObs` only, guard split into `if src >= 0` | FAIL: same RE10045 at the `array.get` line | no table | – | – |
| T2 on, `showObs` only, guard as one `map<int,int>` | OK | `2/2·0·0·0·0` | – | – |
| **T2 on, all layers, map fix (this commit)** | OK (`Variant B|T2`, `OB_INVALIDATED:5`) | `2/2·4·0·6·3` | 15 | `lab_variant_t2ON_15m_mapfix.png` |
| `obBodyOnly` on, map fix | OK | `2/1·4·0·6·3` | 14 | `lab_variant_obBodyOnly_15m.png` |
| `showHistory` on, map fix | OK | `2/1·4·0·6·3` | 15 (14 + faded `OB ✓` 80916.8/80793) | `lab_variant_showHistory_15m.png` |

Findings:
- **T2 bug (fixed here).** Core T2 alone is healthy (`23ff2ec` had never been run on TradingView: "Compile-gate: pending"); the crash was the tail's breaker-copy
  guard in `f_collectObs`, which kept two function-local `array<int>` (`seenKeys`, `seenAt`) pushed in lock-step and indexed one with the other's `indexof`.
  On TradingView the second array was empty when the first reported index 2 (deterministic, bar 12325), with or without short-circuiting the `and`.
  Cause not pinned further; replacing the pair with a single `map<int,int>` (key `idx*2+(bull?1:0)` → earliest `createdIdx`, same semantics as the
  first-match `indexof`) removes the error. Core and strategy are untouched. The flip tracker's `f_isBreakerCopy` loop (showBreakers under T2) is exercised by the all-layers run and is fine.
- **obBodyOnly.** Every OB/BB box edge equals the Python `max/min(open, close)` of the OB candle (81744.8/81686, 80908/80682.1, 80563.1/80508.8, 80106/80099.2,
  78338.2/78328.9, 77762.8/77724.1); FVG boxes unchanged. The chart had advanced two bars since the baseline read (extra FVG 76072.1/75727.3), so the 5→6 FVG delta is the clock, not the flag.
- **showHistory.** Closes the two items deferred above. `data lines -f "EFloud Lab"` verbose: 5 faded dashed swept levels (80344, 78706.8, 77816.1, 78134, 77510.5) each span creation bar → sweep bar only (`x2` = sweep bar, 1–2 bars long), while the 3 active BSL lines (80927.5, 81188, 81953.7) extend to the last bar; the volume-confirmed one (77816.1) is drawn at width 2 (bold star width). One faded mitigated OB box (`OB ✓`, 80916.8/80793, transparent border/fill) is added; active zone counts are unchanged.

Final state: the repo build (`pine set --file pine/efloud_lab.pine` + compile, pineVersion 44) is back on the chart and healthy (defaults, 9 rows, `2/1·4·0·6·3`).
