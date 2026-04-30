"""
Real-Data Backtest — Binance historical OHLCV + BacktestRunner.
Phase 2 kararı için gerçek piyasa verisinde stratejiyi test eder.
"""
import sys, time, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.ERROR)

import pandas as pd
import ccxt
from backtest.runner import BacktestRunner


def fetch_binance(symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
    ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
    raw = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


PHASE2_CONFIG = {
    "exchange": {"leverage": 3},
    "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
    "structure": {"swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                    "eq_threshold_pct": 0.1, "range_lookback": 50},
    "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
    "risk": {"risk_per_trade_pct": 0.25, "max_open_positions": 4,
             "min_rr": 1.8, "min_confluence": 65},
    "operation": {"dry_run": True, "watch_only": False},
    "safety": {
        "daily_loss_limit_pct": 1.5, "weekly_drawdown_limit_pct": 5.0,
        "consecutive_loss_limit": 2, "consecutive_pause_min": 180,
        "max_position_notional_pct": 1.0, "max_total_exposure": 1.5,
        "max_holding_hours": 24, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
    },
}


def run_symbol(symbol: str, balance: float = 2000.0):
    print(f"\n📡 Fetching {symbol} from Binance Futures...")
    try:
        df_e = fetch_binance(symbol, "15m", 1000)
        time.sleep(0.3)
        df_m = fetch_binance(symbol, "1h", 500)
        time.sleep(0.3)
        df_h = fetch_binance(symbol, "4h", 300)
        time.sleep(0.3)
        df_d = fetch_binance(symbol, "1d", 100)
        time.sleep(0.3)
    except Exception as e:
        print(f"  ❌ Fetch failed: {e}")
        return None

    span = (df_e.index[-1] - df_e.index[0]).total_seconds() / 86400
    print(f"   {len(df_e)} bars 15m, {span:.1f} days "
          f"(${df_e['low'].min():,.2f} - ${df_e['high'].max():,.2f})")

    runner = BacktestRunner(PHASE2_CONFIG, warmup_bars=200, step_every_n_bars=1,
                              fee_rate=0.0004)  # Binance Futures taker = %0.04
    r = runner.run(symbol=symbol, df_htf=df_h, df_mtf=df_m, df_entry=df_e,
                    df_daily=df_d, initial_balance=balance)

    move = (df_e['close'].iloc[-1] - df_e['close'].iloc[0]) / df_e['close'].iloc[0] * 100
    return {
        "symbol": symbol, "days": span, "move_pct": move,
        "trades": r.total_trades, "wins": r.wins,
        "wr": r.win_rate, "ret": r.total_return_pct, "dd": r.max_drawdown_pct,
        "pf": r.profit_factor, "sharpe": r.sharpe_like,
    }


def main():
    print("━" * 90)
    print("  PHASE 2 REAL-DATA BACKTEST — Binance historical + min_rr=1.8 fix")
    print("━" * 90)

    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "DOGE/USDT"]
    results = []
    for s in symbols:
        r = run_symbol(s)
        if r:
            results.append(r)

    if not results:
        print("\nHiç sonuç yok.")
        return

    print(f"\n{'Symbol':<10} {'Days':>5} {'Move%':>7} {'Trades':>7} {'WR%':>6} "
          f"{'Ret%':>8} {'DD%':>6} {'PF':>6} {'Shp':>6}")
    print("─" * 90)
    for r in results:
        print(f"{r['symbol']:<10} {r['days']:>5.1f} {r['move_pct']:>+6.1f} "
              f"{r['trades']:>7} {r['wr']:>6.1f} {r['ret']:>+7.2f} "
              f"{r['dd']:>5.1f} {r['pf']:>5.2f} {r['sharpe']:>5.2f}")

    import numpy as np
    total_trades = sum(r['trades'] for r in results)
    profitable = sum(1 for r in results if r['ret'] > 0)
    avg_ret = np.mean([r['ret'] for r in results])
    weighted_wr = np.mean([r['wr'] for r in results if r['trades'] > 0]) \
                  if any(r['trades'] > 0 for r in results) else 0.0

    print("─" * 90)
    print(f"\n  Toplam trade: {total_trades} | Profitable symbols: {profitable}/{len(results)}")
    print(f"  Avg return: {avg_ret:+.2f}% | Avg win rate: {weighted_wr:.1f}%")

    if avg_ret > 1.0 and profitable >= len(results) * 0.6:
        verdict = "✅ Phase 2 için yeşil ışık"
    elif avg_ret > 0 and profitable >= len(results) * 0.5:
        verdict = "🟡 Marjinal — Phase 1 forward test öneriyorum"
    else:
        verdict = "🔴 Phase 2 = para yakar. Strateji düzeltilmeli"
    print(f"\n  Verdict: {verdict}")


if __name__ == "__main__":
    main()
