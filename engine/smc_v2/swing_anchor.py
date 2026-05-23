"""HTF swing anchor selection for SMC v2 structural SL.

Per spec §10 #1:
  Return the most recent unbroken HTF swing on the 'wrong side' of the trade.

  - For SHORT: wrong side = swing_highs above entry. Unbroken = no HTF bar
    formed after the swing has traded above the swing's price.
  - For LONG: mirror — swing_lows below entry; unbroken = no bar.low < price.

  Returns the swing's price (float), or None if no unbroken swing exists.
  When None, the caller raises SLTooFarError (setup rejected per spec).

API contract (load-bearing for PR #S3b):
  The function operates entirely on the **ordinal-bar-position axis**, NOT
  on a timestamp axis. Both `trigger_idx` (the trigger bar's ordinal) and
  every `bar.ordinal` MUST be integers from the same DataFrame's position
  range (e.g. produced via `df.reset_index().index.tolist()` or by enumerating
  `df.itertuples()`).

  Callers (PR #S3b orchestrator wiring) must coerce their HTF OHLC rows into
  a sequence of `BarLike` objects with `.ordinal: int`, `.high: float`,
  `.low: float`. Passing raw ms-epoch timestamps as `.ordinal` will silently
  produce wrong results because `Swing.idx` is always a small int (0..N-1).

Pure function — no I/O, no logging.
"""
from typing import Optional


def select_htf_swing_anchor(
    htf_swings: dict,
    direction: str,
    trigger_idx: int,
    htf_bars: list,
) -> Optional[float]:
    """Select the most-recent-unbroken HTF swing on the trade's wrong side.

    Args:
        htf_swings: {"swing_highs": [Swing, ...], "swing_lows": [Swing, ...]}
            Each Swing has `.price` (float) and `.idx` (int — bar ordinal).
            Per `SMCEngine.swings()` in engine/smc.py:130-140.
        direction: "LONG" or "SHORT"
        trigger_idx: int — ordinal of the CHoCH trigger bar in the HTF
            DataFrame. Only swings with `idx < trigger_idx` are considered
            (we don't anchor SL on future structure).
        htf_bars: list of objects with `.ordinal: int`, `.high: float`,
            `.low: float`. Both production HTF OHLC rows and test FakeBar
            fixtures must use the same ordinal axis as `Swing.idx`.
            **Must be sorted by ordinal ascending.**

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
        if swing.idx >= trigger_idx:
            continue  # formed at/after trigger — not yet known at decision time

        # Check unbroken: no bar with ordinal > swing.idx has traded through.
        broken = False
        for bar in htf_bars:
            if bar.ordinal <= swing.idx:
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
