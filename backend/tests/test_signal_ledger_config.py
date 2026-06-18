# backend/tests/test_signal_ledger_config.py
import yaml
from pathlib import Path

def test_signal_ledger_config_defaults_off():
    cfg = yaml.safe_load(Path("configs/config.phase2_1k.yaml").read_text(encoding="utf-8"))
    sl = cfg.get("signal_ledger")
    assert sl is not None, "signal_ledger block missing from LIVE config"
    assert sl["enabled"] is False
    assert sl["max_horizon_hours"] == 48
    assert sl["resolution_tf"] == "1m"
    assert sl["fill_window_bars"] == 8
    assert sl["resolver_cadence_sec"] == 300
    assert sl["max_symbols"] == 25
    assert sl["fetch_fail_alert_pct"] == 20
