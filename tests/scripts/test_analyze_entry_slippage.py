from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "analyze_entry_slippage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("analyze_entry_slippage", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def sample_trades():
    return [
        # BTC LONG, +0.5% adverse fill, latency 3s
        {"symbol": "BTC/USDT", "direction": "LONG", "signal_entry_price": 100.0,
         "actual_fill_price": 100.5, "zone_mid": 100.25, "latency_ms": 3000.0,
         "entry_timestamp": "2026-06-08T10:00:00+00:00"},
        # BTC LONG, +0.1% adverse fill, latency 1s
        {"symbol": "BTC/USDT", "direction": "LONG", "signal_entry_price": 100.0,
         "actual_fill_price": 100.1, "zone_mid": 100.0, "latency_ms": 1000.0,
         "entry_timestamp": "2026-06-08T11:00:00+00:00"},
        # ETH SHORT, sold 0.5 below signal -> +1.0% adverse, latency 2s
        {"symbol": "ETH/USDT", "direction": "SHORT", "signal_entry_price": 50.0,
         "actual_fill_price": 49.5, "zone_mid": 50.0, "latency_ms": 2000.0,
         "entry_timestamp": "2026-06-08T12:00:00+00:00"},
        # No telemetry (signal/fill zero) -> excluded from telemetry stats
        {"symbol": "DOGE/USDT", "direction": "LONG", "signal_entry_price": 0.0,
         "actual_fill_price": 0.0, "zone_mid": 0.0, "latency_ms": 0.0,
         "entry_timestamp": "2026-06-08T13:00:00+00:00"},
    ]


def test_compute_overall_stats(sample_trades):
    mod = _load_module()
    out = mod.compute_slippage_stats(sample_trades)

    assert out["n_total"] == 4
    assert out["n_with_telemetry"] == 3

    o = out["overall"]
    assert o["n"] == 3
    # signed slippage (direction-aware): LONG +0.5, +0.1 ; SHORT +1.0 -> mean ~0.5333
    assert o["mean_slippage_pct"] == pytest.approx(0.5333, abs=1e-3)
    assert o["median_abs_slippage_pct"] == pytest.approx(0.5, abs=1e-6)
    assert o["p90_abs_slippage_pct"] == pytest.approx(0.9, abs=1e-3)
    assert o["adverse_rate"] == pytest.approx(1.0, abs=1e-6)  # all three adverse
    assert o["mean_latency_ms"] == pytest.approx(2000.0, abs=1e-6)
    assert o["mean_zone_gap_pct"] == pytest.approx(0.4498, abs=1e-3)


def test_short_slippage_is_direction_signed(sample_trades):
    mod = _load_module()
    out = mod.compute_slippage_stats(sample_trades)
    eth = out["by_symbol"]["ETH/USDT"]
    assert eth["n"] == 1
    # SHORT filled BELOW signal is adverse -> positive
    assert eth["mean_slippage_pct"] == pytest.approx(1.0, abs=1e-6)
    assert eth["adverse_rate"] == pytest.approx(1.0, abs=1e-6)


def test_favorable_fill_is_negative():
    mod = _load_module()
    # LONG filled BELOW signal = favorable -> negative slippage, not adverse
    trades = [{"symbol": "X/USDT", "direction": "LONG", "signal_entry_price": 100.0,
               "actual_fill_price": 99.0, "zone_mid": 100.0, "latency_ms": 0.0}]
    out = mod.compute_slippage_stats(trades)
    assert out["overall"]["mean_slippage_pct"] == pytest.approx(-1.0, abs=1e-6)
    assert out["overall"]["adverse_rate"] == pytest.approx(0.0, abs=1e-6)
    # latency all-zero -> None (not counted)
    assert out["overall"]["mean_latency_ms"] is None


def test_empty_input_is_safe():
    mod = _load_module()
    out = mod.compute_slippage_stats([])
    assert out["n_total"] == 0
    assert out["n_with_telemetry"] == 0
    assert out["overall"]["n"] == 0


def test_cli_smoke(tmp_path, sample_trades):
    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text("\n".join(json.dumps(t) for t in sample_trades), encoding="utf-8")
    out_json = tmp_path / "out.json"
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--journal", str(journal), "--json", str(out_json)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["n_with_telemetry"] == 3
    assert "BTC/USDT" in data["by_symbol"]
