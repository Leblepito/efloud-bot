"""Per-bar MAE/MFE tracking on engine.lifecycle.Position.

Background: PR #51 + PR #52 wired the journal writes but leave mae_pct/
mfe_pct at 0 in every snapshot — Phase 0 evidence then cannot separate
H2 (SL too tight) from H3 (price ran far past SL). This PR adds per-bar
update_excursion() so by the time a Position closes, its MAE/MFE
reflect the actual price path.

MAE = Max Adverse Excursion (% from avg_entry against the trade direction).
MFE = Max Favorable Excursion (% from avg_entry in the trade direction).

LONG: adverse = bar's low below avg, favorable = bar's high above avg.
SHORT: adverse = bar's high above avg, favorable = bar's low below avg.
"""
import pytest

from engine.lifecycle import PositionLifecycle


@pytest.fixture
def long_position():
    lc = PositionLifecycle()
    return lc.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0,
        sl=95.0, tp1=105.0, tp2=110.0,
    )


@pytest.fixture
def short_position():
    lc = PositionLifecycle()
    return lc.open_position(
        symbol="BTC/USDT", direction="SHORT",
        entry_price=100.0, size=1.0,
        sl=105.0, tp1=95.0, tp2=90.0,
    )


# ── 1. Initial state ───────────────────────────────────────────────────────

def test_position_initial_mae_mfe_zero(long_position):
    """A freshly-opened position has mae_pct=mfe_pct=0 (no bars seen yet)."""
    assert long_position.mae_pct == 0.0
    assert long_position.mfe_pct == 0.0


# ── 2. LONG direction ──────────────────────────────────────────────────────

def test_long_update_excursion_low_below_avg_increases_mae(long_position):
    """LONG @ avg=100. Bar low=97 → MAE = (100-97)/100 = 3%."""
    long_position.update_excursion(high=101.0, low=97.0)
    assert long_position.mae_pct == pytest.approx(3.0, rel=1e-4)


def test_long_update_excursion_high_above_avg_increases_mfe(long_position):
    """LONG @ avg=100. Bar high=104 → MFE = (104-100)/100 = 4%."""
    long_position.update_excursion(high=104.0, low=99.5)
    assert long_position.mfe_pct == pytest.approx(4.0, rel=1e-4)


# ── 3. SHORT direction ─────────────────────────────────────────────────────

def test_short_update_excursion_high_above_avg_increases_mae(short_position):
    """SHORT @ avg=100. Bar high=103 → MAE = (103-100)/100 = 3%."""
    short_position.update_excursion(high=103.0, low=99.0)
    assert short_position.mae_pct == pytest.approx(3.0, rel=1e-4)


def test_short_update_excursion_low_below_avg_increases_mfe(short_position):
    """SHORT @ avg=100. Bar low=96 → MFE = (100-96)/100 = 4%."""
    short_position.update_excursion(high=100.5, low=96.0)
    assert short_position.mfe_pct == pytest.approx(4.0, rel=1e-4)


# ── 4. Monotonic max behavior ──────────────────────────────────────────────

def test_update_excursion_monotonic_mae_only_grows(long_position):
    """MAE must not decrease when a later bar shows a smaller adverse move."""
    long_position.update_excursion(high=101.0, low=95.0)   # MAE = 5%
    long_position.update_excursion(high=102.0, low=99.0)   # would be only 1%
    assert long_position.mae_pct == pytest.approx(5.0, rel=1e-4)


def test_update_excursion_monotonic_mfe_only_grows(long_position):
    """MFE must not decrease when a later bar shows a smaller favorable move."""
    long_position.update_excursion(high=108.0, low=99.0)   # MFE = 8%
    long_position.update_excursion(high=102.0, low=99.5)   # would be only 2%
    assert long_position.mfe_pct == pytest.approx(8.0, rel=1e-4)


# ── 5. Edge cases ──────────────────────────────────────────────────────────

def test_update_excursion_ignores_invalid_inputs(long_position):
    """Zero/negative price inputs are ignored; MAE/MFE remain at last good value."""
    long_position.update_excursion(high=104.0, low=98.0)
    before_mae = long_position.mae_pct
    before_mfe = long_position.mfe_pct
    long_position.update_excursion(high=0.0, low=0.0)
    long_position.update_excursion(high=-1.0, low=-1.0)
    assert long_position.mae_pct == before_mae
    assert long_position.mfe_pct == before_mfe


# ── 6. Orchestrator journal handoff ────────────────────────────────────────

def test_journal_record_exit_helper_passes_mae_mfe_from_position(tmp_path):
    """When _journal_record_exit is called, the position's accumulated
    mae_pct/mfe_pct must reach the journal as keyword arguments."""
    from unittest.mock import MagicMock
    import yaml
    from engine import SafeOrchestrator
    from engine.journal import TradeJournal

    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    mock_journal = MagicMock(spec=TradeJournal)
    orch = SafeOrchestrator(
        cfg, state_dir=str(tmp_path), freshness_check=False,
        trade_journal=mock_journal,
    )
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0, sl=95.0, tp1=105.0, tp2=110.0,
    )
    pos.update_excursion(high=108.0, low=96.0)   # MAE=4, MFE=8
    orch.lifecycle.close_position(pos, price=104.0, reason="TP1")

    orch._journal_record_exit(pos, exit_price=104.0, reason="TP1")

    call = mock_journal.record_exit.call_args
    kw = call.kwargs if call.kwargs else {}
    assert kw.get("mae_pct") == pytest.approx(4.0, rel=1e-4) or (
        call.args and len(call.args) > 5 and call.args[6] == pytest.approx(4.0, rel=1e-4)
    )
    assert kw.get("mfe_pct") == pytest.approx(8.0, rel=1e-4) or (
        call.args and len(call.args) > 4 and call.args[5] == pytest.approx(8.0, rel=1e-4)
    )


# ── 7. Orchestrator run_cycle integration ──────────────────────────────────

def test_run_cycle_updates_open_position_excursion(tmp_path):
    """run_cycle must call update_excursion(high, low) on every open
    position in the symbol so MAE/MFE accumulate across bars even if no
    explicit signal fires that cycle."""
    import yaml
    import pandas as pd
    from engine import SafeOrchestrator

    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    orch = SafeOrchestrator(cfg, state_dir=str(tmp_path), freshness_check=False)
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0, sl=95.0, tp1=105.0, tp2=110.0,
    )
    assert pos.mae_pct == 0.0
    assert pos.mfe_pct == 0.0

    idx = pd.date_range("2026-01-01", periods=300, freq="15min")
    df = pd.DataFrame({
        "open": [100.0] * 300,
        "high": [110.0] * 300,
        "low": [90.0] * 300,
        "close": [100.0] * 300,
        "volume": [1.0] * 300,
    }, index=idx)
    orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000)

    # LONG @ avg=100: low=90 → MAE = 10%; high=110 → MFE = 10%.
    assert pos.mae_pct == pytest.approx(10.0, rel=1e-4)
    assert pos.mfe_pct == pytest.approx(10.0, rel=1e-4)
