"""T-20261105-05: Telegram LuxAlgo zone alerts are switched on for the live mid bot.

Read-only feature (#275): the engine logs `[lux] near` when price is within
`smc_v2.luxalgo.near_alert_atr` ATR of a pending zone, and the alerter turns
`[lux] near|touch|confirmed` + `[v2 reject]` lines into Telegram messages when
EFLOUD_ALERTER_LUX_ALERTS is on. Neither touches the order path.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _yaml(rel: str) -> dict:
    with open(ROOT / rel, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_mid_config_sets_near_alert_threshold():
    lux = _yaml("configs/config.phase2_1k.yaml")["smc_v2"]["luxalgo"]
    assert lux["enabled"] is True
    assert float(lux["near_alert_atr"]) == 1.0


def test_alerter_service_enables_lux_alerts():
    alerter = _yaml("docker-compose.prod.yml")["services"]["alerter"]
    assert "EFLOUD_ALERTER_LUX_ALERTS=1" in alerter["environment"]


def test_lux_alerts_only_change_alerter_and_luxalgo_block():
    """Guard: the flag lives on the alerter service only, not on trading bots."""
    services = _yaml("docker-compose.prod.yml")["services"]
    for name, svc in services.items():
        if name == "alerter":
            continue
        env = svc.get("environment") or []
        assert not any(str(e).startswith("EFLOUD_ALERTER_LUX_ALERTS") for e in env), name
