"""DOGE +15% hareketi neden kaçırıldı? Sinyal pipeline'ını izle."""
import sys, time, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import ccxt
from engine.smc import SMCEngine
from engine.signals import generate_signals

logging.basicConfig(level=logging.INFO, format='%(name)-22s | %(levelname)-5s | %(message)s')


def fetch(symbol, tf, limit):
    ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
    raw = ex.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


def main():
    print("DOGE/USDT diagnose — 1000 bars 15m\n")
    df_e = fetch("DOGE/USDT", "15m", 1000)
    time.sleep(0.2)
    df_m = fetch("DOGE/USDT", "1h", 500)
    time.sleep(0.2)
    df_h = fetch("DOGE/USDT", "4h", 300)
    time.sleep(0.2)
    df_d = fetch("DOGE/USDT", "1d", 100)

    print(f"15m range: ${df_e['low'].min():.4f} → ${df_e['high'].max():.4f}")
    print(f"15m start→end: ${df_e['close'].iloc[0]:.4f} → ${df_e['close'].iloc[-1]:.4f} "
          f"({(df_e['close'].iloc[-1]/df_e['close'].iloc[0]-1)*100:+.1f}%)\n")

    eng = SMCEngine(swing_lb=5, ob_seq=5, body_mode=True, eq_thr=0.001,
                     range_lb=50, ote_lo=0.618, ote_hi=0.786)

    # HTF bias
    htf_a = eng.analyze(df_h)
    print(f"HTF (4h) bias: {htf_a['trend']}")
    print(f"HTF range: {htf_a['range'].lo:.4f} - {htf_a['range'].hi:.4f}\n")

    # Test farklı min_rr / min_conf kombinasyonları
    print(f"{'min_rr':>7} {'min_conf':>10} {'sinyaller':>10}  detail")
    print("─" * 80)
    for rr in [1.5, 1.8, 2.0]:
        for conf in [40, 50, 55, 65]:
            sigs = generate_signals(eng, df_h, df_m, df_e,
                                    min_confluence=conf, min_rr=rr,
                                    fib_ext=1.618, recency_bars=40,
                                    df_daily=df_d, daily_filter_strict=False)
            detail = ""
            if sigs:
                detail = "; ".join(f"{s.direction}@{s.entry:.4f} R:R={s.rr1}" for s in sigs[:3])
            print(f"{rr:>7.1f} {conf:>10} {len(sigs):>10}  {detail}")


if __name__ == "__main__":
    main()
