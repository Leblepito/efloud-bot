"""
Multi-seed Backtest — Strategy Robustness Test
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Farklı piyasa koşullarında (uptrend, downtrend, choppy) bot'un performansı.
"""
import sys, logging, numpy as np, pandas as pd, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.ERROR)  # Spam azalt

from backtest.runner import BacktestRunner


def gen_data(n, tf_min, seed, drift, vol):
    np.random.seed(seed)
    returns = np.random.normal(drift, vol, n)
    closes = 2000 * np.exp(np.cumsum(returns))
    o, h, l = [], [], []
    for i, c in enumerate(closes):
        p = closes[i-1] if i > 0 else 2000
        op = p * (1 + np.random.normal(0, vol * 0.3))
        bh, bl = max(op, c), min(op, c)
        w = vol * p * np.random.uniform(0.2, 1.5)
        o.append(op); h.append(bh + w * 0.5); l.append(bl - w * 0.5)
    v = np.random.lognormal(10, 0.5, n)
    now = pd.Timestamp.now(tz='UTC').tz_localize(None)
    ts = pd.date_range(end=now, periods=n, freq=f'{tf_min}min')
    return pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': closes, 'volume': v}, index=ts)


def run_scenario(name, drift, vol, seed, config):
    df_e = gen_data(1000, 15, seed, drift, vol)
    df_m = gen_data(400, 60, seed, drift, vol)
    df_h = gen_data(200, 240, seed, drift, vol)
    df_d = gen_data(60, 1440, seed, drift, vol * 2)

    start_p = df_e['close'].iloc[0]
    end_p = df_e['close'].iloc[-1]
    move_pct = (end_p - start_p) / start_p * 100

    runner = BacktestRunner(config, warmup_bars=200, step_every_n_bars=4)
    result = runner.run(
        symbol="ETH/USDT",
        df_htf=df_h, df_mtf=df_m, df_entry=df_e, df_daily=df_d,
        initial_balance=10000.0,
    )

    return {
        "scenario": name, "seed": seed, "market_move": move_pct,
        "trades": result.total_trades, "win_rate": result.win_rate,
        "return_pct": result.total_return_pct, "dd_pct": result.max_drawdown_pct,
        "pf": result.profit_factor, "sharpe": result.sharpe_like,
    }


def main():
    print("━" * 90)
    print("  MULTI-SEED BACKTEST — Strategy Robustness")
    print("━" * 90)

    config = {
        "exchange": {"leverage": 1},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "structure": {"swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                        "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"risk_per_trade_pct": 1.5, "max_open_positions": 3,
                 "min_rr": 1.8, "min_confluence": 55},
        "operation": {"dry_run": True, "watch_only": False},
        "safety": {
            "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
            "max_position_notional_pct": 20, "max_total_exposure": 5.0,
            "max_holding_hours": 240, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
        },
    }

    scenarios = [
        ("Strong uptrend",    0.0005,  0.006, 1),
        ("Mild uptrend",       0.0002,  0.008, 2),
        ("Choppy/sideways",    0.0,     0.006, 3),
        ("Mild downtrend",     -0.0002, 0.008, 4),
        ("Strong downtrend",   -0.0005, 0.006, 5),
        ("High volatility",    0.0002,  0.015, 6),
        ("Low volatility",     0.0003,  0.003, 7),
    ]

    results = []
    for name, drift, vol, seed in scenarios:
        try:
            r = run_scenario(name, drift, vol, seed, config)
            results.append(r)
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            continue

    # Display
    print(f"\n{'Scenario':<25} {'Move%':>8} {'Trades':>7} {'WR%':>6} {'Ret%':>8} {'DD%':>6} {'PF':>6} {'Shp':>6}")
    print("─" * 90)
    for r in results:
        print(f"{r['scenario']:<25} {r['market_move']:>+7.1f} {r['trades']:>7} "
              f"{r['win_rate']:>6.1f} {r['return_pct']:>+7.2f} {r['dd_pct']:>5.1f} "
              f"{r['pf']:>5.2f} {r['sharpe']:>5.2f}")

    # Özet
    if results:
        avg_ret = np.mean([r['return_pct'] for r in results])
        avg_wr = np.mean([r['win_rate'] for r in results if r['trades'] > 0]) if any(r['trades'] > 0 for r in results) else 0
        total_trades = sum(r['trades'] for r in results)
        profitable_scenarios = sum(1 for r in results if r['return_pct'] > 0)

        print("─" * 90)
        print(f"{'AGGREGATE':<25} {'':>8} {total_trades:>7} {avg_wr:>6.1f} {avg_ret:>+7.2f}")
        print(f"\n  {profitable_scenarios}/{len(results)} scenarios profitable")
        print(f"  Avg return: {avg_ret:+.2f}% | Avg win rate: {avg_wr:.1f}%")


if __name__ == "__main__":
    main()
