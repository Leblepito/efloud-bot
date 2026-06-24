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


# --- C1 observability: the swallowed balance-fetch error must be LOGGED ---
# The capital-loss core (fail-closed sizing) is already covered above; the only
# residual is that bot_runner._scan_universe swallowed the fetch error silently.

def _live_runner_with_failing_balance():
    """Real BotRunner driven through _scan_universe with a client whose
    get_balance() always raises — the transient Binance hiccup C1 describes."""
    from unittest.mock import MagicMock
    from backend.bot_runner import BotRunner

    runner = BotRunner()
    runner.cfg = {
        "operation": {"dry_run": False},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m", "kline_limit": 50},
    }
    client = MagicMock()
    client.fetch_ohlcv.return_value = pd.DataFrame(
        {"open": [100], "high": [101], "low": [99], "close": [100], "volume": [1.0]}
    )
    client.get_balance.side_effect = RuntimeError("transient -1001 / network")
    runner.client = client
    runner.universe = MagicMock()
    runner.universe.resolve.return_value = ["SOL/USDT"]
    runner.orch = MagicMock()
    runner.order_mgr = MagicMock()
    runner.loop = None
    return runner, client


def test_balance_fetch_error_is_logged_not_swallowed(caplog):
    """C1 observability: a live balance-fetch error must (a) leave balance None
    so the orchestrator fail-closes (no fabricated $10k), and (b) emit a WARNING
    so the silent trading-halt is visible — no more bare ``except: pass``."""
    import logging

    runner, _client = _live_runner_with_failing_balance()
    with caplog.at_level(logging.WARNING, logger="efloud.runner"):
        runner._scan_universe()  # must not raise

    runner.orch.run_cycle.assert_called_once()
    assert runner.orch.run_cycle.call_args.kwargs["balance"] is None, (
        "live balance-fetch failure must pass balance=None (fail-closed), "
        "never a fabricated value"
    )
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "balance" in r.message.lower()
        and "fetch failed" in r.message.lower()
        and "SOL/USDT" in r.message
        for r in warns
    ), f"expected a balance-fetch-failed WARNING naming the symbol, got: {[r.message for r in warns]}"
