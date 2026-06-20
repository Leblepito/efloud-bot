"""M3 regression lock: the Order Block BODY filter uses the high-low SMA(14)
(engine/smc.py:195 `(h-l).rolling(14).mean()`), NOT a true-range ATR(14).

CLAUDE.md previously called both "ATR(14)"; PINE_SPEC §A.3/§A.4 and the code keep
them distinct (the OB gate is high-low SMA, the SL buffer is true-range ATR). This
test pins the OB gate to high-low SMA so a future "unify ATR" refactor cannot
silently swap it to true-range (which would reject this OB). Doc-only fix; this is
the guardrail. See [[reference]] PINE_SPEC §A.3.
"""
import pandas as pd

from engine.smc import SMCEngine


def _gapped_discriminating_df() -> pd.DataFrame:
    """A bull breakout whose body (3.0) is > 1.5×high-low-SMA(14) but
    < 1.5×true-range-ATR(14). An early price GAP (level 100 → 200 at bar 6)
    inflates true-range ATR (|high − prev_close| ≈ 100) far above the intrabar
    high-low SMA, so the two candidate gates disagree on this breakout."""
    rows = [{"open": 100.0, "close": 100.0, "high": 100.5, "low": 99.5, "volume": 1.0}
            for _ in range(6)]                                   # bars 0-5 @ level 100
    rows += [{"open": 200.0, "close": 200.0, "high": 200.5, "low": 199.5, "volume": 1.0}
             for _ in range(12)]                                 # bars 6-17 @ level 200 (gap at 6)
    rows.append({"open": 200.0, "close": 199.0, "high": 200.0, "low": 199.0, "volume": 1.0})  # 18 bearish
    rows.append({"open": 199.0, "close": 202.0, "high": 202.0, "low": 199.0, "volume": 1.0})  # 19 bull breakout, body=3
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="15min")
    return pd.DataFrame(rows, index=idx)


def test_ob_body_filter_uses_high_low_sma_not_true_range():
    df = _gapped_discriminating_df()
    i = len(df) - 1  # breakout bar 19
    body = abs(df["close"].iloc[i] - df["open"].iloc[i])

    # Recompute both candidate gates the way each implementation would.
    h, l, c = df["high"], df["low"], df["close"]
    hl_sma = (h - l).rolling(14).mean().iloc[i]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    tr_atr = tr.rolling(14).mean().iloc[i]

    # The case is genuinely discriminating: high-low gate ACCEPTS, true-range REJECTS.
    assert 1.5 * hl_sma < body < 1.5 * tr_atr, (
        f"frame not discriminating: body={body}, 1.5*hl_sma={1.5 * hl_sma:.3f}, "
        f"1.5*tr_atr={1.5 * tr_atr:.3f}"
    )

    obs = SMCEngine().order_blocks(df, sh=[], sl=[], trend="UNDEF")
    bulls = [o for o in obs if o.direction == "BULL"]
    assert len(bulls) == 1, (
        f"expected exactly one BULL OB (proving the gate uses high-low SMA, not "
        f"true-range ATR which would reject body={body}); got {obs}"
    )
