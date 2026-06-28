"""CMP-3 — EN compliance + PRICE_WHITELIST + unlabeled_simulation regression.

Sits next to ``test_content_compliance.py`` (TR + money/pct baseline).
Tests are written before the implementation is updated (TDD red).
"""
from __future__ import annotations

import pytest

from scripts.content_compliance import (
    BANNED_EN_PHRASES,
    find_violations,
    has_disclaimer,
)


# --- 1) EN banned phrases: list shape + per-phrase regression -----------------

EXPECTED_EN_PHRASES = {
    "guaranteed profit",
    "guaranteed returns",
    "risk-free",
    "risk free",
    "no loss",
    "no-loss",
    "can't lose",
    "cannot lose",
    "double your money",
    "passive income machine",
    "get rich",
    "get-rich-quick",
    "signal and earn",
    "guaranteed win",
}


def test_en_banned_list_is_complete_and_well_formed():
    assert len(BANNED_EN_PHRASES) >= 12
    assert set(BANNED_EN_PHRASES) >= EXPECTED_EN_PHRASES
    # lowercase, no commas inside phrases
    for p in BANNED_EN_PHRASES:
        assert p == p.lower(), f"EN banned phrase must be lowercase: {p!r}"
        assert "," not in p, f"EN banned phrase must not contain comma: {p!r}"


@pytest.mark.parametrize("phrase", sorted(EXPECTED_EN_PHRASES))
def test_each_en_phrase_is_flagged(phrase):
    text = f"This product offers {phrase} for all subscribers."
    v = find_violations(text, lang="en")
    assert any(tag == f"banned_phrase:{phrase}" for tag in v), (
        f"Expected banned_phrase:{phrase!r} in {v!r}"
    )


def test_en_phrases_still_flagged_under_default_lang():
    # backward-compat: default 'all' must also catch EN leaks
    assert find_violations(
        "Guaranteed profit, risk-free returns, double your money"
    )  # non-empty -> spec's own bug-evidence


# --- 2) TR regression — must still be flagged under any lang -----------------

def test_tr_phrases_still_flagged_under_lang_all():
    assert find_violations("Kesin kazanç sağlıyoruz")  # default all
    assert find_violations("Kesin kazanç sağlıyoruz", lang="tr")


def test_tr_phrases_NOT_flagged_under_lang_en():
    # EN-only scan should ignore TR phrases
    assert find_violations("Kesin kazanç sağlıyoruz", lang="en") == []


def test_en_phrases_NOT_flagged_under_lang_tr():
    assert find_violations("Guaranteed profit for all", lang="tr") == []


# --- 3) PRICE_WHITELIST — $59/mo + $590/mo subscription OK, other $ banned ---

def test_product_price_59_monthly_is_allowed():
    assert find_violations("Indicator subscription - $59/mo access") == []


def test_product_price_590_bot_monthly_is_allowed():
    assert find_violations("Get the bot for $590/mo today") == []


def test_product_price_59_turkish_monthly_is_allowed():
    assert find_violations("İndikatör aboneliği - 59$/ay erişim") == []


def test_arbitrary_dollar_amounts_still_banned():
    assert "absolute_money" in find_violations("$250 trade today")
    assert "absolute_money" in find_violations("balance $1000 in account")
    assert "absolute_money" in find_violations("250 USDT profit")


def test_price_lookalikes_are_not_whitelisted():
    # Only the EXACT $59/$590 prices are whitelisted; lookalikes that merely START
    # with them must still be flagged (regression: a non-anchored prefix leaked
    # "$39,000" / "$39.99" through the money gate).
    assert "absolute_money" in find_violations("You could make $39,000 profit")
    assert "absolute_money" in find_violations("Just $39.99 today")
    assert "absolute_money" in find_violations("up to $390 per trade")


def test_absolute_money_emitted_once_even_if_multiple_matches():
    # Two non-whitelisted matches => still single 'absolute_money' tag
    tags = find_violations("Opened $250 and closed $260")
    assert tags.count("absolute_money") == 1


# --- 4) unlabeled_simulation tag --------------------------------------------

def test_unlabeled_simulation_flagged_for_backtest_word():
    assert "unlabeled_simulation" in find_violations(
        "Our backtest results show 73% wins"
    )


def test_unlabeled_simulation_flagged_for_shadow_word():
    assert "unlabeled_simulation" in find_violations(
        "Shadow trading produced great outcomes"
    )


def test_unlabeled_simulation_flagged_for_testnet():
    assert "unlabeled_simulation" in find_violations(
        "Testnet performance was strong"
    )


def test_labeled_backtest_is_allowed():
    assert "unlabeled_simulation" not in find_violations(
        "[BACKTEST] simulated results show 73% wins"
    )


def test_labeled_testnet_is_allowed():
    assert "unlabeled_simulation" not in find_violations(
        "[TESTNET] replay showed positive expectancy"
    )


def test_clean_copy_has_no_unlabeled_simulation():
    assert "unlabeled_simulation" not in find_violations(
        "Live trading journal — see real fills below"
    )


# --- 5) backward-compat — existing tags/behavior must not regress ------------

def test_existing_tag_shapes_preserved_for_tr_phrase():
    v = find_violations("Kesin kazanç vaat ediyoruz")
    # Must still use the original-cased phrase in the tag (backward-compat shape)
    assert "banned_phrase:Kesin kazanç" in v


def test_existing_tag_shapes_preserved_for_money():
    assert "absolute_money" in find_violations("$250 kazanç")


def test_performance_pct_still_flagged():
    assert "performance_pct_claim" in find_violations("73.2% win rate")


def test_disclaimer_detection_unchanged_for_all_three_langs():
    from engine.content_jobs import COMPLIANCE_EN, COMPLIANCE_TR
    assert has_disclaimer(f"... {COMPLIANCE_TR}", lang="tr")
    assert has_disclaimer(f"... {COMPLIANCE_EN}", lang="en")
    assert has_disclaimer(
        f"... {COMPLIANCE_TR} ... {COMPLIANCE_EN}", lang="both"
    )


# --- 6) lang param contract --------------------------------------------------

def test_lang_default_is_all_and_catches_both_languages():
    assert find_violations("Kesin kazanç vaat ediyoruz")  # TR
    assert find_violations("Guaranteed profit daily")     # EN


def test_find_violations_signature_accepts_optional_lang():
    # Must be callable with text only (backward-compat)
    assert isinstance(find_violations("hello world"), list)
    # And with lang kwarg
    assert isinstance(find_violations("hello world", lang="en"), list)
