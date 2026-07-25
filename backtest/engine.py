"""Pure backtest engine — walk-forward simulation with no I/O."""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from backtest.intrabar import resolve_fill, Bar
from backtest.metrics import (
    aggregate_metrics, apply_commission_costs, apply_funding_costs, serialize_trade,
)
from backtest.slippage import adverse_fill, SlippageConfig
from data.timeframes import tf_to_minutes
from engine import SafeOrchestrator
from engine.notifications import NullNotificationManager

log = logging.getLogger("efloud.backtest.engine")


def _closed_higher_tf_bars(df: pd.DataFrame, tf_minutes: int,
                           decision_ts: pd.Timestamp) -> pd.DataFrame:
    """F11 (2026-07-11 spec): open-time index'te `loc[:ts]` HÂLÂ OLUŞAN yüksek-TF
    barını FINAL OHLC'siyle içerir — klasik MTF look-ahead (HTF bias/MTF yapı/
    daily filter her cycle 4-24 saatlik geleceği görüyordu). Yalnız kapanış
    zamanı (open + tf) karar anına kadar TAMAMLANMIŞ barlar döner; tam karar
    anında kapanan bar dahildir.
    """
    out = df.loc[:decision_ts]
    tf_delta = pd.Timedelta(minutes=tf_minutes)
    while len(out) > 0 and out.index[-1] + tf_delta > decision_ts:
        out = out.iloc[:-1]
    return out



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


def stamp_sim_times(trade_dicts: list[dict], sim_open_ts: dict, sim_close_ts: dict) -> None:
    """Surface SIM-time entry/exit onto trade records, in place (keyed by id).

    The live engine sets ``opened_at``/``closed_at`` to wall-clock
    ``datetime.utcnow()`` (``lifecycle.open_position``) — in a backtest every
    trade is stamped within microseconds of the run, so those fields are useless
    for any time-based analysis. The run loop separately tracks ``sim_open_ts`` /
    ``sim_close_ts`` (the simulated bar timestamps) for S2b funding; surfacing
    them as ``sim_opened_at`` / ``sim_closed_at`` enables walk-forward IS/OOS
    partitioning and regime separation by simulated entry time.

    Additive: no trade-logic change. Runs before the commission/funding passes,
    whose ``dict(t)`` copies preserve the new keys. ``None`` when an id is absent.
    """
    for t in trade_dicts:
        so = sim_open_ts.get(t["id"])
        sc = sim_close_ts.get(t["id"])
        t["sim_opened_at"] = str(so) if so is not None else None
        t["sim_closed_at"] = str(sc) if sc is not None else None


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
    commission_pct: float | None = None,
    funding_pct_per_8h: float | None = None,
    max_holding_hours: float | None = None,
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
            # Lazy import: v1 path must not import engine.smc_v2 (preserves the
            # inert invariant — v1 runtime carries no v2 module-level side effects).
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
        # BT-4 (2026-07-11 review): entry fill'lerine slippage. run_cycle icinde
        # lifecycle'a eklenen her YENI Entry tranche'i (ilk giris + piramit) tam
        # 1 kez adverse yonde slip edilir. SL/TP seviyeleri sinyalin planladigi
        # (slip'siz) fiyattan hesaplanmis kalir — canlidaki gercekligin aynisi.
        entry_tranches_slipped: dict = {}  # pos.id -> slip edilmis Entry sayisi
        max_drawdown_pct = 0.0
        current_prices: dict[str, float] = {}
        # S2b: sim-time open/close per position id → funding holding duration.
        sim_open_ts: dict = {}
        sim_close_ts: dict = {}
        # BT-16 (2026-07-25): canli safe_orchestrator her cycle'da
        # pos_guard.check_holding_time() calistirip safety.max_holding_hours'i
        # asan pozisyonu market'ten zorla kapatiyor (_force_close_max_hold,
        # logical reason "MANUAL"). Backtest bu kurali hic modellemiyordu ->
        # max_holding_hours: 4 olan scalp configinde 95 SAATLIK trade'ler
        # simule ediliyor, sonuc canliyla alakasiz cikiyordu (W2 A/B kosusunda
        # 19 trade'in 14'u 8h+ surdu; canlida hicbiri o sekilde kapanamazdi).
        # Resolution order: param -> config["safety"]["max_holding_hours"] -> 0
        # (0/yok = kapali, eski baseline'lar birebir korunur).
        mh = (
            max_holding_hours if max_holding_hours is not None
            else float(config.get("safety", {}).get("max_holding_hours", 0) or 0)
        )
        max_hold_exits = 0

        # Use the first symbol's entry-TF index as the master clock
        entry_tf_name = config["timeframes"]["entry"]
        primary_idx = data[symbols[0]][entry_tf_name].index
        n_bars = len(primary_idx)
        if n_bars < warmup_bars + 50:
            raise ValueError(f"Not enough bars: {n_bars} < {warmup_bars + 50}")

        # F11: karar anı = entry barının kapanışı (open + entry_tf)
        _entry_delta = pd.Timedelta(minutes=tf_to_minutes(entry_tf_name))
        _htf_minutes = tf_to_minutes(config["timeframes"]["htf"])
        _mtf_minutes = tf_to_minutes(config["timeframes"]["mtf"])

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
                decision_ts = current_ts + _entry_delta
                h_slice = _closed_higher_tf_bars(
                    tfs[config["timeframes"]["htf"]], _htf_minutes, decision_ts)
                m_slice = _closed_higher_tf_bars(
                    tfs[config["timeframes"]["mtf"]], _mtf_minutes, decision_ts)
                if smc_window_bars > 0:
                    e_slice = e_slice.iloc[-smc_window_bars:]
                    h_slice = h_slice.iloc[-smc_window_bars:]
                    m_slice = m_slice.iloc[-smc_window_bars:]
                d_slice = tfs.get("1d")
                if d_slice is not None:
                    d_slice = _closed_higher_tf_bars(d_slice, 1440, decision_ts)
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

            # BT-4: bu cycle'da eklenen yeni entry tranche'larini slip et.
            for pos in orch.lifecycle.positions:
                if not pos.is_open:
                    continue
                seen = entry_tranches_slipped.get(pos.id, 0)
                if len(pos.entries) > seen:
                    for e in pos.entries[seen:]:
                        if e.price is not None:
                            e.price = adverse_fill(
                                float(e.price), pos.direction, "entry", slippage_cfg)
                    entry_tranches_slipped[pos.id] = len(pos.entries)

            # MAE/MFE excursion update on bar i for all open positions — mirrors
            # main.py _scan_one update_excursion call so trade records carry
            # non-zero mae_pct/mfe_pct (needed by T2 bug retrospective pipeline).
            for pos in orch.lifecycle.positions:
                if not pos.is_open:
                    continue
                sym_data = data.get(pos.symbol)
                if sym_data is None:
                    continue
                # Symbols can have mismatched bar counts (later listing date or
                # missing bars), so this symbol's frame may be shorter than the
                # master loop index i. Guard before .iloc to avoid IndexError.
                symbol_df = sym_data[entry_tf_name]
                if i >= len(symbol_df):
                    continue
                bar_data = symbol_df.iloc[i]
                pos.update_excursion(
                    float(bar_data["high"]),
                    float(bar_data["low"]),
                )

            # Intrabar fill check — BT-9 (2026-07-11 review): step_every_n_bars>1
            # iken sonraki cycle i+step'te baslar ve yalniz i+step+1'i tarardi;
            # i+1..i+step araligindaki SL/TP dokunuslari SONSUZA DEK kayboluyordu.
            # Simdi atlanan barlar dahil taranir (step=1'de davranis birebir ayni:
            # yalniz i+1). Engine-wiring testleri: backend/tests/test_backtest_hygiene_batch1.py
            for j in range(i + 1, min(i + step_every_n_bars, n_bars - 1) + 1):
                for pos in list(orch.lifecycle.positions):
                    if not pos.is_open:
                        continue
                    sym_data = data.get(pos.symbol)
                    if sym_data is None:
                        continue
                    # Same mismatched-bar-count guard as above for the lookahead.
                    symbol_df = sym_data[entry_tf_name]
                    if j >= len(symbol_df):
                        continue
                    next_bar_data = symbol_df.iloc[j]
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
                        # BT-16: SL/TP dolmadi -> max holding suresi doldu mu?
                        # SL/TP ONCELIKLI: gercekte de borsadaki SL/TP emri
                        # orchestrator'un force-close'undan once dolar, o yuzden
                        # bu kontrol yalnizca level is None dalinda.
                        if mh <= 0:
                            continue
                        opened_ts = sim_open_ts.get(pos.id)
                        if opened_ts is None:
                            # Bu cycle'da acildi; sim_open_ts damgasi cycle
                            # sonunda vuruluyor (asagidaki stamp blogu).
                            opened_ts = current_ts
                        age_h = (symbol_df.index[j] - opened_ts).total_seconds() / 3600.0
                        if age_h < mh:
                            continue
                        # Market close: SL bacagiyla ayni taker slippage'i
                        # (yon de dogru — LONG kapanis = sell = adverse-down).
                        slipped_mh = adverse_fill(
                            float(bar.close), pos.direction, "SL", slippage_cfg)
                        pnl_before_mh = pos.realized_pnl
                        # Canli logical close "MANUAL" reason kullaniyor
                        # (safe_orchestrator.py:959) — birebir ayni tutuluyor ki
                        # backtest trade'leri canli ledger'la karsilastirilabilsin.
                        orch.lifecycle.close_position(pos, slipped_mh, "MANUAL")
                        balance += (pos.realized_pnl - pnl_before_mh)
                        peak_balance = max(peak_balance, balance)
                        sim_close_ts[pos.id] = symbol_df.index[j]
                        max_hold_exits += 1
                        continue
                    # resolve_fill returns "SL" or "TP1"; slippage expects leg in {"entry","SL","TP"}.
                    slip_leg = "SL" if level == "SL" else "TP"
                    slipped = adverse_fill(raw_price, pos.direction, slip_leg, slippage_cfg)
                    pnl_before = pos.realized_pnl
                    orch.lifecycle.close_position(pos, slipped, level)
                    pnl_after = pos.realized_pnl
                    balance += (pnl_after - pnl_before)
                    peak_balance = max(peak_balance, balance)
                    # BT-12: sim_close_ts fill BARININ timestamp'i olmali — onceden
                    # karar bari i'nin damgasi vuruluyordu (holding suresi step
                    # kadar kisaliyor, funding hesabi carpitiliyordu).
                    sim_close_ts[pos.id] = symbol_df.index[j]

            # MTM uses bar-i's close (current cycle); balance was just updated by bar-(i+1) slipped fills.
            # Intentional 1-bar lag — MTM equity drifts forward on the next iteration.
            dd, peak_balance = compute_mtm_drawdown(
                orch.lifecycle.positions, balance, current_prices, peak_balance
            )
            max_drawdown_pct = max(max_drawdown_pct, dd)

            # S2b: stamp sim-time open (first sighting) and close (first time the
            # position is no longer open) so funding can use real holding hours.
            # BT-12: intrabar fill'ler yukarida fill bariyla damgalandi; buradaki
            # close damgasi yalniz run_cycle icinde kapanan pozisyonlari yakalar.
            for pos in orch.lifecycle.positions:
                if pos.id not in sim_open_ts:
                    sim_open_ts[pos.id] = current_ts
                if not pos.is_open and pos.id not in sim_close_ts:
                    sim_close_ts[pos.id] = current_ts

        if skipped_cycles > 0:
            log.warning("Backtest had %d skipped cycles (see DEBUG log for details)", skipped_cycles)
        closed_positions = [p for p in orch.lifecycle.positions if not p.is_open and p.exits]
        trade_dicts = [serialize_trade(p) for p in closed_positions]
        # Surface sim-time entry/exit (opened_at is wall-clock, see stamp_sim_times).
        # Before commission/funding so their dict(t) copies carry the new keys.
        stamp_sim_times(trade_dicts, sim_open_ts, sim_close_ts)
        # S2: net out round-trip taker commission. Resolution order: explicit
        # param → config["backtest"]["commission_pct"] → 0.0 (off, backward-compat
        # — existing tests/baselines unchanged unless commission is enabled).
        # Set backtest.commission_pct: 0.04 (Binance USD-M taker) for realistic
        # net returns / profit factor (e.g. the S1 conf-50-vs-80 net-PF check).
        cp = (
            commission_pct if commission_pct is not None
            else float(config.get("backtest", {}).get("commission_pct", 0.0))
        )
        trade_dicts, balance, total_commission = apply_commission_costs(trade_dicts, balance, cp)
        # S2b: apply funding from sim-time holding duration (after commission, on
        # the already-netted balance/trades). Rate resolution: param →
        # config["backtest"]["funding_pct_per_8h"] → 0.0 (off, backward-compat).
        # Funding is an average symmetric drag (see apply_funding_costs); a
        # per-symbol funding-rate series is a further follow-up (S2c).
        holding_hours: dict = {}
        notional_by_id: dict = {}
        for p in closed_positions:
            o, c = sim_open_ts.get(p.id), sim_close_ts.get(p.id)
            holding_hours[p.id] = (
                (c - o).total_seconds() / 3600.0 if (o is not None and c is not None) else 0.0
            )
            notional_by_id[p.id] = float(p.avg_entry_price) * float(p.total_size_entered)
        fp = (
            funding_pct_per_8h if funding_pct_per_8h is not None
            else float(config.get("backtest", {}).get("funding_pct_per_8h", 0.0))
        )
        trade_dicts, balance, total_funding = apply_funding_costs(
            trade_dicts, balance, fp, holding_hours, notional_by_id
        )
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
            "commission_pct": cp,
            "total_commission": round(total_commission, 4),
            "funding_pct_per_8h": fp,
            "total_funding": round(total_funding, 4),
            "max_holding_hours": mh,
            "max_hold_exits": max_hold_exits,
            **agg,
        }


