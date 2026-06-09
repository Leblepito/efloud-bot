"""Content-pipeline compliance checker tests — shared by Lane C (#12) and the
multi-TF commentary generator (#13).

Enforces the growth-OS guardrails on generated marketing/commentary copy:
- the REAL Turkish banned promise-phrases (GO_TO_MARKET_2026-05-28.md:16-22, C1),
- no absolute-$ profit/loss amounts (decision #5 — ratio/risk metrics only),
- performance-% claims (win-rate / return) banned, but risk-% and R:R allowed.
The mandated disclaimer reuses engine COMPLIANCE_TR/EN (no duplication).
"""
from __future__ import annotations

from engine.content_jobs import COMPLIANCE_EN, COMPLIANCE_TR
from scripts.content_compliance import (
    BANNED_TR_PHRASES,
    find_violations,
    has_disclaimer,
)


def test_banned_list_is_the_real_six():
    assert len(BANNED_TR_PHRASES) == 6
    assert "Garantili getiri" in BANNED_TR_PHRASES
    assert "Fonumuza para yatır" in BANNED_TR_PHRASES


def test_flags_banned_promise_phrase():
    v = find_violations("Garantili getiri sağlıyoruz!")
    assert any("Garantili getiri" in x for x in v)


def test_banned_match_is_case_insensitive_and_comma_tolerant():
    assert find_violations("SİNYAL AL KAZAN")      # upper, no comma
    assert find_violations("sinyal al, kazan")     # original comma form


def test_clean_setup_copy_has_no_violations():
    txt = f"15m FVG retest, bullish OB confluence. R:R 1:2. {COMPLIANCE_TR}"
    assert find_violations(txt) == []


def test_flags_absolute_dollar_amount():
    assert find_violations("Bugün 250$ kâr")       # $ amount
    assert find_violations("$1,000 profit locked")  # $ amount


def test_allows_risk_percent_and_rr_ratio():
    # Ratio/risk metrics are explicitly allowed (decision #5).
    assert find_violations("Stop 2% risk, hedef R:R 1:3") == []


def test_flags_performance_percent_claim():
    assert find_violations("73.2% win rate")        # performance promise
    assert find_violations("%80 kazanç oranı")      # TR performance promise


def test_disclaimer_detection_tr_and_en():
    assert has_disclaimer(f"setup... {COMPLIANCE_TR}", lang="tr")
    assert has_disclaimer(f"setup... {COMPLIANCE_EN}", lang="en")
    assert not has_disclaimer("no disclaimer present", lang="tr")
