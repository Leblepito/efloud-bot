# Publishing EFloud Signals v2 to TradingView (Protected · Public)

This is the publication packet for `efloud_signals_v2_en.pine`. Copy the description
into TradingView's **Publish script** dialog. Source stays **Protected** (hidden); the
script is **Public** (anyone can add it to a chart and use it).

---

## Title

```
EFloud Signals v2 — Multi-Timeframe Smart Money Concepts
```

## Short description (the publication text — English, House-Rules compliant)

```
EFloud Signals v2 is a multi-timeframe Smart Money Concepts (SMC) tool. Instead of
firing on every break, it waits for a structured sequence before printing a signal:

  1. Higher-timeframe bias  — trend from market structure (CHoCH/BOS), with a slope
     fallback when structure is undefined. Signals are only taken in the direction of
     the HTF bias.
  2. Change of Character (CHoCH) on your chart timeframe — a reversal break, not a
     continuation.
  3. Pullback into a zone — the nearest unmitigated Fair Value Gap (FVG), or an
     Optimal Trade Entry (OTE 0.618–0.786) band as fallback.
  4. Engulfing confirmation inside the zone (optional) before the entry prints.

When a setup confirms, the script draws Entry, Stop Loss and TP1/TP2 levels:
  • Stop Loss — structural (zone/​swing) plus an ATR buffer, with min/max ATR clamps.
  • Take Profit — a hybrid ladder: nearest liquidity (HTF swings + equal highs/lows)
    and FVG targets, with a Fibonacci price-discovery fallback (1.272 / 1.618 / 2.618)
    and a minimum R:R filter.

HOW TO USE
  • Pick a Trade-Horizon Profile: scalp / mid / long (or custom).
  • Set your CHART timeframe to the profile's entry timeframe
    (scalp = 5m, mid = 15m, long = 1h). A red warning shows if the chart TF doesn't match.
  • The HTF is derived automatically from the profile (scalp 12h, mid 4h, long 1w).
  • Optional daily macro filter can reject counter-trend setups.
  • Alerts: "EFloud V2 LONG" / "EFloud V2 SHORT" fire on confirmed entries.

REPAINT
  Signals evaluate on confirmed (closed) bars; higher-timeframe data is requested with
  lookahead off. Zone boxes for still-pending setups update live until a setup confirms
  or expires, which is expected behavior for a waiting-state tool.

This is a research/analysis tool, not financial advice and not a recommendation to buy
or sell. Past behavior does not guarantee future results. Always use your own risk
management.
```

> House-Rules notes: English only; no profit claims or performance promises; explains
> what the script does and how to use it; original work. Add 1–2 representative chart
> screenshots (a clean LONG and SHORT example) when publishing.

## Tags / category

`Smart Money Concepts`, `CHoCH`, `Fair Value Gap`, `OTE`, `Multi-Timeframe`, `Trend Analysis`

## Optional funnel line (only if it complies — keep it soft, no spam)

A single, non-promotional pointer is usually tolerated; avoid hard CTAs/affiliate links:

```
Built by the u2algo / EFloud team. More on the methodology: ualgotrade.com
```

(If moderation flags external links, remove this line — the script stands on its own.)

---

## Step-by-step publish (final Submit is done by you, on your TV account)

Prereqs: TradingView **Desktop** open and **logged in** to an account that can publish.
Protected public publishing works on free plans (invite-only would need a paid plan — not used here).

1. Open Pine Editor → paste the contents of `efloud_signals_v2_en.pine`
   (or let Claude inject it via the TradingView MCP: `pine_set_source`).
2. **Save** the script (Ctrl/Cmd+S), give it the Title above.
3. Compile and confirm **zero errors** (MCP: `pine_smart_compile` → `pine_get_errors`).
4. Add it to a clean chart on the right symbol+TF (e.g. BINANCE:BTCUSDT, 15m for `mid`)
   and take 1–2 screenshots showing a LONG and a SHORT signal with levels.
5. Click **Publish script** (top-right of the Pine Editor).
6. In the dialog:
   - Title: paste the Title.
   - Description: paste the Short description.
   - Privacy/Source: choose **Protected** (closed-source).
   - Visibility: **Public**.
   - Add the screenshots + tags.
7. Read and accept the **House Rules**, then **Submit**. TradingView moderates before it
   goes live in the public library — this can take a little while.

## Verification checklist

- [ ] `efloud_signals_v2_en.pine` compiles with zero errors.
- [ ] Title + description are English, explain usage, make no profit claims.
- [ ] Source set to Protected, visibility Public.
- [ ] 1–2 representative screenshots attached.
- [ ] Behavior matches `pine/efloud_signals.pine` (string-only diff — verified in the spec).
