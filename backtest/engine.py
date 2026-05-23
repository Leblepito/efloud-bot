"""Pure backtest engine — walk-forward simulation with no I/O."""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from backtest.intrabar import resolve_fill, Bar
from backtest.metrics import aggregate_metrics, serialize_trade
from backtest.slippage import adverse_fill, SlippageConfig
from engine import SafeOrchestrator
from engine.notifications import NullNotificationManager

log = logging.getLogger("efloud.backtest.engine")


@dataclass
class _PosView:
    """Adapter so resolve_fill (which expects .entry attribute) works with Position objects."""
    direction: str
    entry: float
    sl: float
    tp1: float


def compute_mtm_drawdown(positions, balance, current_prices, peak):
    """Return (drawdown_pct_now, new_peak) given current prices.

    Args:
        positions: iterable of Position objects (open ones contribute unrealized pnl).
        balance: realized cash balance.
        current_prices: {symbol: latest_price} for symbols with open positions.
        peak: previous peak equity (MTM, not just realized).
    """
    unrealized = 0.0
    for p in positions:
        if not p.is_open or p.symbol not in current_prices:
            continue
        sign = 1 if p.direction == "LONG" else -1
        unrealized += (current_prices[p.symbol] - p.avg_entry_price) * p.remaining_size * sign
    mtm = balance + unrealized
    new_peak = max(peak, mtm)
    dd_pct = ((new_peak - mtm) / new_peak * 100) if new_peak > 0 else 0.0
    return dd_pct, new_peak


_DEFAULT_SMC_WINDOW = 500


def run_backtest(
    *,
    symbols: list[str],
    data: dict[str, dict[str, pd.DataFrame]],
    config: dict,
    initial_balance: float = 2000.0,
    warmup_bars: int = 200,
    step_every_n_bars: int = 1,
    smc_window_bars: int = _DEFAULT_SMC_WINDOW,
    smc_version: Literal["v1", "v2"] = "v1",
) -> dict[str, Any]:
    """Run a walk-forward backtest. No I/O.

    Args:
        symbols: list of symbols to simulate. Single-symbol mode = 1 entry; portfolio = N.
        data: {symbol: {tf: df}} pre-loaded OHLCV.
        config: bot config dict (same schema as live).
        initial_balance: starting USDT.
        warmup_bars: bars consumed before first cycle (analysis warmup).
        step_every_n_bars: cycle frequency (1 = every bar, 4 = every 4 bars).
        smc_window_bars: rolling-window cap on slices passed to run_cycle. SMC analysis
            (sfps, fvgs, swings, order_blocks) iterates the entire df each call. Without
            a cap, slices grow unbounded → O(N²) per cycle, O(N³) per backtest.
            500 bars (≈85 days @ 4h, 5 days @ 15min) preserves long-range signals while
            keeping cycle cost roughly constant. Mirrors live bot behaviour where CCXT
            fetch returns a fixed window. Set to 0 to disable (full history, slow).

    Returns: dict with initial_balance, final_balance, trades, symbols, etc.
    """
    # Process symbols in alphabetical order for deterministic results
    symbols = sorted(symbols)

    # Use a temp state_dir — persist=False means no disk writes but orch __init__ needs a dir
    with tempfile.TemporaryDirectory(prefix="bt_") as state_dir:
        setup_state_store = None
        if smc_version == "v2":
            from engine.smc_v2.setup_state import SetupStateStore
            setup_state_store = SetupStateStore(
                path=Path(state_dir) / "setup_candidates.json",
                max_pending_per_symbol=int(
                    config.get("smc_v2", {}).get("max_pending_per_symbol", 3)
                ),
            )

        orch = SafeOrchestrator(
            config,
            state_dir=state_dir,
            notification_mgr=NullNotificationManager(),
            freshness_check=False,
            persist=False,
            setup_state_store=setup_state_store,
        )
        balance = float(initial_balance)
        peak_balance = balance
        skipped_cycles = 0  # cycles where run_cycle raised — see "skipped_cycles" in return dict
        slippage_cfg = SlippageConfig()
        max_drawdown_pct = 0.0
        current_prices: dict[str, float] = {}

        # Use the first symbol's entry-TF index as the master clock
        entry_tf_name = config["timeframes"]["entry"]
        primary_idx = data[symbols[0]][entry_tf_name].index
        n_bars = len(primary_idx)
        if n_bars < warmup_bars + 50:
            raise ValueError(f"Not enough bars: {n_bars} < {warmup_bars + 50}")

        for i in range(warmup_bars, n_bars, step_every_n_bars):
            current_ts = primary_idx[i]
            # Convert pandas Timestamp → naive datetime for breaker (pure Python).
            # tz-aware → naive UTC; tz-naive → as-is. Breaker semantics are tz-agnostic
            # (uses datetime.utcnow elsewhere) so we strip tz for consistency.
            sim_now = current_ts.to_pydatetime()
            if sim_now.tzinfo is not None:
                sim_now = sim_now.replace(tzinfo=None)
            for symbol in symbols:
                tfs = data[symbol]
                # Slicing semantics:
                #   - entry TF: iloc[:i+1] inclusive of bar i (current bar's close is observed at current_ts).
                #   - HTF/MTF/daily: loc[:current_ts] returns bars where index <= current_ts; non-aligned
                #     boundaries are handled correctly (a 15min ts on a 4h index returns the latest <= ts).
                e_slice = tfs[entry_tf_name].iloc[: i + 1]
                h_slice = tfs[config["timeframes"]["htf"]].loc[: current_ts]
                m_slice = tfs[config["timeframes"]["mtf"]].loc[: current_ts]
                if smc_window_bars > 0:
                    e_slice = e_slice.iloc[-smc_window_bars:]
                    h_slice = h_slice.iloc[-smc_window_bars:]
                    m_slice = m_slice.iloc[-smc_window_bars:]
                d_slice = tfs.get("1d")
                if d_slice is not None:
                    d_slice = d_slice.loc[: current_ts]
                if len(h_slice) < 50 or len(m_slice) < 50:
                    continue
                try:
                    orch.run_cycle(symbol, h_slice, m_slice, e_slice, d_slice,
                                   balance=balance, now=sim_now)
                except Exception as e:
                    skipped_cycles += 1
                    log.debug("Cycle %s @ %s raised %s: %s", symbol, current_ts, type(e).__name__, e)
                    continue
                current_prices[symbol] = float(e_slice["close"].iloc[-1])

            # MAE/MFE excursion update on bar i for all open positions — mirrors
            # main.py _scan_one update_excursion call so trade records carry
            # non-zero mae_pct/mfe_pct (needed by T2 bug retrospective pipeline).
            for pos in orch.lifecycle.positions:
                if not pos.is_open:
                    continue
                sym_data = data.get(pos.symbol)
                if sym_data is None:
                    continue
                bar_data = sym_data[entry_tf_name].iloc[i]
                pos.update_excursion(
                    float(bar_data["high"]),
                    float(bar_data["low"]),
                )

            # Intrabar fill check on next bar (i+1) for any open positions
            # TODO(Chunk 5): add run_backtest-level test triggering actual SL fill on synthetic data.
            # Currently the helper composition is unit-tested but the engine wiring is implicit.
            if i + 1 < n_bars:
                for pos in list(orch.lifecycle.positions):
                    if not pos.is_open:
                        continue
                    sym_data = data.get(pos.symbol)
                    if sym_data is None:
                        continue
                    next_bar_data = sym_data[entry_tf_name].iloc[i + 1]
                    bar = Bar(
                        open=float(next_bar_data["open"]),
                        high=float(next_bar_data["high"]),
                        low=float(next_bar_data["low"]),
                        close=float(next_bar_data["close"]),
                    )
                    view = _PosView(
                        direction=pos.direction,
                        entry=pos.avg_entry_price,
                        sl=pos.sl,
                        tp1=pos.tp1,
                    )
                    level, raw_price = resolve_fill(view, bar)
                    if level is None:
                        continue
                    # resolve_fill returns "SL" or "TP1"; slippage expects leg in {"entry","SL","TP"}.
                    slip_leg = "SL" if level == "SL" else "TP"
                    slipped = adverse_fill(raw_price, pos.direction, slip_leg, slippage_cfg)
                    pnl_before = pos.realized_pnl
                    orch.lifecycle.close_position(pos, slipped, level)
                    pnl_after = pos.realized_pnl
                    balance += (pnl_after - pnl_before)
                    peak_balance = max(peak_balance, balance)

            # MTM uses bar-i's close (current cycle); balance was just updated by bar-(i+1) slipped fills.
            # Intentional 1-bar lag — MTM equity drifts forward on the next iteration.
            dd, peak_balance = compute_mtm_drawdown(
                orch.lifecycle.positions, balance, current_prices, peak_balance
            )
            max_drawdown_pct = max(max_drawdown_pct, dd)

        if skipped_cycles > 0:
            log.warning("Backtest had %d skipped cycles (see DEBUG log for details)", skipped_cycles)
        closed_positions = [p for p in orch.lifecycle.positions if not p.is_open and p.exits]
        trade_dicts = [serialize_trade(p) for p in closed_positions]
        agg = aggregate_metrics(trade_dicts, initial_balance, peak_balance, balance)

        return {
            "initial_balance": initial_balance,
            "final_balance": balance,
            "peak_balance": peak_balance,
            "trades": trade_dicts,
            "equity_curve": [],
            "symbols": symbols,
            "skipped_cycles": skipped_cycles,
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "smc_version": smc_version,
            **agg,
        }


