"""Test main.py OrderManager wiring matches config.yaml parameters.

These tests verify that main.py CLI mode constructs OrderManager with
the correct parameters from config.yaml, matching bot_runner.py wiring.

Bug: main.py was passing hedge_mode=False (default) even when config
had hedge_mode: true. In hedge mode, Binance requires positionSide
parameter on SL/TP orders (not reduceOnly). Wrong mode → SL/TP rejected.
"""
from unittest.mock import MagicMock, patch
import pytest


class TestMainOMWiring:
    """Verify OrderManager receives correct parameters from config."""

    def _make_config(self, hedge_mode=False, state_dir="./state"):
        """Minimal valid config for main.py startup."""
        return {
            "exchange": {
                "testnet": True, "leverage": 3, "margin_mode": "ISOLATED",
                "hedge_mode": hedge_mode, "market_type": "futures",
            },
            "operation": {
                "dry_run": True, "check_interval_sec": 1,
                "state_dir": state_dir, "log_level": "WARNING",
                "log_file": "/dev/null", "reports_dir": "/tmp/reports",
            },
            "risk": {"risk_per_trade_pct": 1.0, "min_confluence": 50, "min_rr": 1.5},
            "safety": {"min_seconds_between_symbol_fetches": 1.0,
                       "starting_balance": 1000, "max_position_notional_pct": 3.0},
            "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m", "kline_limit": 100},
            "symbols": {"mode": "fixed", "fixed_core": ["BTC/USDT"]},
            "structure": {"swing_lookback": 4, "ob_sequential": 5,
                          "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
            "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786},
        }

    def _run_main_with_patches(self, config):
        """Run main() with all external dependencies mocked."""
        with (
            patch("main.BinanceClient") as mock_client_cls,
            patch("main.OrderManager") as mock_om_cls,
            patch("main.SafeOrchestrator") as mock_orch_cls,
            patch("main.SymbolUniverse") as mock_universe_cls,
            patch("main.TradeJournal"),
            patch("main.load_config", return_value=config),
            patch("main.resolve_credentials", return_value=("key", "secret")),
            patch("main.validate_config", return_value=True),
            patch("main.MainnetGuard.check", return_value=True),
            patch("main.GracefulShutdown") as mock_shutdown_cls,
            patch("main.print_banner"),
            patch("main.setup_logging"),
        ):
            mock_shutdown = MagicMock()
            mock_shutdown.stop = True  # Exit immediately after 0 cycles
            mock_shutdown_cls.return_value = mock_shutdown

            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_universe = MagicMock()
            mock_universe.resolve.return_value = ["BTC/USDT"]
            mock_universe_cls.return_value = mock_universe

            from main import main
            try:
                main()
            except SystemExit:
                pass

            return mock_om_cls

    def test_om_receives_hedge_mode_true_from_config(self):
        """OrderManager must receive hedge_mode=True when config has it."""
        cfg = self._make_config(hedge_mode=True)
        mock_om_cls = self._run_main_with_patches(cfg)

        om_call = mock_om_cls.call_args
        assert om_call.kwargs.get("hedge_mode") is True, \
            f"OrderManager should receive hedge_mode=True, got: {om_call.kwargs}"

    def test_om_receives_hedge_mode_false_from_config(self):
        """OrderManager must receive hedge_mode=False when config has it."""
        cfg = self._make_config(hedge_mode=False)
        mock_om_cls = self._run_main_with_patches(cfg)

        om_call = mock_om_cls.call_args
        assert om_call.kwargs.get("hedge_mode") is False, \
            f"OrderManager should receive hedge_mode=False, got: {om_call.kwargs}"

    def test_om_receives_state_dir_from_config(self):
        """OrderManager must receive state_dir for crash recovery."""
        cfg = self._make_config(state_dir="./test_state_dir")
        mock_om_cls = self._run_main_with_patches(cfg)

        om_call = mock_om_cls.call_args
        assert om_call.kwargs.get("state_dir") == "./test_state_dir", \
            f"OrderManager should receive state_dir='./test_state_dir', got: {om_call.kwargs}"

    def test_om_receives_orphan_protector(self):
        """OrderManager must receive orphan_protector for orphan detection."""
        cfg = self._make_config()
        mock_om_cls = self._run_main_with_patches(cfg)

        om_call = mock_om_cls.call_args
        # In dry_run=True, orphan_protector may be None (acceptable),
        # but the kwarg must be present
        assert "orphan_protector" in om_call.kwargs, \
            f"OrderManager kwargs missing orphan_protector: {om_call.kwargs}"
