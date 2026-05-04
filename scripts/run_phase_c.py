"""Phase C — Confluence × Notional grid optimization runner.

Runs the 5 × 4 = 20 config grid via the existing CLI grid command,
in portfolio mode across all 10 phase2_1k symbols. Wall time ~4-6h on
4 workers (depends on per-symbol cycle skip rates).

After completion, builds a markdown summary at
docs/results/{date}-phase-C-grid-results.md with top configs by Sharpe-like.

Usage:
    python -m scripts.run_phase_c

Prerequisites:
    - Cache populated (run scripts.prefetch_data first if not)
    - Git tree clean (cmd_grid refuses dirty trees per spec §6.8)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

GRID_SPEC = "configs/grids/confluence_x_notional.yaml"
SYMBOLS = ",".join([
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "DOGE/USDT", "SOL/USDT",
    "BNB/USDT", "TRX/USDT", "LINK/USDT", "BCH/USDT", "ADA/USDT",
])
PERIOD_DAYS = 365
WORKERS = 4
BALANCE = 2000.0


def main() -> int:
    print("=== Phase C — Confluence × Notional grid ===")
    print(f"Grid spec: {GRID_SPEC}")
    print(f"Symbols: {SYMBOLS}")
    print(f"Period: {PERIOD_DAYS} days")
    print(f"Workers: {WORKERS}")
    print(f"Initial balance: ${BALANCE:,.0f}")
    print(f"\nWall time estimate: ~4-6 hours.")

    # Verify git tree is clean (cmd_grid will also check, but fail-fast)
    git_status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if git_status:
        print("\nERROR: git tree is dirty. cmd_grid refuses dirty trees per spec §6.8.")
        print("Commit or stash changes first:\n")
        print(git_status)
        return 1

    # Run the grid via the CLI
    print("\nLaunching grid...")
    t0 = time.time()
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "backtest.cli", "grid",
                "--grid", GRID_SPEC,
                "--symbols", SYMBOLS,
                "--period-days", str(PERIOD_DAYS),
                "--workers", str(WORKERS),
                "--balance", str(BALANCE),
            ],
            check=False,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user (CTRL+C). Workers should be cleaning up.")
        print("If a partial grid_* dir exists, you can re-run scripts.run_phase_c")
        print("after committing/stashing any uncommitted state — checkpoints are preserved.")
        return 130
    elapsed = time.time() - t0
    print(f"\nGrid run finished in {elapsed/60:.1f} min (exit {proc.returncode})")

    if proc.returncode != 0:
        print("Grid run failed; not generating summary.")
        return proc.returncode

    # Find the most recent grid output dir
    backtests_dir = Path("reports/backtests")
    # Filter: only dirs created AFTER our start time (5s buffer for clock skew)
    grid_dirs = sorted(
        (d for d in backtests_dir.iterdir()
         if d.is_dir() and d.name.startswith("grid_") and d.stat().st_mtime >= t0 - 5),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not grid_dirs:
        print("ERROR: no grid output dir found.")
        return 1
    out_dir = grid_dirs[0]
    print(f"Grid output: {out_dir}")

    # Load all per-config results
    configs_dir = out_dir / "configs"
    results = []
    for f in configs_dir.glob("*.json"):
        try:
            r = json.loads(f.read_text())
            if "error" not in r:
                results.append(r)
        except Exception as e:
            print(f"  warning: could not parse {f.name}: {e}")

    if not results:
        print("ERROR: no usable results in grid output.")
        return 1

    # Rank by sharpe_like, then by total_return_pct as tiebreaker
    by_sharpe = sorted(
        results,
        key=lambda r: (r.get("sharpe_like", 0), r.get("total_return_pct", 0)),
        reverse=True,
    )
    by_return = sorted(
        results,
        key=lambda r: r.get("total_return_pct", 0),
        reverse=True,
    )

    today = time.strftime("%Y-%m-%d")
    lines = [
        f"# Phase C — Confluence × Notional Grid Results ({today})",
        "",
        f"**Grid spec:** `{GRID_SPEC}`",
        f"**Symbols:** {SYMBOLS}",
        f"**Period:** {PERIOD_DAYS} days",
        f"**Initial balance:** ${BALANCE:,.0f}",
        f"**Configs evaluated:** {len(results)}",
        f"**Wall time:** {elapsed/60:.1f} min",
        f"**Grid output dir:** `{out_dir}`",
        "",
        "## Top 5 by Sharpe-like",
        "",
        "| Rank | min_confluence | max_notional_pct | Trades | Win% | Return% | Max DD% | PF | Sharpe-like |",
        "|-----:|---------------:|-----------------:|-------:|-----:|--------:|--------:|---:|------------:|",
    ]
    for i, r in enumerate(by_sharpe[:5], 1):
        lines.append(
            f"| {i} | "
            f"{r.get('risk.min_confluence', '?')} | "
            f"{r.get('safety.max_position_notional_pct', '?')} | "
            f"{r.get('total_trades', 0)} | "
            f"{r.get('win_rate', 0):.1f} | "
            f"{r.get('total_return_pct', 0):.2f} | "
            f"{r.get('max_drawdown_pct', 0):.2f} | "
            f"{r.get('profit_factor', 0):.2f} | "
            f"{r.get('sharpe_like', 0):.2f} |"
        )

    lines.extend([
        "",
        "## Top 5 by Total Return",
        "",
        "| Rank | min_confluence | max_notional_pct | Trades | Win% | Return% | Max DD% | PF | Sharpe-like |",
        "|-----:|---------------:|-----------------:|-------:|-----:|--------:|--------:|---:|------------:|",
    ])
    for i, r in enumerate(by_return[:5], 1):
        lines.append(
            f"| {i} | "
            f"{r.get('risk.min_confluence', '?')} | "
            f"{r.get('safety.max_position_notional_pct', '?')} | "
            f"{r.get('total_trades', 0)} | "
            f"{r.get('win_rate', 0):.1f} | "
            f"{r.get('total_return_pct', 0):.2f} | "
            f"{r.get('max_drawdown_pct', 0):.2f} | "
            f"{r.get('profit_factor', 0):.2f} | "
            f"{r.get('sharpe_like', 0):.2f} |"
        )

    # Stability heuristic: best Sharpe config also in top 5 by return?
    best_sharpe = by_sharpe[0]
    best_sharpe_in_top5_return = best_sharpe in by_return[:5]
    lines.extend([
        "",
        "## Recommendation",
        "",
        f"**Best by Sharpe-like:** min_confluence={best_sharpe.get('risk.min_confluence')}, "
        f"max_notional_pct={best_sharpe.get('safety.max_position_notional_pct')}",
        f"- Total return: {best_sharpe.get('total_return_pct', 0):.2f}%",
        f"- Max DD (MTM): {best_sharpe.get('max_drawdown_pct', 0):.2f}%",
        f"- Profit factor: {best_sharpe.get('profit_factor', 0):.2f}",
        f"- Sharpe-like: {best_sharpe.get('sharpe_like', 0):.2f}",
        "",
        f"**Stability check:** best Sharpe config "
        f"{'IS' if best_sharpe_in_top5_return else 'is NOT'} in top 5 by raw return — "
        f"{'consistent' if best_sharpe_in_top5_return else 'review for over-fitting before shipping'}.",
        "",
        "**Next step:** if the recommended config differs from the live `phase2_1k` "
        "(`min_confluence=50`, `max_position_notional_pct=2.0`), prepare a separate PR "
        "to update the live config — DO NOT auto-merge to master from this branch.",
        "",
    ])

    summary_path = Path("docs/results") / f"{today}-phase-C-grid-results.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSummary written to: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
