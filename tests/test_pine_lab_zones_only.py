"""Zones-only publish build (spec docs/superpowers/specs/2026-11-19-indicator-zones-only-design.md)."""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IND = (ROOT / "pine" / "efloud_lab.pine").read_text(encoding="utf-8")
STRAT = ROOT / "pine" / "efloud_lab_strategy.pine"
# LF-normalised sha256 (the operator checkout holds the same content with CRLF: 56bf544a...3c22)
STRAT_SHA = "df9fe691bf401325db6748b420c437a3ba786f53f86da76a7f38229ee530f5ed"


def test_signal_layer_removed():
    for token in ("sigLines", "sigLabels", "zoneBoxes", '"LONG "', '"SHORT "',
                  '"Entry/SL/TP lines"', '"Pending candidate zones"', '"Kept signal drawings"'):
        assert token not in IND, token


def test_dashboard_has_no_signal_engine_rows():
    for row in ('"Pending W/Z/R"', '"Po3"', '"Drops (last 20)"'):
        assert row not in IND, row
    for row in ('"Range EQ"', '"OTE"', '"Zones s/i·BB·MB·FVG·Liq"'):
        assert row in IND, row


def test_at_most_one_alert_call_site():
    assert len(re.findall(r"\balert\(", IND)) <= 1


def test_strategy_artefact_unchanged():
    data = STRAT.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == STRAT_SHA


def test_zone_alert_inputs_and_single_alert():
    assert '"Alert: zone entry"' in IND and '"Alert: liquidity sweep"' in IND
    assert len(re.findall(r"\balert\(", IND)) == 1
    assert "alert.freq_once_per_bar_close" in IND


def test_zone_alert_dedup_is_one_capped_map():
    assert "map.new<string, int>()" in IND
    assert "map.size(alertSeen) >= 500" in IND
    assert "barstate.isrealtime" in IND


def test_alert_text_is_informational():
    assert "informational, not a trade signal" in IND
