"""PR A — startup margin/leverage/position-mode enforcement.

margin-mode failure must ABORT startup (ISOLATED is a guarantee, not best-effort);
leverage failure is non-fatal; position-mode failure aborts (existing behavior).
"""


class _FailMarginClient:
    def __init__(self):
        self.calls = []

    def set_margin_mode(self, sym, mode):
        self.calls.append((sym, mode))
        raise RuntimeError("-4046 simulated hard failure")

    def set_leverage(self, sym, lev):
        pass

    def set_position_mode(self, dual_side=False):
        return True


def test_margin_mode_hard_failure_aborts_startup():
    from backend.bot_runner import _enforce_margin_setup

    client = _FailMarginClient()
    ok, err = _enforce_margin_setup(
        client, tradeable=["BTC/USDT"], margin_mode="ISOLATED",
        leverage=5, hedge_mode=False,
    )
    assert ok is False
    assert "margin" in err.lower()


def test_margin_mode_success_returns_ok():
    from backend.bot_runner import _enforce_margin_setup

    class _OkClient(_FailMarginClient):
        def set_margin_mode(self, sym, mode):
            self.calls.append((sym, mode))
            return True   # set_margin_mode treats benign -4046 as success internally

    client = _OkClient()
    ok, err = _enforce_margin_setup(
        client, tradeable=["BTC/USDT", "ETH/USDT"], margin_mode="ISOLATED",
        leverage=5, hedge_mode=False,
    )
    assert ok is True
    assert err == ""
    assert ("BTC/USDT", "ISOLATED") in client.calls


def test_position_mode_failure_aborts():
    from backend.bot_runner import _enforce_margin_setup

    class _PosFailClient(_FailMarginClient):
        def set_margin_mode(self, sym, mode):
            return True

        def set_position_mode(self, dual_side=False):
            return False   # Binance rejected (open positions/orders)

    ok, err = _enforce_margin_setup(
        _PosFailClient(), tradeable=["BTC/USDT"], margin_mode="ISOLATED",
        leverage=5, hedge_mode=False,
    )
    assert ok is False
    assert "position mode" in err.lower()
