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
    # no hit within horizon -> carry the accumulated excursions so the timeout
    # mark-to-market panel is not degenerate (final-review fix)
    return {"outcome": None, "mfe_r": mfe, "mae_r": mae}

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
    if raced.get("outcome") is None:
        return {"status": "timeout", "outcome": "timeout", "fill_price": fill["fill_price"],
                "ts_filled": fill["ts_filled"], "bars_to_fill": fill["bars_to_fill"],
                "mfe_r": raced.get("mfe_r"), "mae_r": raced.get("mae_r"),
                "hypo_r_gross": None, "resolved_at_granularity": "1m"}
    return {"status": "resolved", "outcome": raced["outcome"], "fill_price": fill["fill_price"],
            "ts_filled": fill["ts_filled"], "bars_to_fill": fill["bars_to_fill"],
            "hypo_r_gross": raced["hypo_r_raw"], "mfe_r": raced["mfe_r"], "mae_r": raced["mae_r"],
            "bars_to_resolve": raced["bars_to_resolve"], "ts_resolved": raced["ts_resolved"],
            "resolved_at_granularity": "1m"}

# ---------------------------------------------------------------------------
# Task 4 — Resolver orchestration: fetch abstraction, cost netting, heartbeat
# ---------------------------------------------------------------------------
import json, time, logging
from pathlib import Path
from engine.edge_costs import net_r

log = logging.getLogger("efloud.signal_resolver")

_TF_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000,
          "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000}


def _tf_to_ms(tf: str) -> int:
    return _TF_MS.get(tf, 60_000)


def resolve_open_signals(ledger, fetcher, cfg):
    tf = cfg["resolution_tf"]; horizon_h = cfg["max_horizon_hours"]
    horizon_ms = int(horizon_h * 3600 * 1000)
    counters = {"scanned":0,"newly_filled":0,"resolved":0,"timed_out":0,
                "still_open":0,"fetch_failed":0,"unfilled":0,"awaiting_fill":0}
    for rec in ledger.open_signals()[: cfg["max_symbols"]]:
        counters["scanned"] += 1
        until = min(int(time.time()*1000), rec.ts_emitted + horizon_ms)
        try:
            bars = fetcher.fetch_bars(rec.symbol, tf, rec.brk_ts, until)
        except Exception as exc:
            log.warning("resolver fetch failed %s: %s", rec.symbol, exc)
            ledger.update_resolution(rec.signal_id, status="unresolved_data")
            counters["fetch_failed"] += 1
            continue
        patch = resolve_signal(rec, bars, cfg["smc_version"], horizon_h, cfg["fill_window_bars"])
        if patch["status"] == "unfilled":
            # Activation item C: only FINALIZE 'unfilled' once the fill window
            # has fully elapsed in wall-clock time. A 300s-cadence pass must not
            # kill young signals before they had a chance to fill (survivorship
            # bias in the sample).
            deadline = rec.ts_emitted + cfg["fill_window_bars"] * _tf_to_ms(tf)
            if int(time.time() * 1000) < deadline:
                counters["awaiting_fill"] += 1
                continue  # not finalized — retried next pass
        if patch.get("hypo_r_gross") is not None:
            ts_res = patch.get("ts_resolved", until)
            hold_h = max((ts_res - rec.ts_emitted) / 3_600_000.0, 0.0)
            funding = fetcher.funding_sum(rec.symbol, rec.ts_emitted, ts_res)
            patch["hypo_r_net"] = net_r(rec.direction, rec.emitted_entry, rec.sl,
                                        patch["hypo_r_gross"], hold_h, funding)
        ledger.update_resolution(rec.signal_id, **patch)
        st = patch["status"]
        if st == "resolved":
            counters["resolved"] += 1
        elif st == "timeout":
            counters["timed_out"] += 1
        elif st == "unfilled":
            # item C: explicit counter — was mislabeled still_open before
            counters["unfilled"] += 1
        else:
            counters["still_open"] += 1
        if patch.get("ts_filled"):
            counters["newly_filled"] += 1
    _write_heartbeat(cfg, counters)
    _maybe_alert(cfg, counters)
    # threshold echoed so the scheduler wrapper can derive ok (item D)
    return {**counters, "fetch_fail_alert_pct": cfg["fetch_fail_alert_pct"]}

def _write_heartbeat(cfg, counters):
    state_dir = Path(cfg.get("state_dir", "./state"))
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {**counters, "ts_ms": int(time.time()*1000)}
    (state_dir / "signal_resolver_heartbeat.json").write_text(
        json.dumps(payload), encoding="utf-8")

def _maybe_alert(cfg, counters):
    scanned = counters["scanned"] or 1
    fail_pct = 100 * counters["fetch_failed"] / scanned
    if fail_pct >= cfg["fetch_fail_alert_pct"]:
        try:
            from scripts.routines._alert import AlertRouter
            AlertRouter().send("WARNING", "signal_resolver_fetchfail",
                               "signal_resolver fetch-fail",
                               f"{fail_pct:.0f}% >= {cfg['fetch_fail_alert_pct']}% fetch failures this pass")
        except Exception:
            log.warning("resolver fetch-fail %.0f%% (alert router unavailable)", fail_pct)

# ---------------------------------------------------------------------------
# Task 7 — Real OHLCVFetcher adapter + CLI/@register entrypoints
# ---------------------------------------------------------------------------
from scripts.routines.runner import register


class _FetcherAdapter:
    """Wraps the real OHLCVFetcher (DataFrame API) into the resolver-facing
    fetch_bars(list[dict]) / funding_sum(float) interface.

    REAL fetcher notes (data/fetcher.py):
      fetch_ohlcv_range → returns FetchResult(df, gaps); df has DatetimeIndex
        named "timestamp", columns: open, high, low, close, volume.
      fetch_funding_rates → returns DataFrame with DatetimeIndex named "ts",
        column: funding_rate.
    """
    def __init__(self, fetcher):
        self._f = fetcher

    def fetch_bars(self, symbol, tf, since_ms, until_ms):
        result = self._f.fetch_ohlcv_range(symbol, tf, since_ms, until_ms)
        return _bars_from_df(result.df)

    def funding_sum(self, symbol, since_ms, until_ms):
        df = self._f.fetch_funding_rates(symbol, since_ms, until_ms)
        return _sum_funding(df)


def _bars_from_df(df):
    """DatetimeIndex DataFrame -> [{ts(ms),open,high,low,close}].
    Index: timestamp (pd.DatetimeIndex). Columns: open, high, low, close, volume.
    """
    import pandas as pd
    if df is None or len(df) == 0:
        return []
    out = []
    for idx, row in df.iterrows():
        ts = int(pd.Timestamp(idx).value // 1_000_000) if not isinstance(idx, (int, float)) else int(idx)
        out.append({"ts": ts, "open": float(row["open"]), "high": float(row["high"]),
                    "low": float(row["low"]), "close": float(row["close"])})
    return out


def _sum_funding(df):
    """Sum funding_rate fraction over the window.
    Real column name confirmed: 'funding_rate' (data/fetcher.py line 111).
    Fallback probes handle alternative naming for resilience.
    """
    if df is None or len(df) == 0:
        return 0.0
    for col in ("funding_rate", "fundingRate", "rate"):
        if col in getattr(df, "columns", []):
            return float(df[col].astype(float).sum())
    return 0.0


@register("signal_resolver")
def _routine_run(client=None, alert=None, cfg=None):
    """Scheduler-facing wrapper. ok derived from main()'s counters
    (activation item D) instead of hardcoding ok=True. Breaches stay empty:
    _maybe_alert already routes the fetch-fail alert (no double alerting)."""
    from scripts.routines._base import RoutineResult
    result = main()
    ok = True
    if isinstance(result, dict) and "scanned" in result:
        scanned = result["scanned"] or 1
        fail_pct = 100.0 * result.get("fetch_failed", 0) / scanned
        ok = fail_pct < result.get("fetch_fail_alert_pct", 20)
    return RoutineResult(
        name="signal_resolver",
        ok=ok,
        breaches=[],
        report_path=None,
    )


def main(cfg_path="configs/config.phase2_1k.yaml"):
    import yaml
    from pathlib import Path
    from data.fetcher import OHLCVFetcher
    from engine.signal_ledger import SignalLedger
    cfg_all = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    cfg = dict(cfg_all["signal_ledger"])
    cfg["state_dir"] = cfg_all.get("operation", {}).get("state_dir", "./state")
    cfg["smc_version"] = cfg_all.get("engine", {}).get("smc_version", "v1")
    from engine.signal_ledger import ledger_enabled
    if not ledger_enabled(cfg):
        return {"skipped": "signal_ledger disabled (config/env)"}
    ledger = SignalLedger(Path(cfg["state_dir"]) / "signal_ledger.jsonl")
    fetcher = _FetcherAdapter(OHLCVFetcher())
    return resolve_open_signals(ledger, fetcher, cfg)


if __name__ == "__main__":
    print(main())
