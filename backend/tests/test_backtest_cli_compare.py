"""CLI 'compare' subcommand argparse smoke test (PR #S4)."""
from __future__ import annotations

from backtest.cli import build_parser


def test_compare_subcommand_registered():
    parser = build_parser()
    args = parser.parse_args([
        "compare",
        "--config", "configs/config.phase2_1k.yaml",
        "--symbols", "ETH/USDT,BTC/USDT",
        "--period-days", "7",
    ])
    assert args.cmd == "compare"
    assert args.symbols == "ETH/USDT,BTC/USDT"
    assert args.period_days == 7
    assert args.balance == 2000.0  # default


def test_existing_subcommands_preserved():
    """Regression: refactor must not break single/portfolio/grid."""
    parser = build_parser()
    single = parser.parse_args([
        "single", "--symbol", "ETH/USDT", "--period-days", "30",
    ])
    assert single.cmd == "single"
    assert single.symbol == "ETH/USDT"

    port = parser.parse_args([
        "portfolio", "--symbols", "ETH/USDT,BTC/USDT", "--period-days", "30",
    ])
    assert port.cmd == "portfolio"
    assert port.symbols == "ETH/USDT,BTC/USDT"


def test_compare_balance_override():
    parser = build_parser()
    args = parser.parse_args([
        "compare",
        "--config", "configs/config.phase2_1k.yaml",
        "--symbols", "ETH/USDT",
        "--period-days", "7",
        "--balance", "5000",
    ])
    assert args.balance == 5000.0
