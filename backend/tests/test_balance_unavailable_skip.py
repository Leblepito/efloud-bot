"""C4 regression: a failed balance fetch on a LIVE cycle must NOT fabricate a
$10k balance and size new entries against it.

Background: ``bot_runner._scan_universe`` fetches the balance inside a
``try/except: pass``; on failure ``balance`` stays ``None`` and is passed to
``run_cycle``. ``safe_orchestrator`` then did
``actual_balance = balance if balance is not None else 10000.0`` — so a single
transient balance-read hiccup sized the trade (and ran PositionGuard) against a
fabricated $10,000 instead of the real ~$2,000 wallet (≈5x over-notional).

Fix: when balance is unavailable on a live (non-dry-run) cycle, treat it like
stale data → manage existing positions but open NO new entries this cycle.
Dry-run/backtest pass an explicit balance, so None there is exempt.
"""
import pandas as pd
import pytest
import yaml

from engine import SafeOrchestrator


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _orch(cfg, tmp_path):
    return SafeOrchestrator(
        cfg, state_dir=str(tmp_path), freshness_check=False, persist=False,
    )


def _flat_df():
    idx = pd.date_range("2026-01-01", periods=300, freq="15min")
    return pd.DataFrame(
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1.0},
        index=idx,
    )


def test_live_balance_none_blocks_new_entries(base_config, tmp_path):
    base_config["operation"]["dry_run"] = False
    orch = _orch(base_config, tmp_path)
    df = _flat_df()
    result = orch.run_cycle("BTC/USDT", df, df, df, df, balance=None)
    assert result.can_trade is False
    assert any("balance unavailable" in w.lower() for w in result.warnings), (
        f"expected a balance-unavailable warning, got: {result.warnings}"
    )


def test_live_balance_present_emits_no_balance_warning(base_config, tmp_path):
    base_config["operation"]["dry_run"] = False
    orch = _orch(base_config, tmp_path)
    df = _flat_df()
    result = orch.run_cycle("BTC/USDT", df, df, df, df, balance=2000.0)
    assert not any("balance unavailable" in w.lower() for w in result.warnings)


def test_dry_run_balance_none_is_exempt(base_config, tmp_path):
    """Dry-run/backtest legitimately run without a live balance — no skip."""
    base_config["operation"]["dry_run"] = True
    orch = _orch(base_config, tmp_path)
    df = _flat_df()
    result = orch.run_cycle("BTC/USDT", df, df, df, df, balance=None)
    assert not any("balance unavailable" in w.lower() for w in result.warnings)
