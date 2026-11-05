"""Pine lab parity harness tests (spec §7.2) — synthetic data only, no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import pine_lab_parity as plp  # noqa: E402


def _df_from_closes(closes, wick=0.2, start="2026-01-01"):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    highs = np.maximum(opens, closes) + wick
    lows = np.minimum(opens, closes) - wick
    idx = pd.date_range(start, periods=len(closes), freq="15min")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": 1.0}, index=idx)


def _zigzag(points, steps=6):
    out = []
    for a, b in zip(points[:-1], points[1:]):
        out += list(np.linspace(a, b, steps, endpoint=False))
    out.append(points[-1])
    return out


def _trend_df(n_cycles=20):
    pts = [100, 110, 104, 108, 98, 103, 92, 97, 88, 99, 94, 112, 105, 120, 113, 128]
    closes = []
    base = 0.0
    for _ in range(n_cycles):
        closes += [p + base for p in _zigzag(pts)]
        base += 5.0
    return _df_from_closes(closes)


def _lab_config():
    cfg = plp.load_config(ROOT / "configs" / "config.phase2_1k.yaml")
    lux = cfg["smc_v2"]["luxalgo"]
    lux.update({"swing_length": 4, "internal_length": 2, "eq_length": 2, "atr_length": 10,
                "require_premium_discount": False, "min_confluence": 0, "pullback_timeout_bars": 60})
    cfg["risk"]["recency_bars"] = 120
    cfg["smc_v2"]["po3_gate"] = False
    cfg["smc_v2"]["max_entry_dist_atr"] = 0.0
    cfg["smc_v2"]["max_zone_overshoot_atr"] = 999.0
    cfg["safety"]["min_sl_atr"] = 0.5
    return cfg


def test_load_ohlcv_csv_tradingview_and_binance_layouts(tmp_path):
    tv = tmp_path / "tv.csv"
    tv.write_text("time,open,high,low,close,Volume\n1700000000,1,2,0.5,1.5,10\n1700000900,1.5,2.5,1,2,11\n")
    df = plp.load_ohlcv_csv(tv)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.tz is None and df.index[0] == pd.Timestamp("2023-11-14 22:13:20")
    bn = tmp_path / "bn.csv"
    bn.write_text("timestamp,open,high,low,close,volume\n1700000000000,1,2,0.5,1.5,10\n")
    assert plp.load_ohlcv_csv(bn).index[0] == df.index[0]


def test_resample_htf_drops_incomplete_last_bin_and_checks_alignment():
    df = _df_from_closes(list(range(100, 100 + 8 * 48 + 7)))        # 8 full 12h bins + 7 bars
    htf = plp.resample_htf(df, "12h")
    assert len(htf) == 8                                            # the 9th (partial) 12h bin is dropped
    assert htf.index[0] == pd.Timestamp("2026-01-01 00:00")
    assert htf["high"].iloc[0] == df["high"].iloc[:48].max()
    bad = df.copy()
    bad.index = bad.index + pd.Timedelta(minutes=7)
    with pytest.raises(ValueError):
        plp.resample_htf(bad, "12h")


def test_replay_emits_and_confirms_on_trending_zigzag():
    df = _trend_df()
    rows, stats = plp.replay(df, _lab_config(), window=200, htf_bias_override="BULL")
    assert stats["bars"] == len(df) - 199
    assert stats["emitted"] >= 1
    assert all(r["direction"] == "LONG" for r in rows)
    assert all(set(r) == set(plp.ROW_FIELDS) for r in rows)
    confirmed = [r for r in rows if r["drop_reason"] == ""]
    assert confirmed, "expected at least one confirmed setup with SL/TP"
    for r in confirmed:
        assert r["sl"] < r["entry"] < r["tp1"]
        assert r["atr_source"] == "WILDER14"
        assert r["tp1_source"] != ""
        assert r["confirmed_ts"] >= r["trigger_bar_ts"]


def test_replay_reads_recency_from_risk_block_like_live_orchestrator():
    cfg = plp.load_config(ROOT / "configs" / "config.phase2_1k.yaml")
    assert cfg["risk"]["recency_bars"] == 168 and "recency_bars" not in cfg.get("smc_v2", {})
    assert plp.recency_bars(cfg) == 168
    assert plp.recency_bars({"smc_v2": {"recency_bars": 99}}) == 40


def test_guard_rejected_flag_marks_floor_widened_stops(tmp_path):
    cfg = _lab_config()
    cfg["safety"]["min_sl_atr"] = 2.0
    df = _trend_df(4)
    orch = plp.LabOrchestrator(cfg, plp.new_store(cfg, tmp_path), tmp_path)
    from engine.smc_v2.setup_state import SetupCandidate
    from engine.smc_v2.zones import ZoneSpec
    flags = set()
    rng = np.random.default_rng(1)
    for _ in range(300):
        entry = float(rng.uniform(0.05, 120000))
        d = df * (entry / 100.0)
        atr = plp.wilder_atr(d, period=14)
        zone = ZoneSpec(low=entry - 0.2 * atr, high=entry, source="OB")
        cand = SetupCandidate(symbol="LAB/USDT", direction="LONG", trigger_bar_ts=1, trigger_price=entry,
                              htf_bias="BULL", target_zone=zone, htf_swing_anchor=zone.low, bars_waited=0,
                              state="CONFIRMED", confluence_score=1,
                              reasons=["LUX swing BOS BULL", "", "confluence=SWING_OB"])
        orch._place_v2_entry_order(cand, current_price=entry, entry_price=entry, df_entry=d)
        rec = orch.records[-1]
        if rec["drop_reason"] == "":
            assert rec["atr_source"] == "WILDER14"
            flags.add(rec["python_guard_rejected"])
    assert flags == {True, False}, "the B2 float flag must fire for some floor-widened stops and not others"


def test_write_rows_roundtrip(tmp_path):
    rows = [{k: "" for k in plp.ROW_FIELDS}]
    rows[0].update(symbol="LAB/USDT", direction="LONG", trigger_bar_ts=5, entry=1.0, sl=0.9, tp1=1.2)
    out = tmp_path / "py.csv"
    plp.write_rows(rows, out)
    back = plp.read_rows(out)
    assert back[0]["trigger_bar_ts"] == 5 and back[0]["entry"] == 1.0 and back[0]["drop_reason"] == ""
