# Design: Publish EFloud Signals v2 indicator to TradingView (Protected, Public)

**Date:** 2026-06-03
**Sub-project:** A of the "efloud × TradingView × Kronos" initiative (see reality-check below).
**Status:** Approved, in implementation.

## Goal

Publish the existing `pine/efloud_signals.pine` (SMC v2 indicator) to tradingview.com
as a **Protected** (closed-source), **Public** script — to attract users to the
u2algo / efloud product while keeping the SMC edge (source hidden). Zero live-bot risk:
this touches no trading code, no exchange, no config.

## Reality-check that scoped this (why ONLY this sub-project, not the full vision)

The broader ask was: wire efloud-bot + Kronos + Claude + TradingView + Binance/forex so the
bot's live trades appear on TradingView and pull in users. Hard platform limits make most of
that infeasible as imagined:

- **Pine Script cannot place live orders or read a Binance account.** `strategy.entry()` is
  backtest/paper only. So the bot's live Binance trades cannot be mirrored onto a TV chart via Pine.
- **The TradingView MCP is local desktop automation (CDP), not a cloud publish.** It drives
  *our* desktop chart for analysis/Pine dev; other users never see it.
- **Binance USD-M Futures is not a TradingView-executable broker.** "Binance" on TV = chart
  data feed, not order execution.
- **Kronos cannot run inside Pine/TradingView** (local Python+torch only).

Feasible decomposition (each its own spec/cycle):
- **A (this doc):** publish the existing Pine indicator → user funnel. Zero risk.
- **B:** TradingView alert → webhook → efloud `/webhook` → safety → Binance. High value, high
  risk (live money, new execution path). Deferred.
- **C:** mirror bot trades on our own dashboard (u2algo-site / bot.ualgotrade.com) with
  lightweight-charts. Not TV. Low risk. Deferred.
- **D:** forex live via `exchange/mt5.py` + `oanda.py` adapters. Big, separate. Deferred.

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| Which script | Indicator `efloud_signals.pine` (V2) — clean per fidelity audit (V1 had 4 drifts) |
| Visibility | **Protected** (closed-source) + **Public** — edge hidden, anyone can use |
| Inputs | Keep all as-is (full flexibility; the edge is in the state-machine logic, not single defaults) |
| Language | English user-facing strings (TV House Rules) — behavior identical |

## Components

1. **English publish variant** → `pine/publish/efloud_signals_v2_en.pine`
   - Dev file `pine/efloud_signals.pine` is NOT touched (keeps strategy-sync intact).
   - Translate: header block, input labels, group names, the "wrong timeframe" warning table.
   - Already-English (leave): `plotshape`/`label` titles, `alertcondition` messages, indicator title.
   - Inline Turkish comments may stay (source is Protected → hidden from users; moderators tolerate
     non-English comments). Variable/input identifiers unchanged → behavior + parity preserved.

2. **Publication copy** → `pine/publish/PUBLISH_efloud_signals.md`
   - English: title, what-it-does, how-to-use (set profile = chart TF), input groups, profiles
     (scalp/mid/long), repaint-safety note, **"not financial advice"**, funnel link to u2algo-site.
   - House-Rules compliant: no profit promises, English, explains the script, original.

3. **Compile-clean via MCP** (local, our desktop)
   - `tv_launch` (TV must be logged in) → `pine_set_source` → `pine_smart_compile`
     → `pine_get_errors` loop until zero errors.

4. **Publish handoff** (semi-manual)
   - Pine editor → Publish script → Visibility: **Protected** + **Public** → paste description
     → agree to House Rules → Submit. Final Submit done by the user (their account + moderation).
   - Click-by-click guide provided.

## Constraints / risks

- TV Desktop must be running and **logged in** to an account that can publish (MCP currently
  not connected — `tv_health_check` failed).
- **Protected** public publishing is available on free plans; **invite-only** would need a paid
  plan (not chosen).
- Moderation requires a realistic English description and a representative chart.
- Input defaults remain visible to users (accepted — logic edge is in the hidden state machine).

## Out of scope

No changes to trading logic, exchange, config, or the dev Pine files. No webhook/execution
bridge (that is sub-project B). No live-trade mirroring.

## Verification

- English variant compiles with **zero errors** in Pine Editor (via MCP).
- Behavior parity: same `indicator()` title, same input identifiers/defaults, same signals as
  `pine/efloud_signals.pine` (string-only diff).
- Publication copy passes a House-Rules self-check (English, no profit claims, explains usage).
