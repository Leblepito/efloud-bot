def derive(config: dict) -> dict:
    safety = (config or {}).get("safety", {}) or {}
    wk = float(safety.get("weekly_drawdown_limit_pct", 8) or 8)
    return {
        # R4 drawdown sentinel — fractions of the real breaker limit
        "dd_warn_pct": round(wk * 0.6, 2),
        "dd_alert_pct": round(wk * 0.8, 2),
        "dd_critical_pct": round(wk * 0.95, 2),
        # R2 margin / liquidation distance (% from mark to liq price)
        "liq_distance_warn_pct": 20,
        # 2026-07-24: 10 -> 7 (operator onayi, sohbet). 10x pozisyon dogumda
        # liq'e ~%9.3-9.5 mesafede dogar (1/kaldirac - maintenance) -> esik 10
        # iken her 10x pozisyon acilistan itibaren omur boyu WARN uretiyordu.
        # 7 = ~%2.5+ aleyhte hareket sonrasi oter; critical=5 katmani ayni.
        "liq_distance_alert_pct": 7,
        "liq_distance_critical_pct": 5,
        "margin_ratio_warn": 0.5,
        "margin_ratio_critical": 0.75,
        # R5 exposure
        "concentration_warn_pct": 30,
        # R6 funding
        "funding_rate_elevated_8h": 0.001,        # 0.1% / 8h
        "funding_cost_pct_of_pnl_warn": 5.0,
        # M2 rate-limit (Binance weight budget)
        "weight_warn_pct": 75,
        "weight_alert_pct": 90,
        "weight_critical_pct": 95,
        # M6 fill anomaly
        "fill_z_warn": 3.0,
        # M1 healthz consecutive failures before paging
        "healthz_fail_threshold": 3,
        # D1/D2 market collect
        "oi_spike_pct_4h": 10.0,
        "ohlcv_gap_tolerance_bars": 1,
        # S1 backtest regression
        "sharpe_regression_warn_pct": 10.0,
        "sharpe_regression_escalate_pct": 20.0,
    }
