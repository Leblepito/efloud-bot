"""Pure backtest engine — walk-forward simulation with no I/O."""
from __future__ import annotations

import logging
import tempfile
from typing import Any

import pandas as pd

from engine import SafeOrchestrator
from engine.notifications import NullNotificationManager

log = logging.getLogger("efloud.backtest.engine")


def run_backtest(
    *,
    symbols: list[str],
    data: dict[str, dict[str, pd.DataFrame]],
    config: dict,
    initial_balance: float = 2000.0,
    warmup_bars: int = 200,
    step_every_n_bars: int = 1,
) -> dict[str, Any]:
    """Run a walk-forward backtest. No I/O.

    Args:
        symbols: list of symbols to simulate. Single-symbol mode = 1 entry; portfolio = N.
        data: {symbol: {tf: df}} pre-loaded OHLCV.
        config: bot config dict (same schema as live).
        initial_balance: starting USDT.
        warmup_bars: bars consumed before first cycle (analysis warmup).
        step_every_n_bars: cycle frequency (1 = every bar, 4 = every 4 bars).

    Returns: dict with initial_balance, final_balance, trades, symbols, etc.
    """
    # Process symbols in alphabetical order for deterministic results
    symbols = sorted(symbols)

    # Use a temp state_dir — persist=False means no disk writes but orch __init__ needs a dir
    with tempfile.TemporaryDirectory(prefix="bt_") as state_dir:
        orch = SafeOrchestrator(
            config,
            state_dir=state_dir,
            notification_mgr=NullNotificationManager(),
            freshness_check=False,
            persist=False,
        )
        balance = float(initial_balance)
        peak_balance = balance
        skipped_cycles = 0  # cycles where run_cycle raised — see "skipped_cycles" in return dict

        # Use the first symbol's entry-TF index as the master clock
        entry_tf_name = config["timeframes"]["entry"]
        primary_idx = data[symbols[0]][entry_tf_name].index
        n_bars = len(primary_idx)
        if n_bars < warmup_bars + 50:
            raise ValueError(f"Not enough bars: {n_bars} < {warmup_bars + 50}")

        for i in range(warmup_bars, n_bars, step_every_n_bars):
            current_ts = primary_idx[i]
            for symbol in symbols:
                tfs = data[symbol]
                # Slicing semantics:
                #   - entry TF: iloc[:i+1] inclusive of bar i (current bar's close is observed at current_ts).
                #   - HTF/MTF/daily: loc[:current_ts] returns bars where index <= current_ts; non-aligned
                #     boundaries are handled correctly (a 15min ts on a 4h index returns the latest <= ts).
                e_slice = tfs[entry_tf_name].iloc[: i + 1]
                h_slice = tfs[config["timeframes"]["htf"]].loc[: current_ts]
                m_slice = tfs[config["timeframes"]["mtf"]].loc[: current_ts]
                d_slice = tfs.get("1d")
                if d_slice is not None:
                    d_slice = d_slice.loc[: current_ts]
                if len(h_slice) < 50 or len(m_slice) < 50:
                    continue
                try:
                    orch.run_cycle(symbol, h_slice, m_slice, e_slice, d_slice, balance=balance)
                except Exception as e:
                    skipped_cycles += 1
                    log.warning("Cycle %s @ %s raised %s: %s", symbol, current_ts, type(e).__name__, e)
                    continue

            # PnL update (intrabar fills + MTM) — deferred to Chunk 4

        closed_positions = [p for p in orch.lifecycle.positions if not p.is_open and p.exits]

        return {
            "initial_balance": initial_balance,
            "final_balance": balance,
            "peak_balance": peak_balance,
            "trades": [_serialize_trade(p) for p in closed_positions],
            "equity_curve": [],
            "symbols": symbols,
            "skipped_cycles": skipped_cycles,
        }


def _serialize_trade(p) -> dict:
    return {
        "symbol": p.symbol,
        "direction": p.direction,
        "entry": float(p.avg_entry_price),
        "exit": float(p.exits[-1].price) if p.exits else None,
        "pnl": float(p.realized_pnl),
        "exit_reason": p.exits[-1].reason if p.exits else None,
        "opened_at": str(p.opened_at),
        "closed_at": str(p.closed_at) if p.closed_at else None,
    }
