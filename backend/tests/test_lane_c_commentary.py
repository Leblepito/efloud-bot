"""Multi-timeframe commentary generator tests — PR #13 (Phase 4a).

Top-down SMC narration over the doctrine chain (1D macro → 4H trend → 1H
structure → 15M trigger → invalidation → disclaimer). Guardrails: no promise /
future-certainty language ("kesinlikle", "guaranteed", "will"...), banned-phrase
+ disclaimer asserts, ratio/risk metrics only (decision #5). Golden-file render.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.content_jobs import COMPLIANCE_TR
from scripts.lane_c_commentary import (
    SCHEMA_PATH,
    build_commentary,
    commentary_violations,
    render_commentary,
)

SETUP = {
    "symbol": "BTC/USDT",
    "direction": "LONG",
    "timeframes": {
        "1d": {"label": "makro", "note": "Haftalık OB üzerinde, makro yükseliş"},
        "4h": {"label": "trend/bias", "note": "HTF trend korunuyor, BoS yukarı"},
        "1h": {"label": "yapı", "note": "MTF CHoCH yukarı"},
        "15m": {"label": "tetik", "note": "FVG retest girişi"},
    },
    "entry": 50000.0, "sl": 49000.0, "tp1": 52000.0, "tp2": 53000.0,
    "invalidation": "15m kapanış 48800 altı", "confluence": 85,
}

GOLDEN = (
    "BTC/USDT · LONG — Çok zaman dilimli görünüm\n"
    "\n"
    "1D (makro): Haftalık OB üzerinde, makro yükseliş\n"
    "4H (trend/bias): HTF trend korunuyor, BoS yukarı\n"
    "1H (yapı): MTF CHoCH yukarı\n"
    "15M (tetik): FVG retest girişi\n"
    "\n"
    "Risk ~2.0% · R:R 1:2.0 (TP1) · 1:3.0 (TP2)\n"
    "Geçersizleşme: 15m kapanış 48800 altı\n"
    "\n"
    "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir."
)


def test_golden_render():
    assert render_commentary(SETUP) == GOLDEN


def test_sections_are_top_down_order():
    c = build_commentary(SETUP)
    assert [s["timeframe"] for s in c["sections"]] == ["1D", "4H", "1H", "15M"]


def test_commentary_carries_disclaimer():
    c = build_commentary(SETUP)
    assert c["disclaimer"] == COMPLIANCE_TR
    assert COMPLIANCE_TR in c["script"]


def test_ratio_risk_only_and_compliance_clean():
    script = render_commentary(SETUP)
    assert "R:R" in script and "Risk ~" in script
    assert commentary_violations(script) == []


def test_promise_language_is_flagged():
    bad = dict(SETUP, timeframes={
        "1d": {"label": "makro", "note": "Fiyat kesinlikle yükselecek, garanti"},
    })
    v = commentary_violations(render_commentary(bad))
    assert any(x.startswith("promise:") for x in v)


def test_banned_phrase_in_note_is_flagged():
    bad = dict(SETUP, timeframes={
        "15m": {"label": "tetik", "note": "Garantili getiri burada"},
    })
    assert commentary_violations(render_commentary(bad))


def test_schema_file_exists_and_structured_output_validates():
    assert SCHEMA_PATH.exists(), SCHEMA_PATH
    schema = json.loads(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    import jsonschema
    jsonschema.validate(build_commentary(SETUP), schema)  # must not raise


def test_missing_tp2_omits_tp2_metric():
    setup = dict(SETUP)
    setup = {k: v for k, v in SETUP.items() if k != "tp2"}
    script = render_commentary(setup)
    assert "(TP1)" in script
    assert "(TP2)" not in script
