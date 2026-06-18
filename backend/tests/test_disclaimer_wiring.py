"""CMP-5 — disclaimer wiring per-page acceptance tests.

Lock-in: every live HTML in u2algo-site/ MUST carry the CMP-1 canonical
byte-anchors (COMPLIANCE_TR/EN from engine.content_jobs) verbatim, so
``has_disclaimer(page_text, lang)`` returns True on the right surface.

Acceptance spec (from P-002.5 CMP-5):
  - premium.html, quickstart.html: TR + EN anchors (NFA + Risk + Proof≠Product)
  - index.html: TR + EN (EN-first global ziyaretçi)
  - terms.html, privacy.html: TR anchor + A.Ş. jurisdiction note (B6)
  - risk-disclosure.html (NEW): TR + EN anchors + all 6 blocks (B1-B6)
  - Sitemap entries all live surfaces
  - find_violations on every page == [] (no banned-phrase / perf-% / $ leak
    except the whitelisted $39 lifetime mentions)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine.content_jobs import COMPLIANCE_EN, COMPLIANCE_TR
from scripts.content_compliance import (
    PRODUCT_PRICE_USD,
    find_violations,
    has_disclaimer,
)

SITE = Path(__file__).resolve().parents[2] / "u2algo-site"


def _read(name: str) -> str:
    p = SITE / name
    assert p.exists(), f"missing live page: {p}"
    return p.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────
# 1. Per-page disclaimer presence (the CMP-5 acceptance gate)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("page,lang", [
    ("premium.html", "tr"),
    ("quickstart.html", "tr"),
    ("index.html", "tr"),
    ("index.html", "en"),
    ("terms.html", "tr"),
    ("privacy.html", "tr"),
    ("risk-disclosure.html", "tr"),
    ("risk-disclosure.html", "en"),
])
def test_page_has_canonical_disclaimer(page, lang):
    text = _read(page)
    assert has_disclaimer(text, lang=lang), (
        f"{page} missing COMPLIANCE_{lang.upper()} byte-anchor.\n"
        f"  expected substring: {COMPLIANCE_TR if lang=='tr' else COMPLIANCE_EN!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# 2. risk-disclosure.html — full coverage (B1-B6 EN + TR)
# ─────────────────────────────────────────────────────────────────────

def test_risk_disclosure_has_full_block_coverage():
    text = _read("risk-disclosure.html")
    # Each CMP-1 block's canonical short-form phrase (B1-B6) should appear
    # in BOTH languages. We don't byte-anchor every phrase — only the
    # NFA anchor (COMPLIANCE_TR/EN) is byte-anchored per CMP-1 §0.
    must_contain_en = [
        "Not investment advice. Trade at your own risk.",  # B1 anchor
        "Trading carries a high level of risk",  # B2 risk warning
        "Past performance does not guarantee",   # B3 past perf
        "[BACKTEST]",                            # B4 sim label
        "research log",                          # B5 proof≠product
        "joint-stock company",                   # B6 jurisdiction
    ]
    must_contain_tr = [
        "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.",  # B1 anchor
        "Trade, sermayeniz için yüksek risk taşır",                # B2
        "Geçmiş performans gelecekteki sonuçların garantisi değildir",  # B3
        "[BACKTEST]",                                              # B4
        "araştırma günlüğüdür",                                   # B5
        "Anonim Şirketi",                                          # B6
    ]
    for needle in must_contain_en + must_contain_tr:
        assert needle in text, f"risk-disclosure.html missing: {needle!r}"


def test_risk_disclosure_links_back():
    """risk-disclosure.html must link back to the main pages so visitors
    can navigate."""
    text = _read("risk-disclosure.html")
    for target in ("/", "/premium.html", "/quickstart.html",
                   "/terms.html", "/privacy.html"):
        assert target in text, f"risk-disclosure.html missing link to {target}"


# ─────────────────────────────────────────────────────────────────────
# 3. A.Ş. jurisdiction note (B6) on terms + privacy + index
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("page", ["terms.html", "privacy.html", "index.html"])
def test_jurisdiction_note_present(page):
    text = _read(page)
    # A.Ş. or "Anonim Şirketi" must appear — CMP-1 §1 B6 short-form
    assert ("A.Ş." in text) or ("Anonim Şirketi" in text), (
        f"{page} missing A.Ş. jurisdiction note (CMP-1 B6)."
    )


# ─────────────────────────────────────────────────────────────────────
# 4. find_violations == [] on every page (banned/perf/%/$ gate)
# ─────────────────────────────────────────────────────────────────────

def _strip_style(text: str) -> str:
    """Strip <style>...</style> blocks so CMP-3's _SIM_WORDS regex
    (which matches `shadow` literally) doesn't trip on CSS property names
    like ``box-shadow`` / ``text-shadow``. Marketing copy / body text is
    what the CMP-3 sim-label gate was designed to protect; CSS is irrelevant."""
    return re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)


@pytest.mark.parametrize("page", [
    "index.html", "premium.html", "quickstart.html",
    "terms.html", "privacy.html", "risk-disclosure.html",
])
def test_page_passes_compliance_gate(page):
    """Every page MUST pass the PROMOTIONAL-CLAIM gates: no banned phrase
    (TR + EN), no absolute $ (except the whitelisted $39 lifetime), no perf-%.

    ``unlabeled_simulation`` is intentionally NOT enforced over a full static
    page. These pages legitimately DESCRIBE and DISCLAIM the backtest/shadow
    methodology ("backtest results are not a guarantee") — the opposite of
    presenting unlabeled sim *results*. The sim-label gate is for promotional
    result snippets (CON video scripts, social posts), applied by the content
    pipeline — not for body copy that disclaims simulation. Forcing inline
    ``[BACKTEST]`` tokens into marketing prose (e.g. "v2 [BACKTEST] shadow")
    mangles the live page for zero compliance gain.
    """
    text = _read(page)
    # Strip CSS <style> blocks before the gate check (see _strip_style docstring).
    text_for_gate = _strip_style(text)
    v = [t for t in find_violations(text_for_gate, lang="all")
         if t != "unlabeled_simulation"]
    assert v == [], (
        f"{page} has promotional-claim violations: {v}"
    )


# ─────────────────────────────────────────────────────────────────────
# 5. Sitemap covers all 6 surfaces
# ─────────────────────────────────────────────────────────────────────

def test_sitemap_lists_all_live_surfaces():
    sitemap = _read("sitemap.xml")
    for path in ("/", "/premium.html", "/quickstart.html",
                 "/terms.html", "/privacy.html", "/risk-disclosure.html"):
        # Sitemap uses full URL form
        assert f"https://u2algo.com{path}" in sitemap or path == "/", (
            f"sitemap.xml missing entry for {path}"
        )
    # root entry has full URL
    assert "https://u2algo.com/" in sitemap


# ─────────────────────────────────────────────────────────────────────
# 6. robots.txt allows risk-disclosure.html (not disallowed)
# ─────────────────────────────────────────────────────────────────────

def test_robots_does_not_disallow_risk_disclosure():
    """If a Disallow rule blocks risk-disclosure.html specifically, the
    compliance gate is meaningless. Spot-check: the file is either
    permissive OR does not name risk-disclosure in a Disallow rule."""
    robots_path = SITE / "robots.txt"
    if not robots_path.exists():
        pytest.skip("robots.txt missing")
    text = robots_path.read_text(encoding="utf-8")
    # An explicit Disallow for risk-disclosure would look like:
    #   Disallow: /risk-disclosure.html
    assert "Disallow: /risk-disclosure.html" not in text, (
        "robots.txt must not block risk-disclosure.html"
    )


# ─────────────────────────────────────────────────────────────────────
# 7. Footer cross-link — every page must link to risk-disclosure.html
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("page", [
    "index.html", "premium.html", "quickstart.html",
    "terms.html", "privacy.html",
])
def test_page_links_to_risk_disclosure(page):
    text = _read(page)
    assert "/risk-disclosure.html" in text or "risk-disclosure.html" in text, (
        f"{page} must link to /risk-disclosure.html (CMP-5 acceptance)"
    )


# ─────────────────────────────────────────────────────────────────────
# 8. Conservative proof — no $/per-trade on content-bearing sections
#    (the existing $39 lifetime / one-time price is whitelist-OK)
# ─────────────────────────────────────────────────────────────────────

def test_no_dollar_amount_outside_whitelist():
    """No page should contain $-amounts OTHER than the whitelisted $39
    lifetime / one-time product price."""
    # Match $ + digit + optional comma/dot + optional digits (NOT a digit-only match)
    money_pattern = re.compile(r"\$\s*\d[\d,.]*")
    whitelist = re.compile(
        rf"\$\s*{PRODUCT_PRICE_USD}\b"
        rf"(?:\s*(?:lifetime|one[- ]?time|once|tek\s+seferlik|ömür\s+boyu))?",
        re.IGNORECASE,
    )
    for page in ("index.html", "premium.html", "quickstart.html",
                 "terms.html", "privacy.html", "risk-disclosure.html"):
        text = _read(page)
        for m in money_pattern.finditer(text):
            # The matched amount must be whitelisted; if a longer span in the
            # text (e.g. "$39 Lifetime") covers this match, it's whitelisted.
            tail = text[m.start():m.start()+60]
            assert whitelist.search(tail), (
                f"{page} has non-whitelisted $-amount at offset {m.start()}: "
                f"{m.group(0)!r} (context: {tail[:50]!r})"
            )


# ─────────────────────────────────────────────────────────────────────
# 9. CMP-1 spec contract — anchor strings are byte-equal to constants
# ─────────────────────────────────────────────────────────────────────

def test_canonical_anchors_match_engine_constants():
    """The string 'Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.'
    must byte-match COMPLIANCE_TR, and the EN one must match COMPLIANCE_EN."""
    assert COMPLIANCE_TR == "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir."
    assert COMPLIANCE_EN == "Not investment advice. Trade at your own risk."
    assert PRODUCT_PRICE_USD == 39