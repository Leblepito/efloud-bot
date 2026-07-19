"""scripts.kronos_service — konsensüs + parse + profil testleri."""
from __future__ import annotations

import json

from scripts.kronos_service import (
    PROFILE_LAYERS,
    _BAND_RE,
    _DIRECTION_RE,
    atomic_write_json,
    consensus,
)


def test_consensus_majority():
    runs = [
        {"direction": "UP", "band": "NARROW"},
        {"direction": "UP", "band": "MODERATE"},
        {"direction": "DOWN", "band": "NARROW"},
    ]
    c = consensus(runs)
    assert c["confirmed"] is True
    assert c["direction"] == "UP"
    assert c["band"] == "NARROW"
    assert c["votes"] == {"UP": 2, "DOWN": 1}


def test_consensus_no_majority():
    runs = [
        {"direction": "UP", "band": "WIDE"},
        {"direction": "DOWN", "band": "WIDE"},
    ]
    c = consensus(runs)
    assert c["confirmed"] is False
    assert c["direction"] is None


def test_consensus_empty():
    c = consensus([])
    assert c == {"direction": None, "band": None, "confirmed": False, "runs": 0}


def test_predict_output_parse():
    """_predict.py format_output satırları regex'lerle parse edilebilmeli."""
    sample = (
        "# Kronos Prediction: BTC-USD\n\n"
        "**Last close:** $67,432.10 (2026-07-19 00:00)\n"
        "**Predicted close after 14 x 1d candles:** $69,001.55\n"
        "**Direction:** UP (+2.33%)\n"
        "**Confidence band:** NARROW (signal worth investigating)\n"
    )
    assert _DIRECTION_RE.search(sample).group(1) == "UP"
    assert _BAND_RE.search(sample).group(1) == "NARROW"


def test_profiles_match_playbook():
    """PLAYBOOK §2 komut haritası — yfinance-geçersiz interval OLMAMALI."""
    valid = {"1m", "5m", "15m", "30m", "60m", "1h", "1d", "5d", "1wk", "1mo"}
    for profile, layers in PROFILE_LAYERS.items():
        assert [l[0] for l in layers] == ["htf", "mtf", "ltf"], profile
        for _, _, interval, _ in layers:
            assert interval in valid, (profile, interval)


def test_atomic_write(tmp_path):
    p = tmp_path / "out" / "kronos.json"
    atomic_write_json(p, {"a": 1, "sym": "BTC"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "sym": "BTC"}
    assert not p.with_suffix(".json.tmp").exists()
