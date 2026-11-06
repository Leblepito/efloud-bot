"""T-20261107-03: TP-placement-failure Telegram alerts are on for the alerter.

The flag only gates an alerter log rule (ops/alerter/rules.py
TpPlacementFailedRule); it must live on the alerter service, never on a
trading bot service.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FLAG = "EFLOUD_ALERTER_TP_ALERTS"


def _services() -> dict:
    with open(ROOT / "docker-compose.prod.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)["services"]


def test_alerter_service_enables_tp_alerts():
    assert f"{FLAG}=1" in _services()["alerter"]["environment"]


def test_tp_alert_flag_only_on_alerter():
    for name, svc in _services().items():
        if name == "alerter":
            continue
        env = svc.get("environment") or []
        assert not any(str(e).startswith(FLAG) for e in env), name
