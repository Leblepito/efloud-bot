"""
Backtest Integration Test
━━━━━━━━━━━━━━━━━━━━━━━━━
Synthetic trending ETH data ile tam backtest.
"""
import sys, logging, numpy as np, pandas as pd, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.WARNING,  # Backtest log spam azalt
    format='%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s'
)

from backtest.runner import BacktestRunner


def gen_data(n, tf_min, seed, drift=0.0003, vol=0.008):
    np.random.seed(seed)
    returns = np.random.normal(drift, vol, n)
    closes = 2000 * np.exp(np.cumsum(returns))
    opens, highs, lows = [], [], []
    for i, c in enumerate(closes):
        prev = closes[i-1] if i > 0 else 2000
        o = prev * (1 + np.random.normal(0, vol * 0.3))
        bh, bl = max(o, c), min(o, c)
        w = vol * prev * np.random.uniform(0.2, 1.5)
        opens.append(o)
        highs.append(bh + w * np.random.uniform(0, 1))
        lows.append(bl - w * np.random.uniform(0, 1))
    volumes = np.random.lognormal(10, 0.5, n)
    now = pd.Timestamp.now(tz='UTC').tz_localize(None)
    ts = pd.date_range(end=now, periods=n, freq=f'{tf_min}min')
    return pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows,
        'close': closes, 'volume': volumes
    }, index=ts)


def main():
    print("━" * 70)
    print("  BACKTEST INTEGRATION TEST")
    print("━" * 70)

    config = {
        "exchange": {"leverage": 1},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "structure": {
            "swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
            "eq_threshold_pct": 0.1, "range_lookback": 50,
        },
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {
            "risk_per_trade_pct": 1.5, "max_open_positions": 3,
            "min_rr": 1.5, "min_confluence": 40,
        },
        "operation": {"dry_run": True, "watch_only": False},
        "safety": {
            "daily_loss_limit_pct": 3.0,
            "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3,
            "consecutive_pause_min": 120,
            "max_position_notional_pct": 20,
            "max_total_exposure": 5.0,
            "max_holding_hours": 240,  # backtest için gevşet
            "min_sl_atr": 0.5,
            "max_sl_atr": 5.0,
        },
    }

    # 1000 bar 15m = ~10.5 gün
    print("\n📊 Generating synthetic 15m data (1000 bars = ~10 days)...")
    df_entry = gen_data(1000, 15, 42, drift=0.0004, vol=0.008)
    df_mtf = gen_data(400, 60, 42, drift=0.0004, vol=0.008)
    df_htf = gen_data(200, 240, 42, drift=0.0004, vol=0.008)
    df_daily = gen_data(60, 1440, 42, drift=0.0004, vol=0.015)

    print(f"  Entry range: ${df_entry['low'].min():.2f} - ${df_entry['high'].max():.2f}")
    print(f"  Start → End: ${df_entry['close'].iloc[0]:.2f} → ${df_entry['close'].iloc[-1]:.2f}")

    print("\n🧪 Running backtest...")
    runner = BacktestRunner(config, warmup_bars=200, step_every_n_bars=4)
    result = runner.run(
        symbol="ETH/USDT",
        df_htf=df_htf, df_mtf=df_mtf, df_entry=df_entry, df_daily=df_daily,
        initial_balance=10000.0,
        verbose=False,
    )

    print("\n" + "═" * 70)
    print(result.to_summary())
    print("═" * 70)

    # Trade listesi
    if result.trades:
        print("\n📋 First 10 trades:")
        print(f"  {'#':>3} {'Dir':>5} {'Entry':>10} {'Exit':>10} {'PnL':>10} {'R:R':>6} {'Reason':>10}")
        for i, t in enumerate(result.trades[:10], 1):
            print(f"  {i:>3} {t.direction:>5} {t.avg_entry:>10.2f} {t.exit_price:>10.2f} "
                  f"{t.pnl:>+10.2f} {t.rr_realized:>+6.2f} {t.exit_reason:>10}")
        if len(result.trades) > 10:
            print(f"  ... {len(result.trades) - 10} more trades")

    # Equity curve sample
    if result.equity_curve:
        print(f"\n📈 Equity curve ({len(result.equity_curve)} snapshots):")
        for pt in result.equity_curve[::max(1, len(result.equity_curve) // 5)]:
            print(f"  {pt['ts']}: ${pt['balance']:,.2f} | price ${pt['price']:,.2f}")


if __name__ == "__main__":
    main()
