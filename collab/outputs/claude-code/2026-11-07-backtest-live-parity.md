# Backtest vs live parity — 2026-11-07 (decision 3, T-20261107-24)

Source: branch `collab/claude-code/T-20261107-24-operator-decisions-backtest` @ `435df23` (PR #335) ·
produced 2026-11-07 ~22:45 UTC · config `configs/config.phase2_1k.yaml` (the live config) ·
live data: read-only copy of the prod trade journal (105 rows, entries 2026-09-28 → 2026-11-06).

**Informational, not a gate.** It answers one question: does the restored backtest trade the way
the live bot trades today?

## Short answer

- **Since LuxAlgo went live (2026-11-02 →), the backtest reproduces 8 of the 10 live entries.**
  Each match has the same symbol and direction, and the backtest bar is one 15m bar before the
  live fill (the live fill lands at that bar's close).
- **All 8 matched pairs have the same outcome and a similar PnL.** Same sign every time: 6 losers,
  2 winners. For example DOGE SHORT is +7.33 live vs +6.28 backtest (TP2), and SOL LONG is
  +9.73 vs +8.82 (TP2).
- **Over the full 41 days, only 11 of 88 live entries match.** That is expected. The live config
  changed about 18 times in the window, and before 2026-11-01 live ran different code
  (pre-LuxAlgo).
- **Today's logic is not profitable on this window.** 10 symbols × 41 days gives 137 trades,
  33.6 % wins, gross PF 0.69, and **NET −$181.9** on 10 × $2000 (−0.91 %), of which $58.4 is
  commission and funding. 8 of 10 symbols have PF < 1. This matches the earlier NET-cost
  finding (T-20261104-09: about −0.30 R per trade).

## How it was run

- **Per symbol:** `python -m backtest.cli single --symbol <S>/USDT --period-days 41 --config
  configs/config.phase2_1k.yaml`, 4 symbols in parallel.
  - The portfolio run is serial at about 28 min per symbol and would not finish inside its
    timeout, so I ran single-symbol jobs instead.
  - `max_open_positions` is 10, which is one per symbol, so 10 single-symbol runs are a fair
    stand-in for the portfolio.
- **Live parity in the engine (PR #335):**
  - `smc_version` comes from the config (v2).
  - Every timeframe gets 750 bars of history (live `kline_limit`); the daily frame is capped at
    100 bars.
  - Exits work as on the exchange: TP1 closes 50 %, the stop moves to break-even, then TP2.
  - NET costs come from the config (0.04 % commission, 0.01 % funding per 8 h).
  - The LLM, agent team and Kronos are off.
- **Matching** uses `backtest.compare_live.reconcile`: same symbol and direction, nearest
  simulated bar within ±2 h. A ±6 h window changes nothing after 11-02; over the full window
  it gives 15 matches.
  - The early journal wrote one row per TP leg. Rows for the same symbol and direction within
    60 s are merged, so 105 rows become 88 entries.
- **PnL is gross on both sides.** Binance realized PnL excludes fees, and so does the backtest
  per-trade `pnl`.

## Bug found and fixed on the way: the backtest breaker ran on the wall clock

The first SOL run tripped "Daily loss −10.19 %" even though its whole 41-day return was −2.68 %.
The cause was the backtest mixing simulated time with the real clock:

1. **Closed trades were recorded at wall-clock time.** `record_trade(pnl)` was called with no
   timestamp, and the v2 entry gate called `breaker.check(now=None)`. Every simulated trade
   therefore counted as "today", so the daily-loss check summed the whole run. It then tripped
   with a real-time resume time (tomorrow), which blocked every remaining simulated bar.
   SOL was the only symbol where this happened, and it cut its trades from 18 to 16.
2. **Pauses were judged against the wall clock.** `BreakerStatus.can_trade` compared a TRIPPED
   pause with the real clock, which is always later than any simulated resume time. Every
   consecutive-loss pause was released immediately. This was audit defect 1 from 2026-08-12,
   pinned as a strict xfail.
   - After the fix, the pauses really block (for example TRX: 16 blocked cycles, previously 0).
   - In this window no setup happened to land inside a pause, so the other trade lists did
     not change.

Fixes `da675dc` + `435df23`:
- The orchestrator records closed trades at the cycle time and passes it to the v2 gate.
- `check(now)` stamps the status with `as_of`.

Live passes `now=None` everywhere, so live behaviour is unchanged. The risk-safety-auditor
confirmed this: SAFE_WITH_NITS, with the call-site list in the PR. Tests are
`tests/backtest/test_breaker_sim_time.py` (TEST-BT-004), and the 2026-08-12 xfail for defect 1
was removed because it now passes. All numbers in this report come from the fixed runs.

**Open, not fixed here:** the breaker's weekly peak timestamp (`peak_set_at`) is still the wall
clock, so in a backtest the 7-day peak rebase never happens. This is conservative: a backtest
can only halt more often than live, never less. It did not trigger in these runs (max DD
2.6 %). The fix belongs in `engine/safety/breaker.py` behind its own risk-ops review.

## Per symbol (41 days, 2026-09-27 → 2026-11-07, NET)

| Symbol | Trades | Win % | PF | NET return | Max DD | Costs $ |
|---|---|---|---|---|---|---|
| ADA | 13 | 30.8 | 0.93 | −0.22 % | 1.61 % | 5.56 |
| BCH | 7 | 57.1 | 1.55 | +0.42 % | 1.37 % | 3.11 |
| BNB | 12 | 33.3 | 0.53 | −0.74 % | 0.97 % | 5.05 |
| BTC | 14 | 42.9 | 0.76 | −0.58 % | 0.75 % | 6.05 |
| DOGE | 13 | 30.8 | 0.56 | −1.08 % | 1.36 % | 5.35 |
| ETH | 19 | 26.3 | 0.43 | −2.15 % | 1.98 % | 7.94 |
| LINK | 10 | 30.0 | 0.57 | −1.10 % | 1.31 % | 4.25 |
| SOL | 18 | 22.2 | 0.42 | −2.46 % | 2.57 % | 7.34 |
| TRX | 19 | 36.8 | 0.32 | −0.82 % | 0.76 % | 8.00 |
| XRP | 12 | 41.7 | 1.17 | −0.36 % | 1.80 % | 5.76 |

All runs report `skipped_cycles = 0`. The 15m cache ends 2026-11-07 13:00 UTC, 0.1 day before
the period end (the CLI prints a stale-cache warning).

## Comparable window: 2026-11-02 → 2026-11-06 (LuxAlgo live)

Live had 10 entries and the backtest 20; 8 are matched.

| Symbol | Dir | Live entry | Backtest bar | Live PnL | Backtest PnL | Backtest exit |
|---|---|---|---|---|---|---|
| DOGE | SHORT | 11-02 04:15 | 11-02 04:00 | +7.33 | +6.28 | TP2 |
| BNB | LONG | 11-02 16:45 | 11-02 16:30 | −3.52 | −4.16 | SL |
| TRX | SHORT | 11-02 23:00 | 11-02 22:15 | −1.13 | −2.60 | SL |
| SOL | LONG | 11-03 06:45 | 11-03 06:30 | +9.73 | +8.82 | TP2 |
| BCH | LONG | 11-05 18:30 | 11-05 18:15 | −10.65 | −11.44 | SL |
| ETH | LONG | 11-06 02:30 | 11-06 02:15 | −5.57 | −6.58 | SL |
| BTC | LONG | 11-06 04:45 | 11-06 04:30 | −3.28 | −4.60 | SL |
| TRX | SHORT | 11-06 05:00 | 11-06 04:45 | +0.88 | +0.32 | SL at break-even after TP1 |

- **Each of the 6 losing backtest trades is larger** than its live pair (by 7 % to 130 %). This fits the
  backtest's pessimistic fills (slipped entry, SL taken at the bar open when it gaps through).
- **Live entries not reproduced (2):**
  - BTC LONG 11-02 17:00 (−3.47).
  - SOL LONG 11-06 07:30 (PnL 0 in the copy, probably still open).
- **Backtest-only entries (12):** ADA, BNB, SOL ×2, ETH ×3, XRP, BTC ×2, LINK, BCH. Together they
  are 2 winners (TP2) and 10 SL. These causes are possible but **not verified**:
  - Live downtime: AUTOSTART=0, so a restart leaves the bot idle until a manual start.
  - Exchange-side rejects the backtest does not model: the entry-drift guard, min notional,
    −2021.
  - The live journal copy ends at 11-06 07:30, so the two entries after it (ETH 08:30,
    BCH 09:00) may simply not be in the copy.

## Full window (2026-09-27 → 2026-11-06)

- **11 of 88 live entries match** (15 at ±6 h).
- **Direction is the clearest difference.** Live opened 26 SHORTs on these symbols (BTC 4,
  LINK 5, TRX 5, XRP 3, …), while today's logic mostly goes LONG over the same bars (BTC 13/0,
  ETH 17/0, SOL 17/0). DOGE is the exception, at 0/13 SHORT.
- **Most of the window ran pre-LuxAlgo code and older configs**, so this is the logic changing,
  not the backtest drifting.
- **This window does not validate the backtest; the 11-02 → window does.**

## What this means

- **The backtest is usable again.** It runs the current live logic and reproduces the current
  live entries, timing and outcomes on the window where live and backtest share the same code.
- **What it says about the edge is negative.** On 41 days × 10 symbols NET it is −0.91 %, which is
  consistent with the earlier gate measurements. Any change to entries or scoring should now go
  through `backtest.cli` with the NET gate (CLAUDE.md principle 4), not through live
  observation.
- **Next (backlog item 12, now unblocked):** speed. At about 28 min per symbol per 41 days, a
  10-symbol × 1-year gate takes about 40 CPU-hours.
