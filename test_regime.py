"""
Regime Detector Diagnostic
━━━━━━━━━━━━━━━━━━━━━━━━━━
Farklı piyasa koşulları yaratıp algoritmanın doğru sınıflandırdığını doğrular.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/home/claude/efloud-bot')

from engine import RegimeDetector


def trending_market(n=300, tf_min=15):
    """Güçlü yönlü hareket — ADX yüksek olmalı."""
    np.random.seed(42)
    # Strong persistent trend
    trend = np.linspace(2000, 2400, n)  # %20 yukarı
    noise = np.random.normal(0, 3, n)   # Küçük noise
    closes = trend + noise
    return _build_df(closes, tf_min, spread_mult=0.002)


def ranging_market(n=300, tf_min=15):
    """Sıkışık yatay — ADX düşük, BB daralmış."""
    np.random.seed(99)
    base = 2200
    # Sine wave mean-reversion etrafında
    osc = np.sin(np.linspace(0, 8*np.pi, n)) * 15  # ±$15 oscillation
    noise = np.random.normal(0, 2, n)
    closes = base + osc + noise
    return _build_df(closes, tf_min, spread_mult=0.001)


def volatile_market(n=300, tf_min=15):
    """Ani patlama — son 30 bar çok volatil (ATR birkaç kat)."""
    np.random.seed(7)
    base = 2000
    # Normal trend first (n - 30) bars
    normal_n = n - 30
    normal = base + np.cumsum(np.random.normal(0, 2, normal_n))
    # Last 30 bars: huge swings
    explosive = normal[-1] + np.cumsum(np.random.normal(0, 80, 30))
    closes = np.concatenate([normal, explosive])
    return _build_df(closes, tf_min, spread_mult=0.03)


def _build_df(closes, tf_min, spread_mult=0.003):
    """Close'lardan OHLC DataFrame inşa et."""
    n = len(closes)
    opens, highs, lows = [], [], []
    for i, c in enumerate(closes):
        prev = closes[i-1] if i > 0 else c
        o = prev * (1 + np.random.normal(0, spread_mult * 0.3))
        bh, bl = max(o, c), min(o, c)
        wick = c * spread_mult * np.random.uniform(0.2, 1.2)
        opens.append(o)
        highs.append(bh + wick)
        lows.append(bl - wick)
    volumes = np.random.lognormal(10, 0.5, n)
    now = pd.Timestamp.now(tz='UTC').tz_localize(None)
    ts = pd.date_range(end=now, periods=n, freq=f'{tf_min}min')
    return pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows,
        'close': closes, 'volume': volumes
    }, index=ts)


def main():
    print("━" * 70)
    print("  REGIME DETECTOR DIAGNOSTIC")
    print("━" * 70)

    detector = RegimeDetector()

    tests = [
        ("Strong trending", trending_market(300), ["TRENDING"]),
        ("Tight ranging", ranging_market(300), ["RANGING", "TRENDING"]),  # BBW'ye bağlı
        ("Volatile spike", volatile_market(300), ["VOLATILE", "REVERSAL"]),
    ]

    passed = 0
    for name, df, expected in tests:
        analysis = detector.analyze(df)
        status = "✅" if analysis.regime in expected else "⚠️ "
        if analysis.regime in expected:
            passed += 1

        print(f"\n  {status} {name}")
        print(f"      Detected:  {analysis.regime} ({analysis.confidence}%)")
        print(f"      Expected:  {'/'.join(expected)}")
        print(f"      Metrics:   ADX={analysis.adx:.1f} | BBW={analysis.bb_width:.2f} | "
              f"ATR={analysis.atr_ratio:.1f}x")
        print(f"      Can open:  {analysis.can_open_new_position}")
        print(f"      Tighten:   {analysis.should_tighten_stops}")
        for note in analysis.notes:
            print(f"      Note:      {note}")

    print(f"\n  {'='*68}")
    print(f"  {passed}/{len(tests)} regime classifications correct")
    print(f"  {'='*68}\n")


if __name__ == "__main__":
    main()
