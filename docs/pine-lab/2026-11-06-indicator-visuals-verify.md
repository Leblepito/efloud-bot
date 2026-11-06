# EFloud Lab — indicator zone visuals: TradingView verification (2026-11-06)

Build: `pine/efloud_lab.pine` @ 9dad0ca (display-only layers: OB, BB/MB, FVG, liquidity, OTE). Chart BINANCE perpetuals, 15m.
Python reference: `scripts/pine_lab_parity.py visuals` on `data/lab/<S>_15m.csv` (closed bars, fetched right before each symbol's run).
Last closed bar in the CSV (ms): BTC 1793952900000, ETH 1793953800000, SOL 1793953800000. TradingView's forming bar at read time: 1793954700 s for all three
(Pine draws on it from state confirmed at the previous close). The BTC variant dumps spanned about one bar close; no object changed between dumps.
Tolerance = mintick (BTC 0.1, ETH 0.01, SOL 0.01). Python objects with `idx` < 100 are excluded.

## Method

Each configuration is a compile-based source variant (never `indicator set`, see Incident). `make_variant.py` (kept outside the repo) copies `pine/efloud_lab.pine`
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
| SOL | 6/6 PASS | Pine 8 / Python 9, precision 100, recall 88.9 FAIL | 6/6 PASS | Pine 6 / Python 7, precision 100, recall 85.7 FAIL | PASS |

BTC passes every layer at any window 900-1400; ETH at 1000 and 1200. Precision is 100 % in every aligned cell.

Dashboard row 8 (zone counts, N=200) equals the drawn counts (BTC 2/1, 3, 1, 5, 3; ETH 1/4, 3, 1, 6, 3; SOL 2/4, 5, 1, 8, 6) and the OTE row equals Python `ote`
(BTC SHORT H=80927.5 L=75158 0.705=79225.4975; ETH SHORT H=2444.02 L=2205.11 0.705=2373.54155; SOL SHORT H=97.08 L=88.24 0.705=94.4722).

### Mismatches that remain

- SOL FVG 96.07/95.88 (Python bar time 1793880900000, 81 bars old) appears in Python only for windows >= 975 and is absent in Pine; at windows 850-950 FVG matches 100/100.
  Probable cause (not proven): the FVG auto threshold is a cumulative mean, so the set depends on the window start (README section 4, PINE_SPEC section 20). OB/BB for SOL also flip between windows 925 and 975.
- SOL liquidity BSL 103.89 (bar time 1793217600000, about 818 bars old): Python only; Liquidity passes at window 900 where it falls outside.
- No single window gives 100 % on all SOL layers; each layer reaches 100/100 at some window in 850-1050 (FVG 850-950, Liquidity 900, OB and BB 975-1050).
  Open item: decide whether Pine's effective loaded history (about 950 bars at read time) or the 750 live window is the reference. The SOL FVG/liquidity residuals were not proven benign.

## Stress: 1m (SOL, variant signalsON)

Compile has_errors false; after 60 s the study is healthy (61 inputs, 9-row dashboard, 16 boxes, no runtime error badge). Screenshot:
`C:/Users/utkuc/tradingview-mcp/screenshots/tv_full_2026-11-06T09-00-20-708Z.png`.

## Screenshot checklist (1m SOL screenshot; the 15m visual review remains with the operator)

- Zone and level texts (BSL, SSL, FVG, iOB, IN_ZONE) readable: yes.
- Z-order, zones behind candles and labels: yes.
- OTE direction equals dashboard: dashboard row reads SHORT; box orientation not inspected at 15m.
- Swept lines end at the sweep bar and star levels bold: not visually verified (history EQ drawing was not run).

## Incident: "Can't parse pine"

Earlier attempts left the study in an error state (no inputs, no tables, red badge). Cause: the MCP `indicator set` input round-trip makes TradingView answer "Can't parse pine"
and the study dies; a later compile only saves and never revives it. Recovery: `indicator remove <id>`, then add "EFloud Lab" again from "Komut dosyalarım" (new entity id, here XQrBO8), recompile.
Rule: change configuration only by compiling source variants; never use `indicator set`.

## Perf fix 9dad0ca

The breaker-copy check is O(P) and skipped when T2 (invalidation + breaker) is off.
