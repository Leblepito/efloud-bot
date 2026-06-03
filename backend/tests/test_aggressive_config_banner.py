"""F3.2: config.aggressive_v1.yaml must carry a DO-NOT-DEPLOY banner.

aggressive_v1 is margin_mode CROSSED + hedge_mode true — it contradicts the live
ISOLATED + one-way posture (PR A). Pointing EFLOUD_CONFIG_PATH at it would
silently revert the safety posture (the FIL auto-flip incident class). The banner
documents this; the test guards against its removal and confirms the file still
parses (the banner is comments only).
"""
from pathlib import Path

import yaml

_CFG = Path(__file__).resolve().parents[2] / "configs" / "config.aggressive_v1.yaml"


def test_banner_present():
    text = _CFG.read_text(encoding="utf-8")
    assert "DO-NOT-DEPLOY" in text
    assert "ISOLATED + one-way" in text  # the contradiction is spelled out


def test_still_parses_and_is_the_dangerous_config():
    cfg = yaml.safe_load(_CFG.read_text(encoding="utf-8"))
    # The banner is comments → the YAML body is unchanged and still the (archived)
    # CROSSED + hedge config the banner warns about.
    assert cfg["exchange"]["margin_mode"] == "CROSSED"
    assert cfg["exchange"]["hedge_mode"] is True
