# u2algo Price Action — zones-only publish build + zone event alerts (2026-11-19)

**Status:** operator-approved (2026-11-15 "İndikatör ürününe odaklan"; 2026-11-19 "Yalnız bölge haritası",
"Bölge olayı alert'leri", approach A).

## Why
The indicator's Signals layer draws LONG/SHORT labels with Entry/SL/TP lines and fires the only `alert()`. It mirrors
the bot's LuxAlgo v2 rule set, which measured NET −0.38 R/trade (180 d × 10 symbols, `docs/research/
2026-11-14-fvg-offline-gate.md` §5); every SMC variant measured has gross ≤ 0. Publishing those signals would spread
a disproven rule set. The operator's stated priority for the indicator (2026-11-06) is the zone map: OB, BB, MB, FVG,
liquidity, OTE.

## Scope
Only `pine/lab/tail_indicator.pine` (+ its generated `pine/efloud_lab.pine`), the publish kit text, and tests.
`pine/lab/core.pine`, `head_*`, `tail_strategy.pine` and the generated strategy are unchanged — the parity artefact
(ADR-0005) stays intact and indicator ↔ strategy shared inputs keep their names.

## Changes to the indicator tail
1. **Remove the Signals layer:** Entry/SL/TP lines, LONG/SHORT labels, the signal `alert()`, and the
   "Pending candidate zones" boxes; drop their inputs (`Pending candidate zones`, `Entry/SL/TP lines`,
   `Kept signal drawings`) and their arrays/cleanup. The core still computes candidates (shared with the strategy);
   the indicator just does not render them.
2. **Dashboard:** keep bias, range equilibrium, zone counts, OTE state; remove rows that describe the signal engine
   (pending candidates, recent rejections, Po3 state).
3. **Zone event alerts** (on confirmed bar close; informational, never a trade signal):
   - *Zone entry:* the closed bar overlaps an active (non-faded) OB/iOB, BB/MB or FVG zone that the previous closed bar
     did not overlap → event `ZONE <kind> <BULL|BEAR> [bot–top]`.
   - *Liquidity sweep:* a BSL/SSL or EQH/EQL level's first trade-through bar (`f_sweepBar`) is the current bar → event
     `SWEEP <BSL|SSL|EQH|EQL> <price>` (+ ★ when volume-confirmed).
   - Dedup: each zone/level fires at most once (key = kind + x1 + rounded bounds), held in **one**
     `map<string,int>` capped at 500 keys (no parallel arrays — RE10045 rule, `skills/tradingview-mcp/SKILL.md`).
   - All events of a bar are joined into **one** `alert()` call with `alert.freq_once_per_bar_close`.
   - Message format unchanged in spirit: empty Telegram chat id → JSON
     `{"symbol","tf","events":[...],"note":"informational, not a trade signal"}`; chat id set → Telegram HTML text
     with the same footer input.
   - New inputs (group Alerts): `Alert: zone entry` (default on), `Alert: liquidity sweep` (default on).
4. Indicator title/short title unchanged ("u2algo Price Action").

## Publish kit (`docs/indicator/tradingview-publish.md`, `docs/indicator/u2algo-price-action.md`)
Remove the Signals bullet and the "Experimental toggles"/signal settings text; rewrite the Alerts section for zone
events; keep licence/credits/disclaimer. Note in Limitations that the indicator does not generate entries.

## Testing
- TDD, static tests on the generated `pine/efloud_lab.pine` (pattern of `tests/test_pine_lab_visuals.py`):
  no `sigLines`/`sigLabels`, no `"LONG "`/`"SHORT "` signal label text, no Entry/SL/TP input titles; exactly one
  `alert(` call site; presence of the two new alert inputs, of `map.new<string, int>`, and of the cap;
  generated strategy file byte-identical to before (`build_pine_lab.py --check` + a hash test).
- `python scripts/build_pine_lab.py --check`; `tests/test_pine_lab_*.py` green.
- Runtime on TradingView (MCP: `pine_set_source` → `pine_smart_compile` → `pine_get_errors` = 0; chart shows zones,
  no signal labels; no runtime error such as RE10045 on BTCUSDT.P 15m and one more symbol). Requires TradingView
  Desktop with the debug port; the operator saves/publishes manually (`docs/indicator/tradingview-publish.md`).

## Out of scope
Any change to `core.pine` or the strategy; monetisation (licence is CC BY-NC-SA 4.0, non-commercial); new zone types.
