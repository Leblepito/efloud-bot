"""SMC v2 setup rejection exceptions.

These are raised by sl_calc.calc_sl and tp_calc.calc_tp_targets to signal
that a setup must be rejected. The caller (orchestrator in PR #S3) catches
them and counts the rejection reason (see spec §6).
"""


class SLTooFarError(ValueError):
    """Raised when structural SL distance exceeds max_sl_atr * ATR.

    Setup must be rejected — clamping to the max would invalidate the SMC
    structure (SL placed at an unrelated price level).
    """

    def __init__(self, stop_dist: float, max_dist: float):
        self.stop_dist = stop_dist
        self.max_dist = max_dist
        super().__init__(
            f"Structural SL distance {stop_dist:.6f} exceeds max {max_dist:.6f} "
            f"(max_sl_atr * ATR). Setup rejected."
        )


class InsufficientTPDistanceError(ValueError):
    """Raised when the nearest valid liquidity/FVG target is closer than min_rr * risk.

    Setup must be rejected — projecting a synthetic TP at min_rr would ignore
    the real structural target and produce unrealistic expectations.
    """

    def __init__(self, nearest: float, required: float):
        self.nearest = nearest
        self.required = required
        super().__init__(
            f"Nearest TP candidate {nearest:.6f} is within required min distance "
            f"{required:.6f}. Setup rejected."
        )
