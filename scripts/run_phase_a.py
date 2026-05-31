"""Phase A — strategy validation runs.

Runs per-symbol 365-day backtest for all 10 phase2_1k symbols, then a portfolio
run with all 10 symbols sharing balance. Aggregates results into a markdown
summary at docs/results/{date}-phase-A-validation-{variant}.md.

Usage:
  python -m scripts.run_phase_a                                       # default config
  python -m scripts.run_phase_a --config configs/config.phase2_1k_h1a_conf60.yaml
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import yaml

from backtest.engine import run_backtest
from backtest.reproducibility import capture_provenance
from backtest.cli import _load_data_for_period

# Default symbol list — overridden by config's symbols.fixed_core when provided.
# Kept here as a fallback for configs without an explicit symbol section.
DEFAULT_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "DOGE/USDT", "SOL/USDT",
    "BNB/USDT", "TRX/USDT", "LINK/USDT", "BCH/USDT", "ADA/USDT",
]
PERIOD_DAYS = 365
INITIAL_BALANCE = 2000.0
DEFAULT_CONFIG_PATH = "configs/config.phase2_1k.yaml"

# step_every_n_bars=4 → 4x faster than step=1 (every 4 bars = 1h cadence on 15min TF).
# Initial step=1 estimate was ~30h total. step=4 brings this to ~7-8h, with no
# meaningful loss of fidelity: live bot's actual cycle interval (30s) on a 15min
# entry TF means 30 cycles repeat the same bar — only every ~30 cycles does a new
# bar arrive, so step=2-3 in backtest already over-samples vs reality. step=4 is
# close to live cadence + comfortably faster.
STEP_EVERY_N_BARS = 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A strategy validation driver")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH,
                        help="Config YAML path (default: configs/config.phase2_1k.yaml)")
    args = parser.parse_args()
    config_path = args.config

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    from data.timeframes import resolve_timeframes
    resolve_timeframes(cfg)
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]

    # Symbol list resolution: prefer config's symbols.fixed_core (so aggressive_v1
    # with 21 symbols works without code changes), fall back to DEFAULT_SYMBOLS.
    symbols_from_cfg = cfg.get("symbols", {}).get("fixed_core") if isinstance(cfg.get("symbols"), dict) else None
    SYMBOLS = symbols_from_cfg if symbols_from_cfg else DEFAULT_SYMBOLS

    # Variant tag for output dirs: strip "config." prefix from filename stem
    variant_tag = Path(config_path).stem.replace("config.", "", 1)

    today = time.strftime("%Y-%m-%d")
    phase_dir = Path(f"reports/backtests/phase_a_{today}_{variant_tag}_{uuid.uuid4().hex[:6]}")
    phase_dir.mkdir(parents=True, exist_ok=True)
    capture_provenance(phase_dir)

    per_symbol = {}
    print(f"=== Phase A — per-symbol {PERIOD_DAYS}d ===")
    for symbol in SYMBOLS:
        t0 = time.time()
        print(f"  [{symbol}] running...", end=" ", flush=True)
        data = _load_data_for_period([symbol], tfs, PERIOD_DAYS)
        result = run_backtest(
            symbols=[symbol], data=data, config=cfg, initial_balance=INITIAL_BALANCE,
            step_every_n_bars=STEP_EVERY_N_BARS,
        )
        per_symbol[symbol] = result
        elapsed = time.time() - t0
        print(
            f"{result.get('total_trades', 0)} trades, "
            f"return={result.get('total_return_pct', 0)}%, "
            f"DD={result.get('max_drawdown_pct', 0)}%, "
            f"PF={result.get('profit_factor', 0)}  "
            f"({elapsed:.0f}s)"
        )
        # Save individual result
        (phase_dir / f"{symbol.replace('/', '_')}_per_symbol.json").write_text(
            json.dumps(result, indent=2, default=str)
        )

    print(f"\n=== Phase A — portfolio (all {len(SYMBOLS)} symbols) ===")
    t0 = time.time()
    data_portfolio = _load_data_for_period(SYMBOLS, tfs, PERIOD_DAYS)
    portfolio_result = run_backtest(
        symbols=SYMBOLS, data=data_portfolio, config=cfg, initial_balance=INITIAL_BALANCE,
        step_every_n_bars=STEP_EVERY_N_BARS,
    )
    elapsed = time.time() - t0
    print(
        f"  {portfolio_result.get('total_trades', 0)} trades, "
        f"return={portfolio_result.get('total_return_pct', 0)}%, "
        f"DD={portfolio_result.get('max_drawdown_pct', 0)}%, "
        f"PF={portfolio_result.get('profit_factor', 0)}  "
        f"({elapsed:.0f}s)"
    )
    (phase_dir / "portfolio.json").write_text(
        json.dumps(portfolio_result, indent=2, default=str)
    )

    # Build markdown summary
    lines = [
        f"# Phase A — Strategy Validation ({today})",
        "",
        f"**Config:** `{config_path}` ($2000 + 5x + 2.0% notional cap = $200/trade)",
        f"**Period:** {PERIOD_DAYS} days",
        f"**Initial balance:** ${INITIAL_BALANCE:,.0f}",
        "",
        "## Per-symbol results",
        "",
        "| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Skipped Cycles |",
        "|--------|-------:|------:|---------:|---------:|---:|------------:|---------------:|",
    ]
    for symbol in SYMBOLS:
        r = per_symbol[symbol]
        lines.append(
            f"| {symbol} | {r.get('total_trades', 0)} | "
            f"{r.get('win_rate', 0)} | {r.get('total_return_pct', 0)} | "
            f"{r.get('max_drawdown_pct', 0)} | {r.get('profit_factor', 0)} | "
            f"{r.get('sharpe_like', 0)} | {r.get('skipped_cycles', 0)} |"
        )

    pr = portfolio_result
    lines.extend([
        "",
        "## Portfolio (all 10 symbols)",
        "",
        f"- **Total trades:** {pr.get('total_trades', 0)}",
        f"- **Win rate:** {pr.get('win_rate', 0)}%",
        f"- **Total return:** {pr.get('total_return_pct', 0)}%",
        f"- **Max DD (MTM):** {pr.get('max_drawdown_pct', 0)}%",
        f"- **Profit factor:** {pr.get('profit_factor', 0)}",
        f"- **Sharpe-like:** {pr.get('sharpe_like', 0)}",
        f"- **Final balance:** ${pr.get('final_balance', 0):,.2f}",
        f"- **Peak balance:** ${pr.get('peak_balance', 0):,.2f}",
        "",
        "## Ranking (by total_return_pct)",
        "",
    ])
    ranked = sorted(per_symbol.items(), key=lambda kv: kv[1].get("total_return_pct", 0), reverse=True)
    for sym, r in ranked:
        lines.append(f"- **{sym}**: {r.get('total_return_pct', 0)}% ({r.get('total_trades', 0)} trades)")
    lines.extend([
        "",
        "## Recommendations (next steps)",
        "",
        "- **Strongest 3 (focus candidates):** " + ", ".join(s for s, _ in ranked[:3]),
        "- **Weakest 3 (drop candidates):** " + ", ".join(s for s, _ in ranked[-3:]),
        "- **Phase C grid:** consider running the confluence × notional grid on the strongest 5-7 symbols only.",
        "",
        f"## Reports directory",
        f"`{phase_dir}`",
        "",
    ])

    summary_path = Path("docs/results") / f"{today}-phase-A-validation-{variant_tag}.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSummary written to: {summary_path}")
    print(f"Per-run JSONs in: {phase_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
