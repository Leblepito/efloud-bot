# scripts/routines/resolve_signals.py  (resolution core; fetch/orchestration added in Task 4)
from __future__ import annotations

def _touch(direction, bar, sl, tp):
    """Return ('sl'|'tp'|None) using conservative same-bar=SL."""
    hi, lo = bar["high"], bar["low"]
    if direction == "LONG":
        sl_hit = lo <= sl
        tp_hit = hi >= tp
    else:
        sl_hit = hi >= sl
        tp_hit = lo <= tp
    if sl_hit:
        return "sl"
    if tp_hit:
        return "tp"
    return None

def replay_fill(rec, bars, smc_version, fill_window_bars=8):
    """MARKET-at-confirmation (v2) or next-bar-open (v1). Returns dict or None (unfilled).

    KNOWN FIDELITY GAP (plan-review correction #7): the real v2 confirmation lives in
    engine/smc_v2/confirmation.py:confirm_entry and enforces prior-opposite-bar + true
    body-engulfing + in-zone. This shadow approximation uses (directional body) AND
    (close beyond the prior bar's high/low) as a proxy. It is an APPROXIMATION; any v2
    edge verdict must carry this caveat (see spec 3.1 and edge_report disclaimer).
    """
    post = [b for b in bars if b["ts"] > rec.ts_emitted]
    if not post:
        return None
    if smc_version == "v1":
        b = post[0]
        # fill_idx_ts is set to ts_emitted so that race_sl_tp includes the fill bar itself
        # (v1 fills at next-bar open; the rest of that bar is part of the race window)
        return {"fill_price": b["open"], "ts_filled": b["ts"], "bars_to_fill": 1, "fill_idx_ts": rec.ts_emitted}
    window = post[:fill_window_bars]
    for i, b in enumerate(window):
        body = b["close"] - b["open"]
        confirmed = (rec.direction == "LONG" and body > 0) or (rec.direction == "SHORT" and body < 0)
        if i > 0:
            prev = window[i - 1]
            confirmed = confirmed and (
                (rec.direction == "LONG" and b["close"] > prev["high"]) or
                (rec.direction == "SHORT" and b["close"] < prev["low"]))
        else:
            confirmed = False  # need a prior bar to judge engulfing
        if confirmed:
            return {"fill_price": b["close"], "ts_filled": b["ts"], "bars_to_fill": i + 1, "fill_idx_ts": b["ts"]}
    return None

def race_sl_tp(rec, bars, fill_ts, horizon_ms):
    """Race from the bar STRICTLY AFTER fill. Returns outcome dict, or None -> caller times out."""
    risk = abs(rec.emitted_entry - rec.sl)
    race = [b for b in bars if b["ts"] > fill_ts and b["ts"] <= fill_ts + horizon_ms]
    mfe = mae = 0.0
    for n, b in enumerate(race, start=1):
        if rec.direction == "LONG":
            mfe = max(mfe, (b["high"] - rec.emitted_entry) / risk)
            mae = min(mae, (b["low"] - rec.emitted_entry) / risk)
        else:
            mfe = max(mfe, (rec.emitted_entry - b["low"]) / risk)
            mae = min(mae, (rec.emitted_entry - b["high"]) / risk)
        hit = _touch(rec.direction, b, rec.sl, rec.tp1)
        if hit == "sl":
            return {"outcome": "sl", "hypo_r_raw": -1.0, "mfe_r": mfe, "mae_r": mae,
                    "bars_to_resolve": n, "ts_resolved": b["ts"]}
        if hit == "tp":
            return _resolve_tp(rec, bars, b, n, risk, mfe, mae, horizon_ms, fill_ts)
    return None

def _resolve_tp(rec, bars, tp1_bar, n, risk, mfe, mae, horizon_ms, fill_ts):
    rr1 = (rec.tp1 - rec.emitted_entry) / risk if rec.direction == "LONG" else (rec.emitted_entry - rec.tp1) / risk
    if rec.exit_model == "single_target" or rec.tp2 is None:
        return {"outcome": "tp1", "hypo_r_raw": rr1, "mfe_r": mfe, "mae_r": mae,
                "bars_to_resolve": n, "ts_resolved": tp1_bar["ts"]}
    rr2 = (rec.tp2 - rec.emitted_entry) / risk if rec.direction == "LONG" else (rec.emitted_entry - rec.tp2) / risk
    after = [b for b in bars if b["ts"] > tp1_bar["ts"] and b["ts"] <= fill_ts + horizon_ms]
    runner = 0.0
    for b in after:
        h2 = _touch(rec.direction, b, rec.emitted_entry, rec.tp2)
        if h2 == "tp":
            runner = rr2; break
        if h2 == "sl":
            runner = 0.0; break
    blended = 0.5 * rr1 + 0.5 * runner
    out = "tp2" if runner == rr2 else "tp1"
    return {"outcome": out, "hypo_r_raw": blended, "mfe_r": mfe, "mae_r": mae,
            "bars_to_resolve": n, "ts_resolved": tp1_bar["ts"]}

def resolve_signal(rec, bars, smc_version, max_horizon_hours, fill_window_bars=8):
    horizon_ms = int(max_horizon_hours * 3600 * 1000)
    fill = replay_fill(rec, bars, smc_version, fill_window_bars)
    if fill is None:
        return {"status": "unfilled", "outcome": "unfilled", "hypo_r_gross": None}
    raced = race_sl_tp(rec, bars, fill["fill_idx_ts"], horizon_ms)
    if raced is None:
        return {"status": "timeout", "outcome": "timeout", "fill_price": fill["fill_price"],
                "ts_filled": fill["ts_filled"], "bars_to_fill": fill["bars_to_fill"],
                "hypo_r_gross": None, "resolved_at_granularity": "1m"}
    return {"status": "resolved", "outcome": raced["outcome"], "fill_price": fill["fill_price"],
            "ts_filled": fill["ts_filled"], "bars_to_fill": fill["bars_to_fill"],
            "hypo_r_gross": raced["hypo_r_raw"], "mfe_r": raced["mfe_r"], "mae_r": raced["mae_r"],
            "bars_to_resolve": raced["bars_to_resolve"], "ts_resolved": raced["ts_resolved"],
            "resolved_at_granularity": "1m"}
