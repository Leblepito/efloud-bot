"""BT-24: bars_waited counts closed LTF bars, not orchestrator ticks.

WHY THIS TEST EXISTS
--------------------
`_advance_setup_state_tick` used to run `cand.bars_waited += 1` on every call.
The orchestrator polls every `check_interval_sec` (30s in config.phase2_1k.yaml)
while the entry timeframe is 15m, so ~30 ticks land on the same bar. The
default `pullback_timeout_bars: 8` therefore expired every v2 candidate after
8 * 30s = 4 MINUTES, before the 15m bar its CHoCH fired on had even closed.
Intended lifetime is 8 * 15m = 2 hours, which is also what the BT-23 replay
measured. `current_bar_ts` was already computed and passed by run_cycle for
exactly this purpose and was simply never read.

These tests pin the behaviours that matter:
  1. repeated ticks on ONE bar    -> bars_waited increments exactly once
  2. distinct bars                -> one increment each
  3. expiry is driven by bars     -> 100 ticks on 8 bars never expires
  4. expiry still fires           -> the 9th bar expires an 8-bar timeout
  5. per-symbol bookkeeping       -> BTC's bar clock never advances ETH's
  6. terminal states untouched    -> CONFIRMED/EXPIRED never re-counted
"""
import pandas as pd
import pytest

from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec


BAR_MS = 15 * 60 * 1000
T0 = 1_700_000_000_000


# --- fixtures ---------------------------------------------------------------

def _df(bars: int = 60) -> pd.DataFrame:
    """Flat OHLC frame. Price never moves, so no zone transition can fire and
    bars_waited is the only thing under observation."""
    return pd.DataFrame({
        "open": [10050.0] * bars,
        "high": [10100.0] * bars,
        "low": [10000.0] * bars,
        "close": [10050.0] * bars,
    })


def _cand(symbol="BTC/USDT", state="AWAITING_PULLBACK", bars_waited=0):
    """Candidate whose zone sits far below price -> stays AWAITING_PULLBACK."""
    return SetupCandidate(
        symbol=symbol,
        direction="LONG",
        trigger_bar_ts=T0,
        trigger_price=10_000.0,
        htf_bias="BULL",
        target_zone=ZoneSpec(low=5_000.0, high=5_100.0, source="OTE"),
        htf_swing_anchor=4_900.0,
        bars_waited=bars_waited,
        state=state,
        confluence_score=3,
        reasons=["test"],
    )


def _orch(tmp_path, candidates, timeout_bars=None):
    from engine.safe_orchestrator import SafeOrchestrator

    smc_v2 = {"require_confirmation": True}
    if timeout_bars is not None:
        smc_v2["pullback_timeout_bars"] = timeout_bars

    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": smc_v2}
    store = SetupStateStore(path=tmp_path / "cands.json")
    store.candidates = list(candidates)
    orch.setup_state_store = store
    return orch


def _tick(orch, bar_ts, symbol="BTC/USDT", price=10_050.0):
    orch._advance_setup_state_tick(
        symbol=symbol,
        current_price=price,
        current_bar_ts=bar_ts,
        df_15m=_df(),
    )


# --- tests ------------------------------------------------------------------

class TestBarClock:

    def test_repeated_ticks_on_one_bar_count_once(self, tmp_path):
        """30 ticks inside a single 15m bar -> bars_waited == 1, not 30."""
        c = _cand()
        orch = _orch(tmp_path, [c])
        for _ in range(30):
            _tick(orch, T0)
        assert c.bars_waited == 1
        assert c.state == "AWAITING_PULLBACK"

    def test_each_new_bar_counts_once(self, tmp_path):
        """Five distinct bar timestamps -> five increments."""
        c = _cand()
        orch = _orch(tmp_path, [c])
        for i in range(5):
            _tick(orch, T0 + i * BAR_MS)
        assert c.bars_waited == 5

    def test_many_ticks_within_timeout_do_not_expire(self, tmp_path):
        """8 bars x 30 ticks = 240 ticks. Old code expired at tick 9."""
        c = _cand()
        orch = _orch(tmp_path, [c], timeout_bars=8)
        for i in range(8):
            for _ in range(30):
                _tick(orch, T0 + i * BAR_MS)
        assert c.bars_waited == 8
        assert c.state == "AWAITING_PULLBACK"

    def test_bar_past_timeout_expires(self, tmp_path):
        """The 9th bar pushes bars_waited to 9 > 8 -> EXPIRED."""
        c = _cand()
        orch = _orch(tmp_path, [c], timeout_bars=8)
        for i in range(9):
            _tick(orch, T0 + i * BAR_MS)
        assert c.bars_waited == 9
        assert c.state == "EXPIRED"

    def test_expiry_fires_on_the_bar_it_crosses(self, tmp_path):
        """Not one bar late: state flips on the same tick the limit is passed."""
        c = _cand()
        orch = _orch(tmp_path, [c], timeout_bars=3)
        _tick(orch, T0)
        _tick(orch, T0 + BAR_MS)
        _tick(orch, T0 + 2 * BAR_MS)
        assert c.state == "AWAITING_PULLBACK"
        _tick(orch, T0 + 3 * BAR_MS)
        assert c.state == "EXPIRED"

    def test_bar_clock_is_per_symbol(self, tmp_path):
        """Ticking BTC must not consume ETH's bar. Symbols are polled in one
        cycle, so a shared clock would let the first symbol eat everyone's."""
        btc = _cand(symbol="BTC/USDT")
        eth = _cand(symbol="ETH/USDT")
        orch = _orch(tmp_path, [btc, eth])

        for i in range(4):
            _tick(orch, T0 + i * BAR_MS, symbol="BTC/USDT")
        assert btc.bars_waited == 4
        assert eth.bars_waited == 0

        _tick(orch, T0, symbol="ETH/USDT")
        assert eth.bars_waited == 1
        assert btc.bars_waited == 4

    def test_default_timeout_is_eight_bars(self, tmp_path):
        """pullback_timeout_bars absent from config -> the 8 default applies to
        BARS. Pins the config knob this bot actually runs with."""
        c = _cand()
        orch = _orch(tmp_path, [c])  # no pullback_timeout_bars
        for i in range(8):
            _tick(orch, T0 + i * BAR_MS)
        assert c.state == "AWAITING_PULLBACK"
        _tick(orch, T0 + 8 * BAR_MS)
        assert c.state == "EXPIRED"

    def test_terminal_states_are_not_counted(self, tmp_path):
        """CONFIRMED/EXPIRED candidates are skipped before the increment."""
        conf = _cand(state="CONFIRMED", bars_waited=2)
        exp = _cand(state="EXPIRED", bars_waited=5)
        orch = _orch(tmp_path, [conf, exp])
        for i in range(4):
            _tick(orch, T0 + i * BAR_MS)
        assert conf.bars_waited == 2
        assert exp.bars_waited == 5
        assert conf.state == "CONFIRMED"
        assert exp.state == "EXPIRED"

    def test_store_none_short_circuits(self, tmp_path):
        """v1 safety invariant: no store -> no work, no attribute created."""
        from engine.safe_orchestrator import SafeOrchestrator

        orch = SafeOrchestrator.__new__(SafeOrchestrator)
        orch.config = {"smc_v2": {}}
        orch.setup_state_store = None
        _tick(orch, T0)
        assert not hasattr(orch, "_v2_last_bar_ts")

    def test_first_tick_after_restart_counts_as_a_bar(self, tmp_path):
        """_v2_last_bar_ts is in-memory, so a restart re-counts the current bar
        once. Documented, bounded cost: it can never SHORTEN the timeout below
        the true bar count, only lengthen the effective wait by one bar."""
        c = _cand(bars_waited=3)
        orch = _orch(tmp_path, [c])
        _tick(orch, T0)          # "restart": map empty -> counts
        assert c.bars_waited == 4
        _tick(orch, T0)          # same bar again -> no double count
        assert c.bars_waited == 4
