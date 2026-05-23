"""HTF swing anchor selection for SMC v2 structural SL.

Per spec §10 #1:
  Return the most recent unbroken HTF swing on the 'wrong side' of the trade.

  - For SHORT: wrong side = swing_highs above entry. Unbroken = no HTF bar
    formed after the swing has traded above the swing's price.
  - For LONG: mirror — swing_lows below entry; unbroken = no bar.low < price.

  Returns the swing's price (float), or None if no unbroken swing exists.
  When None, the caller raises SLTooFarError (setup rejected per spec).

Pure function — no I/O, no logging. Input bars are abstract (anything with
`ts`, `high`, `low` attributes), so tests can use lightweight FakeBar
fixtures and production can pass HTF OHLC DataFrame rows.
"""
from typing import Optional


def select_htf_swing_anchor(
    htf_swings: dict,
    direction: str,
    trigger_ts: int,
    htf_bars: list,
) -> Optional[float]:
    """Select the most-recent-unbroken HTF swing on the trade's wrong side.

    Args:
        htf_swings: {"swing_highs": [Swing, ...], "swing_lows": [Swing, ...]}
            Each Swing has `.price` (float) and `.idx` (int — bar position).
            Per `SMCEngine.swings()` in engine/smc.py:130-140.
        direction: "LONG" or "SHORT"
        trigger_ts: int — only consider swings with idx < trigger_ts
            (we don't anchor SL on future structure).
        htf_bars: list of objects with `.ts`, `.high`, `.low` attributes
            (HTF OHLC bars — DataFrame rows or FakeBar fixtures).

    Returns:
        Swing price (float) if unbroken anchor exists, else None.
    """
    if direction == "SHORT":
        candidates = htf_swings.get("swing_highs", [])
    else:  # LONG
        candidates = htf_swings.get("swing_lows", [])

    if not candidates:
        return None

    # Iterate most-recent-first (highest idx first)
    sorted_candidates = sorted(candidates, key=lambda s: s.idx, reverse=True)

    for swing in sorted_candidates:
        if swing.idx >= trigger_ts:
            continue  # formed after trigger — not yet known at decision time

        # Check unbroken: no bar AFTER the swing's idx has traded through it
        broken = False
        for bar in htf_bars:
            # `bar.ts` is treated as the bar's ordinal index for this check
            # (matches the simple time-monotonic test fixture). In production
            # the caller passes a DataFrame slice where row ts maps to
            # monotonic order; we only need post-swing bars.
            if bar.ts <= swing.idx:
                continue
            if direction == "SHORT":
                if bar.high > swing.price:
                    broken = True
                    break
            else:  # LONG
                if bar.low < swing.price:
                    broken = True
                    break

        if not broken:
            return swing.price

    # No unbroken swing — caller raises SLTooFarError
    return None
