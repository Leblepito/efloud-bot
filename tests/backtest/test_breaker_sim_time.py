"""Backtest breaker must run on sim-time, never on the wall clock.

Repro (2026-11-07 SOL/USDT 41d run): closed trades were recorded with the wall-clock
timestamp and the v2 entry gate called breaker.check(now=None). Every simulated
trade then counted as "today", so the daily-loss check summed the whole run and
tripped with a wall-clock resume time, blocking every remaining simulated bar.
Live passes now=None everywhere, so live behaviour is unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from engine.safe_orchestrator import SafeOrchestrator
from engine.safety.breaker import CircuitBreaker


def _orch(breaker):
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.breaker = breaker
    closed = SimpleNamespace(is_open=False, closed_at="x", realized_pnl=-150.0)
    orch.lifecycle = SimpleNamespace(positions=[closed])
    return orch, closed


def _breaker():
    return CircuitBreaker(daily_loss_pct_limit=10.0, weekly_drawdown_pct_limit=90.0,
                          consecutive_loss_limit=99, starting_balance=1000.0)


def test_closed_trade_is_recorded_at_sim_time():
    br = _breaker()
    orch, pos = _orch(br)
    sim = datetime(2026, 10, 1, 12, 0)
    actions = []
    orch._report_closed_to_breaker(actions, now=sim)
    assert br.trades_today[0]["ts"] == sim
    assert pos._reported_to_breaker is True
    assert actions == ["Recorded PnL $-150.00 to breaker"]


def test_old_sim_loss_does_not_count_as_today_days_later():
    br = _breaker()
    orch, _ = _orch(br)
    orch._report_closed_to_breaker([], now=datetime(2026, 10, 1, 12, 0))
    # -15% on 10-01; four sim-days later the daily window must be clean.
    assert br.check(now=datetime(2026, 10, 5, 12, 0)).can_trade is True


def test_live_path_keeps_wall_clock_when_now_is_none():
    br = _breaker()
    orch, _ = _orch(br)
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    orch._report_closed_to_breaker([], now=None)
    assert br.trades_today[0]["ts"] >= before.replace(microsecond=0)


def test_reported_position_is_not_recorded_twice():
    br = _breaker()
    orch, _ = _orch(br)
    orch._report_closed_to_breaker([], now=datetime(2026, 10, 1))
    orch._report_closed_to_breaker([], now=datetime(2026, 10, 1))
    assert len(br.trades_today) == 1


def test_v2_entry_gate_checks_breaker_at_cycle_time():
    seen = []

    def check(now=None):
        seen.append(now)
        return SimpleNamespace(can_trade=False, state=SimpleNamespace(value="TRIPPED"))

    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"engine": {"smc_v2_symbols": ["ETH/USDT"], "smc_v2_shadow": False}}
    orch.breaker = SimpleNamespace(check=check)
    orch.order_manager = SimpleNamespace()
    cand = SimpleNamespace(symbol="ETH/USDT", direction="LONG")

    orch._cycle_now = datetime(2026, 10, 1, 12, 0)
    assert orch._place_v2_entry_order(cand, 100.0, 100.0) is None
    orch._cycle_now = None
    assert orch._place_v2_entry_order(cand, 100.0, 100.0) is None
    assert seen == [datetime(2026, 10, 1, 12, 0), None]


def test_v2_entry_gate_defaults_to_wall_clock_without_a_cycle():
    seen = []
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"engine": {"smc_v2_symbols": ["ETH/USDT"], "smc_v2_shadow": False}}
    orch.breaker = SimpleNamespace(check=lambda now=None: seen.append(now) or SimpleNamespace(
        can_trade=False, state=SimpleNamespace(value="TRIPPED")))
    orch.order_manager = SimpleNamespace()
    orch._place_v2_entry_order(SimpleNamespace(symbol="ETH/USDT", direction="LONG"), 100.0, 100.0)
    assert seen == [None]


def test_v2_gate_honours_a_sim_time_consecutive_loss_pause():
    """Pre-fix the gate checked at wall clock, which is past any sim resume_at,
    so every consecutive-loss pause was released at once for v2 entries."""
    br = CircuitBreaker(daily_loss_pct_limit=90.0, weekly_drawdown_pct_limit=90.0,
                        consecutive_loss_limit=3, consecutive_loss_pause_minutes=120,
                        starting_balance=1000.0)
    t0 = datetime(2026, 10, 1, 12, 0)
    for _ in range(3):
        br.record_trade(-1.0, timestamp=t0)
    assert br.check(now=t0).can_trade is False

    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"engine": {"smc_v2_symbols": ["ETH/USDT"], "smc_v2_shadow": False}}
    orch.breaker = br
    orch.order_manager = SimpleNamespace()
    orch._cycle_now = datetime(2026, 10, 1, 13, 0)  # inside the 120-minute pause
    assert orch._place_v2_entry_order(SimpleNamespace(symbol="ETH/USDT", direction="LONG"),
                                      100.0, 100.0) is None
    assert br.status.state.value != "OPEN", "the pause must not be released by the v2 gate"


def test_tripped_status_is_judged_at_the_sim_time_it_was_checked():
    br = CircuitBreaker(daily_loss_pct_limit=90.0, weekly_drawdown_pct_limit=90.0,
                        consecutive_loss_limit=3, consecutive_loss_pause_minutes=120,
                        starting_balance=1000.0)
    t0 = datetime(2026, 10, 1, 12, 0)
    for _ in range(3):
        br.record_trade(-1.0, timestamp=t0)
    tripped = br.check(now=t0)
    assert tripped.state.value == "TRIPPED" and tripped.as_of == t0
    assert tripped.can_trade is False                      # pause runs to 14:00 sim-time
    assert br.check(now=datetime(2026, 10, 1, 13, 59)).can_trade is False
    assert br.check(now=datetime(2026, 10, 1, 14, 0)).can_trade is True


def test_live_check_keeps_wall_clock_semantics():
    br = CircuitBreaker(daily_loss_pct_limit=90.0, weekly_drawdown_pct_limit=90.0,
                        consecutive_loss_limit=3, consecutive_loss_pause_minutes=120,
                        starting_balance=1000.0)
    for _ in range(3):
        br.record_trade(-1.0)
    status = br.check()                                    # live: now=None
    assert status.state.value == "TRIPPED" and status.as_of is None
    assert status.can_trade is False                       # resume is 120 real minutes away
    status.resume_at = datetime(2000, 1, 1)                # a pause that has elapsed in real time
    assert status.can_trade is True


# ── Weekly peak (peak_set_at) on sim-time — follow-up of 2026-11-07 ──────────

def _weekly_breaker():
    return CircuitBreaker(daily_loss_pct_limit=90.0, weekly_drawdown_pct_limit=25.0,
                          consecutive_loss_limit=99, starting_balance=1000.0)


def test_weekly_peak_set_in_sim_time_rebases_after_seven_sim_days():
    """Pre-fix sync_balance stamped the peak with the wall clock, which is always
    after sim-time, so the 7-day rebase never happened and the weekly limit became
    an all-time drawdown limit in backtests."""
    br = _weekly_breaker()
    t0 = datetime(2026, 10, 1, 12, 0)
    br.sync_balance(1100.0, now=t0)                       # new peak at sim t0
    assert br.peak_set_at == t0
    br.sync_balance(820.0, now=t0 + timedelta(days=8))    # -25.5 % vs an 8-day-old peak
    status = br.check(now=t0 + timedelta(days=8))
    assert status.state.value != "HALTED"
    assert br.peak_balance == 820.0                       # rebased like live after 7 days


def test_initial_wall_clock_peak_is_clamped_to_sim_time():
    br = _weekly_breaker()                                # peak 1000 stamped with the wall clock
    t0 = datetime(2026, 10, 1, 12, 0)
    br.check(now=t0)
    assert br.peak_set_at == t0                           # a peak cannot sit in the sim future
    br.sync_balance(740.0, now=t0 + timedelta(days=8))    # -26 % vs the 8-day-old start
    assert br.check(now=t0 + timedelta(days=8)).state.value != "HALTED"


def test_weekly_limit_still_halts_inside_seven_sim_days():
    br = _weekly_breaker()
    t0 = datetime(2026, 10, 1, 12, 0)
    br.sync_balance(1100.0, now=t0)
    br.sync_balance(820.0, now=t0 + timedelta(days=3))
    assert br.check(now=t0 + timedelta(days=3)).state.value == "HALTED"


def test_live_peak_stays_on_the_wall_clock():
    br = _weekly_breaker()
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    br.sync_balance(1100.0)                               # live: no now
    assert br.peak_set_at >= before.replace(microsecond=0)
    stamped = br.peak_set_at
    br.check()                                            # live check must not move it
    assert br.peak_set_at == stamped


def test_orchestrator_syncs_balance_at_cycle_time():
    import inspect

    src = inspect.getsource(SafeOrchestrator.run_cycle)
    assert "self.breaker.sync_balance(balance, now=now)" in src


def test_tz_aware_now_is_normalized_for_the_weekly_peak():
    br = _weekly_breaker()
    t0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    br.check(now=t0)
    br.sync_balance(1100.0, now=t0 + timedelta(days=1))
    assert br.peak_set_at.tzinfo is None and br.peak_set_at == datetime(2026, 10, 2, 12, 0)
    assert br.check(now=t0 + timedelta(days=2)).state.value == "OPEN"
    br.sync_balance(800.0, now=t0 + timedelta(days=9))   # -27 % vs an 8-day-old peak → rebase
    assert br.check(now=t0 + timedelta(days=9)).state.value != "HALTED"
    assert br.peak_set_at.tzinfo is None                  # the rebase stores naive UTC too
    assert br.check(now=t0 + timedelta(days=10)).can_trade is True   # no naive/aware TypeError
