"""
Safe Orchestrator Test
━━━━━━━━━━━━━━━━━━━━━
Tüm güvenlik katmanlarının çalıştığını doğrular.
"""

import sys, logging, numpy as np, pandas as pd
sys.path.insert(0, '/home/claude/efloud-bot')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s'
)

from engine import SafeOrchestrator


def gen_ohlcv(n=500, start=2000.0, drift=0.0003, vol=0.006, tf_min=15, seed=42):
    np.random.seed(seed)
    returns = np.random.normal(drift, vol, n)
    closes = start * np.exp(np.cumsum(returns))
    highs, lows, opens = [], [], []
    for i, c in enumerate(closes):
        prev = closes[i-1] if i > 0 else start
        o = prev * (1 + np.random.normal(0, vol*0.3))
        bh, bl = max(o, c), min(o, c)
        w = vol * prev * np.random.uniform(0.2, 1.5)
        highs.append(bh + w * np.random.uniform(0, 1))
        lows.append(bl - w * np.random.uniform(0, 1))
        opens.append(o)
    volumes = np.random.lognormal(10, 0.5, n)
    # Fresh timestamps — son mum şimdiden N TF önce olmalı (max 1 TF stale)
    now = pd.Timestamp.now(tz='UTC').tz_localize(None)
    # Son mum şu anki bara göre ayarla
    ts = pd.date_range(end=now, periods=n, freq=f'{tf_min}min')
    return pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows,
        'close': closes, 'volume': volumes
    }, index=ts)


def _run_case(name, orch, cfg_override=None, data_override=None):
    """Tek test case'i çalıştır ve sonucu yazdır."""
    print(f"\n{'═'*70}\n  TEST: {name}\n{'═'*70}")

    data = data_override or {}
    df_entry = data.get("entry") if data.get("entry") is not None else gen_ohlcv(500, tf_min=15)
    df_mtf = data.get("mtf") if data.get("mtf") is not None else gen_ohlcv(300, tf_min=60)
    df_htf = data.get("htf") if data.get("htf") is not None else gen_ohlcv(200, tf_min=240)
    df_daily = data.get("daily") if data.get("daily") is not None else gen_ohlcv(90, tf_min=1440)

    result = orch.run_cycle(
        symbol="ETH/USDT",
        df_htf=df_htf, df_mtf=df_mtf, df_entry=df_entry, df_daily=df_daily,
        balance=10000,
    )

    print(f"  Price:         ${result.current_price:,.2f}")
    print(f"  HTF bias:      {result.htf_bias}")
    print(f"  Regime:        {result.regime}")
    print(f"  Breaker:       {result.breaker_state}")
    print(f"  Can trade:     {result.can_trade}")
    print(f"  Stale data:    {result.stale_data}")
    print(f"  Actions:       {result.actions_taken}")
    if result.warnings:
        print(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings[:3]:
            print(f"    - {w}")
    return result


def main():
    print("━" * 70)
    print("  SAFE ORCHESTRATOR — SAFETY LAYER TEST SUITE")
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
            "starting_balance": 10000,
            "max_position_notional_pct": 20,
            "max_total_exposure": 5.0,
            "max_holding_hours": 48,
            "volatile_atr_mult": 2.5,
        },
    }

    # Her test için fresh state
    import shutil, os
    state_dir = "/tmp/efloud_test_state"
    shutil.rmtree(state_dir, ignore_errors=True)

    # ─────────────────────────────────────────
    # TEST 1: Normal cycle, trending market
    # ─────────────────────────────────────────
    orch1 = SafeOrchestrator(config, state_dir=state_dir)
    r1 = _run_case("1. Normal trending market", orch1)
    assert r1.breaker_state == "OPEN", "Breaker should be OPEN"

    # ─────────────────────────────────────────
    # TEST 2: Ranging / choppy market
    # ─────────────────────────────────────────
    shutil.rmtree(state_dir, ignore_errors=True)
    orch2 = SafeOrchestrator(config, state_dir=state_dir)
    # Low volatility ranging data
    ranging_entry = gen_ohlcv(500, drift=0.0, vol=0.001, tf_min=15, seed=99)
    ranging_mtf = gen_ohlcv(300, drift=0.0, vol=0.001, tf_min=60, seed=99)
    ranging_htf = gen_ohlcv(200, drift=0.0, vol=0.001, tf_min=240, seed=99)
    r2 = _run_case("2. Ranging market (low ADX)", orch2,
                    data_override={"entry": ranging_entry, "mtf": ranging_mtf,
                                     "htf": ranging_htf})
    print(f"  → Expected RANGING or VOLATILE regime, got: {r2.regime}")

    # ─────────────────────────────────────────
    # TEST 3: Volatile market
    # ─────────────────────────────────────────
    shutil.rmtree(state_dir, ignore_errors=True)
    orch3 = SafeOrchestrator(config, state_dir=state_dir)
    volatile_entry = gen_ohlcv(500, drift=0.0003, vol=0.025, tf_min=15, seed=7)
    volatile_mtf = gen_ohlcv(300, drift=0.0003, vol=0.025, tf_min=60, seed=7)
    volatile_htf = gen_ohlcv(200, drift=0.0003, vol=0.025, tf_min=240, seed=7)
    r3 = _run_case("3. Volatile market", orch3,
                    data_override={"entry": volatile_entry, "mtf": volatile_mtf,
                                     "htf": volatile_htf})
    print(f"  → Regime: {r3.regime}")

    # ─────────────────────────────────────────
    # TEST 4: Circuit Breaker — daily loss limit
    # ─────────────────────────────────────────
    print(f"\n{'═'*70}\n  TEST: 4. Circuit Breaker — Daily Loss Limit\n{'═'*70}")
    shutil.rmtree(state_dir, ignore_errors=True)
    orch4 = SafeOrchestrator(config, state_dir=state_dir)
    # %4 zarar kaydet (limit %3)
    orch4.breaker.record_trade(-400)  # -$400 = -%4
    status = orch4.breaker.check()
    print(f"  After -$400 loss:")
    print(f"    State: {status.state.value}")
    print(f"    Can trade: {status.can_trade}")
    print(f"    Reason: {status.reason}")
    assert status.state.value == "TRIPPED", "Should TRIP at daily limit"
    print(f"  ✅ Breaker correctly tripped")

    # ─────────────────────────────────────────
    # TEST 5: Consecutive Loss
    # ─────────────────────────────────────────
    print(f"\n{'═'*70}\n  TEST: 5. Consecutive Loss Pause\n{'═'*70}")
    shutil.rmtree(state_dir, ignore_errors=True)
    orch5 = SafeOrchestrator(config, state_dir=state_dir)
    for i in range(3):
        orch5.breaker.record_trade(-50)  # Küçük kayıplar
    status = orch5.breaker.check()
    print(f"  After 3 consecutive losses: {status.state.value} | {status.reason}")
    assert status.state.value == "TRIPPED", "Should TRIP after N consecutive losses"
    print(f"  ✅ Consecutive loss pause triggered")

    # ─────────────────────────────────────────
    # TEST 6: Weekly Drawdown HALT
    # ─────────────────────────────────────────
    print(f"\n{'═'*70}\n  TEST: 6. Weekly Drawdown → HALT\n{'═'*70}")
    shutil.rmtree(state_dir, ignore_errors=True)
    orch6 = SafeOrchestrator(config, state_dir=state_dir)
    orch6.breaker.peak_balance = 10000
    orch6.breaker.current_balance = 9100  # -%9 from peak
    status = orch6.breaker.check()
    print(f"  After -9% drawdown: {status.state.value} | {status.reason}")
    assert status.state.value == "HALTED", "Should HALT at weekly DD"
    print(f"  ✅ Weekly DD halt triggered")

    # Manual reset test
    orch6.breaker.manual_reset("test")
    assert orch6.breaker.check().state.value == "OPEN"
    print(f"  ✅ Manual reset works")

    # ─────────────────────────────────────────
    # TEST 7: State persistence
    # ─────────────────────────────────────────
    print(f"\n{'═'*70}\n  TEST: 7. State Persistence & Recovery\n{'═'*70}")
    shutil.rmtree(state_dir, ignore_errors=True)
    orch7a = SafeOrchestrator(config, state_dir=state_dir)
    orch7a.breaker.current_balance = 11500
    orch7a.breaker.peak_balance = 12000
    orch7a.breaker.consecutive_losses = 2
    orch7a._persist_state()
    print(f"  Saved: balance={orch7a.breaker.current_balance}, consec={orch7a.breaker.consecutive_losses}")

    orch7b = SafeOrchestrator(config, state_dir=state_dir)
    print(f"  Loaded: balance={orch7b.breaker.current_balance}, consec={orch7b.breaker.consecutive_losses}")
    assert orch7b.breaker.current_balance == 11500
    assert orch7b.breaker.consecutive_losses == 2
    print(f"  ✅ State survived restart")

    # ─────────────────────────────────────────
    # TEST 8: Position Guard — size cap
    # ─────────────────────────────────────────
    print(f"\n{'═'*70}\n  TEST: 8. Position Guard — Size Cap\n{'═'*70}")
    shutil.rmtree(state_dir, ignore_errors=True)
    orch8 = SafeOrchestrator(config, state_dir=state_dir)

    # %50 notional: çok büyük
    result = orch8.pos_guard.can_open_position(
        balance=10000, entry=2000, size=2.5,  # $5000 notional = %50
        sl=1980, atr=20, direction="LONG", symbol="ETH/USDT",
        existing_positions=[]
    )
    print(f"  Oversized trade: allowed={result.allowed}, reason={result.reason}")
    assert not result.allowed
    print(f"  ✅ Size cap enforced")

    # SL çok sıkı
    result = orch8.pos_guard.can_open_position(
        balance=10000, entry=2000, size=0.5,
        sl=1999.5, atr=20, direction="LONG", symbol="ETH/USDT",  # SL 0.5$, ATR 20
        existing_positions=[]
    )
    print(f"  Too-tight SL: allowed={result.allowed}, reason={result.reason}")
    assert not result.allowed
    print(f"  ✅ Tight SL rejected (whipsaw protection)")

    print(f"\n{'═'*70}")
    print(f"  ✅ ALL TESTS PASSED")
    print(f"{'═'*70}")


if __name__ == "__main__":
    main()
