"""
Backtest Runner — Tarihsel Veri Üzerinde Walk-Forward Simülasyon
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Efloud Bot'un tarihsel veride nasıl performans gösterdiğini ölçer.

Walk-forward mantığı:
  For each bar in history:
    1. DataFrame'leri o bara kadar kes (look-ahead bias yok)
    2. SafeOrchestrator.run_cycle çalıştır
    3. Pozisyonları current_price ile güncelle
    4. Kapanan trade'leri kaydet
  
  End → performans metrikleri hesapla

Metrikler:
  - Total return, CAGR
  - Win rate, profit factor
  - Max drawdown
  - Sharpe-like ratio (günlük return stddev)
  - Avg R:R, avg holding time
  - Trade count, entries/exits

Bu modül SADECE historical simülasyon yapar — gerçek order göndermez.
"""

import logging
import pandas as pd
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from datetime import datetime

log = logging.getLogger("efloud.backtest")


@dataclass
class BacktestTrade:
    """Backtest'te kapanmış tek trade kaydı."""
    entry_ts: str
    exit_ts: str
    symbol: str
    direction: str
    entries_count: int        # Kaç giriş (piramit dahil)
    avg_entry: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    rr_realized: float
    exit_reason: str
    holding_bars: int
    confluence: int = 0
    max_favorable: float = 0  # MFE (max kâr seyri)
    max_adverse: float = 0    # MAE (max zarar seyri)


@dataclass
class BacktestResult:
    """Backtest özet sonucu."""
    symbol: str
    start_ts: str
    end_ts: str
    bars_tested: int

    # Balance
    initial_balance: float
    final_balance: float
    peak_balance: float

    # Returns
    total_return_pct: float
    max_drawdown_pct: float

    # Trades
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    profit_factor: float    # total_wins / total_losses (absolute)
    avg_win: float
    avg_loss: float
    avg_rr: float
    avg_hold_bars: float
    largest_win: float
    largest_loss: float

    # Risk
    consecutive_loss_max: int
    sharpe_like: float       # rough: avg_return / stddev(returns)

    # By exit reason
    by_exit_reason: Dict[str, int]

    # Trades detail
    trades: List[BacktestTrade] = field(default_factory=list)

    # Equity curve (for charting)
    equity_curve: List[dict] = field(default_factory=list)

    def to_summary(self) -> str:
        """Rapor-dostu markdown özet."""
        lines = [
            f"# Backtest Result — {self.symbol}",
            "",
            f"**Period:** {self.start_ts} → {self.end_ts} ({self.bars_tested} bars)",
            "",
            "## Performance",
            f"- Initial balance: ${self.initial_balance:,.2f}",
            f"- Final balance: ${self.final_balance:,.2f}",
            f"- **Total return: {self.total_return_pct:+.2f}%**",
            f"- Peak balance: ${self.peak_balance:,.2f}",
            f"- **Max drawdown: {self.max_drawdown_pct:.2f}%**",
            f"- Sharpe-like: {self.sharpe_like:.2f}",
            "",
            "## Trades",
            f"- Total: {self.total_trades} | Wins: {self.wins} | Losses: {self.losses} | BE: {self.breakeven}",
            f"- Win rate: {self.win_rate:.1f}%",
            f"- Profit factor: {self.profit_factor:.2f}",
            f"- Avg win: ${self.avg_win:+.2f} | Avg loss: ${self.avg_loss:+.2f}",
            f"- Avg R:R realized: {self.avg_rr:.2f}",
            f"- Avg holding: {self.avg_hold_bars:.1f} bars",
            f"- Largest win: ${self.largest_win:+.2f} | Largest loss: ${self.largest_loss:+.2f}",
            f"- Max consecutive losses: {self.consecutive_loss_max}",
            "",
            "## Exit Reasons",
        ]
        for reason, count in sorted(self.by_exit_reason.items(),
                                      key=lambda x: -x[1]):
            pct = (count / self.total_trades * 100) if self.total_trades > 0 else 0
            lines.append(f"- {reason}: {count} ({pct:.1f}%)")
        return "\n".join(lines)


class BacktestRunner:
    """Walk-forward backtest orkestratörü."""

    def __init__(self, config: dict,
                  warmup_bars: int = 200,
                  step_every_n_bars: int = 1,
                  fee_rate: float = 0.0004):
        """
        Args:
            config: Normal bot config
            warmup_bars: İlk N bar sadece analiz için (sinyal üretme)
            step_every_n_bars: Her kaç bar'da bir cycle çalıştır (1=her bar, 4=her 4 bar)
            fee_rate: Tek-yön taker komisyon oranı (Binance Futures default 0.0004 = %0.04).
                      Round-trip iki kez kesilir (entry + exit). 0 ile devre dışı.
        """
        self.config = config
        self.warmup = warmup_bars
        self.step = step_every_n_bars
        self.fee_rate = fee_rate

    def _calc_fees(self, position) -> float:
        """Pozisyonun toplam komisyon maliyeti (entry + exit, pyramid dahil)."""
        if self.fee_rate <= 0:
            return 0.0
        entry_notional = sum(e.price * e.size for e in position.entries)
        exit_notional = sum(e.price * e.size for e in position.exits)
        return (entry_notional + exit_notional) * self.fee_rate

    def run(self,
            symbol: str,
            df_htf: pd.DataFrame,
            df_mtf: pd.DataFrame,
            df_entry: pd.DataFrame,
            df_daily: Optional[pd.DataFrame] = None,
            initial_balance: float = 10000.0,
            verbose: bool = False) -> BacktestResult:
        """Backtest'i çalıştır."""
        # SafeOrchestrator her instance'ta fresh state ister — /tmp'ye
        import tempfile, shutil
        state_dir = tempfile.mkdtemp(prefix="bt_")
        try:
            from engine import SafeOrchestrator
            # Safety'yi backtest'te daha gevşek tut (test amaçlı)
            bt_config = dict(self.config)
            bt_config["safety"] = dict(self.config.get("safety", {}))
            bt_config["safety"]["starting_balance"] = initial_balance
            bt_config["operation"] = dict(self.config.get("operation", {}))
            bt_config["operation"]["dry_run"] = True
            bt_config["operation"]["watch_only"] = False

            orch = SafeOrchestrator(bt_config, state_dir=state_dir)
            
            # Signal deduplication — her signal timestamp bir kez işlensin
            processed_signals = set()  # (direction, entry_price, timestamp)

            entries_count = len(df_entry)
            if entries_count < self.warmup + 50:
                raise ValueError(f"Not enough entry bars: {entries_count} < {self.warmup + 50}")

            log.info(f"Running backtest: {symbol} | {entries_count} bars "
                      f"(warmup={self.warmup}, step={self.step})")

            # Entry TF'in index'ine göre yürü
            balance = initial_balance
            peak_balance = initial_balance
            equity_curve = []

            # HTF/MTF/Daily timestamps sorted ascending
            df_htf = df_htf.sort_index()
            df_mtf = df_mtf.sort_index()
            df_entry = df_entry.sort_index()
            if df_daily is not None:
                df_daily = df_daily.sort_index()

            cycles_run = 0
            for i in range(self.warmup, entries_count, self.step):
                current_ts = df_entry.index[i]

                # Her DataFrame'i current_ts'ye kadar kes (look-ahead bias yok)
                e_slice = df_entry.iloc[:i + 1]
                h_slice = df_htf[df_htf.index <= current_ts]
                m_slice = df_mtf[df_mtf.index <= current_ts]
                d_slice = df_daily[df_daily.index <= current_ts] if df_daily is not None else None

                # Minimum data kontrolü
                if len(h_slice) < 50 or len(m_slice) < 50:
                    continue

                # Cycle çalıştır
                # NOT: freshness check backtest'te zararlı — override
                try:
                    self._run_cycle_without_freshness(orch, symbol,
                                                        h_slice, m_slice, e_slice,
                                                        d_slice, balance, current_ts)
                    cycles_run += 1
                except Exception as e:
                    if verbose:
                        log.error(f"Cycle at {current_ts} failed: {e}")
                    continue

                # Position update with current price
                current_price = float(e_slice["close"].iloc[-1])
                price_map = {symbol: current_price}

                def weakness_check(pos):
                    bias = "BULL" if pos.direction == "LONG" else "BEAR"
                    return orch.intent.check_weakness(e_slice, bias)

                orch.lifecycle.on_tick(price_map, intent_checker=weakness_check)

                # Kapanan pozisyonların PnL'ini balance'a ekle (komisyon düşülerek)
                for p in orch.lifecycle.positions:
                    if not p.is_open and not getattr(p, "_bt_counted", False):
                        fee = self._calc_fees(p)
                        balance += p.realized_pnl - fee
                        p._bt_fee = fee
                        p._bt_counted = True
                        peak_balance = max(peak_balance, balance)

                # Equity snapshot (her 10 cycle)
                if cycles_run % 10 == 0:
                    equity_curve.append({
                        "ts": str(current_ts),
                        "balance": round(balance, 2),
                        "price": current_price,
                    })

            # Backtest bitti — final sonuç
            closed_positions = [p for p in orch.lifecycle.positions if not p.is_open]
            open_positions = [p for p in orch.lifecycle.positions if p.is_open]

            # Açık pozisyonları son fiyatla kapat (komisyon düşülerek)
            final_price = float(df_entry["close"].iloc[-1])
            for p in open_positions:
                orch.lifecycle.close_position(p, final_price, "MANUAL")
                fee = self._calc_fees(p)
                balance += p.realized_pnl - fee
                p._bt_fee = fee

            all_closed = [p for p in orch.lifecycle.positions if not p.is_open]

            # Sonuçları derle
            result = self._build_result(
                symbol=symbol,
                df_entry=df_entry,
                bars_tested=entries_count - self.warmup,
                initial_balance=initial_balance,
                final_balance=balance,
                peak_balance=peak_balance,
                positions=all_closed,
                equity_curve=equity_curve,
            )

            log.info(f"Backtest complete: {result.total_trades} trades | "
                      f"WR={result.win_rate:.1f}% | PF={result.profit_factor:.2f} | "
                      f"Return={result.total_return_pct:+.2f}% | DD={result.max_drawdown_pct:.2f}%")

            return result

        finally:
            shutil.rmtree(state_dir, ignore_errors=True)

    @staticmethod
    def _run_cycle_without_freshness(orch, symbol, h, m, e, d, balance, current_ts):
        """Freshness validation'ı bypass ederek run_cycle çalıştır."""
        # Monkey-patch: validate_kline_freshness'ı geçici olarak no-op yap
        from engine.safety import guard
        original = guard.validate_kline_freshness
        guard.validate_kline_freshness = lambda *a, **kw: True
        # Ayrıca safe_orchestrator içindeki import da patch'lenmeli
        from engine import safe_orchestrator as so_mod
        original_so = so_mod.validate_kline_freshness
        so_mod.validate_kline_freshness = lambda *a, **kw: True
        try:
            orch.run_cycle(symbol, h, m, e, d, balance=balance)
        finally:
            guard.validate_kline_freshness = original
            so_mod.validate_kline_freshness = original_so

    @staticmethod
    def _build_result(symbol, df_entry, bars_tested,
                       initial_balance, final_balance, peak_balance,
                       positions, equity_curve) -> BacktestResult:
        """Pozisyonlardan özet metrikleri hesapla."""
        trades = []
        for p in positions:
            if not p.exits:
                continue
            final_exit = p.exits[-1]
            holding_bars = 0  # TODO: entry ts → exit ts bar count
            try:
                t0 = pd.Timestamp(p.opened_at)
                t1 = pd.Timestamp(p.closed_at or final_exit.timestamp)
                holding_bars = int((t1 - t0).total_seconds() / 60 / 15)  # 15m assumed
            except Exception:
                pass

            risk = abs(p.avg_entry_price - (p.sl if p.sl else 0))
            rr = abs(final_exit.price - p.avg_entry_price) / risk if risk > 0 else 0
            if final_exit.pnl < 0:
                rr = -rr

            fee = getattr(p, "_bt_fee", 0.0)
            net_pnl = p.realized_pnl - fee
            trades.append(BacktestTrade(
                entry_ts=p.opened_at,
                exit_ts=p.closed_at or final_exit.timestamp,
                symbol=p.symbol,
                direction=p.direction,
                entries_count=len(p.entries),
                avg_entry=round(p.avg_entry_price, 4),
                exit_price=round(final_exit.price, 4),
                size=round(p.total_size_entered, 6),
                pnl=round(net_pnl, 2),
                pnl_pct=round((net_pnl / initial_balance) * 100, 2),
                rr_realized=round(rr, 2),
                exit_reason=final_exit.reason,
                holding_bars=holding_bars,
            ))

        # Aggregate metrics
        total = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        be = [t for t in trades if t.pnl == 0]

        sum_wins = sum(t.pnl for t in wins)
        sum_losses = abs(sum(t.pnl for t in losses))
        profit_factor = sum_wins / sum_losses if sum_losses > 0 else (999 if sum_wins > 0 else 0)

        # Consecutive loss max
        consec_max = 0
        cur_consec = 0
        for t in trades:
            if t.pnl < 0:
                cur_consec += 1
                consec_max = max(consec_max, cur_consec)
            else:
                cur_consec = 0

        # Sharpe-like: trade returns stddev
        trade_returns = [t.pnl_pct for t in trades]
        if len(trade_returns) > 2:
            mean_ret = np.mean(trade_returns)
            std_ret = np.std(trade_returns)
            sharpe = mean_ret / std_ret if std_ret > 0 else 0
        else:
            sharpe = 0

        # By exit reason
        by_reason = {}
        for t in trades:
            by_reason[t.exit_reason] = by_reason.get(t.exit_reason, 0) + 1

        return BacktestResult(
            symbol=symbol,
            start_ts=str(df_entry.index[0]),
            end_ts=str(df_entry.index[-1]),
            bars_tested=bars_tested,
            initial_balance=initial_balance,
            final_balance=round(final_balance, 2),
            peak_balance=round(peak_balance, 2),
            total_return_pct=round((final_balance - initial_balance) / initial_balance * 100, 2),
            max_drawdown_pct=round((peak_balance - final_balance) / peak_balance * 100, 2) if peak_balance > 0 else 0,
            total_trades=total,
            wins=len(wins), losses=len(losses), breakeven=len(be),
            win_rate=round(len(wins) / total * 100, 1) if total > 0 else 0,
            profit_factor=round(profit_factor, 2),
            avg_win=round(sum_wins / len(wins), 2) if wins else 0,
            avg_loss=round(-sum_losses / len(losses), 2) if losses else 0,
            avg_rr=round(np.mean([t.rr_realized for t in trades]), 2) if trades else 0,
            avg_hold_bars=round(np.mean([t.holding_bars for t in trades]), 1) if trades else 0,
            largest_win=round(max([t.pnl for t in trades], default=0), 2),
            largest_loss=round(min([t.pnl for t in trades], default=0), 2),
            consecutive_loss_max=consec_max,
            sharpe_like=round(sharpe, 2),
            by_exit_reason=by_reason,
            trades=trades,
            equity_curve=equity_curve,
        )
