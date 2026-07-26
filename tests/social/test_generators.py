"""backend.social.generators — compliance + rotasyon + fallback testleri."""
from __future__ import annotations

import pytest

from backend.social.generators import (
    DISCLAIMER,
    EDU_POOL,
    X_CHAR_LIMIT,
    build_cycle_drafts,
    build_educational,
    build_fleet_status,
    build_market_update,
    post_type_for_slot,
    slot_index_for_hour,
)
from scripts.content_compliance import find_violations

KRONOS_OK = {
    "profile": "mid",
    "symbols": {
        "BTC": {
            "aligned": True,
            "layers": {
                "htf": {"direction": "UP", "band": "NARROW", "confirmed": True},
                "mtf": {"direction": "UP", "band": "MODERATE", "confirmed": True},
                "ltf": {"direction": "UP", "band": "NARROW", "confirmed": True},
            },
        },
        "ETH": {
            "aligned": None,
            "layers": {
                "htf": {"direction": None, "band": "WIDE", "confirmed": False},
            },
        },
        "SOL": {
            "aligned": False,
            "layers": {
                "htf": {"direction": "DOWN", "band": "MODERATE", "confirmed": True},
            },
        },
    },
}

FLEET_OK = {
    "bots": {
        "scalp": {"up": True, "tf": "5m/1h/12h"},
        "mid": {"up": True, "tf": "15m/1h/4h"},
        "long": {"up": True, "tf": "1h/8h/1w"},
    },
    "open_positions": 7,
    "signals_24h": 132,
}


# ── Compliance: üretilen HER kombinasyon gate'den temiz çıkmalı ──


@pytest.mark.parametrize("slot", range(6))
@pytest.mark.parametrize("lang", ["en", "ru"])
def test_all_slots_compliance_clean(slot, lang):
    specs = build_cycle_drafts(
        slot=slot,
        day_ordinal=739_000 + slot,
        kronos=KRONOS_OK,
        fleet=FLEET_OK,
        langs=(lang,),
    )
    assert specs, "her slot en az 1 draft üretmeli"
    for spec in specs:
        assert find_violations(spec.body, lang="all") == [], spec.body


@pytest.mark.parametrize("idx", range(len(EDU_POOL)))
@pytest.mark.parametrize("lang", ["en", "ru"])
def test_full_edu_pool_compliance_clean(idx, lang):
    body = build_educational(day_ordinal=idx, slot=0, lang=lang)
    assert find_violations(body, lang="all") == [], body


# ── X karakter limiti ──


@pytest.mark.parametrize("slot", range(6))
@pytest.mark.parametrize("lang", ["en", "ru"])
def test_x_char_limit(slot, lang):
    for spec in build_cycle_drafts(
        slot=slot, day_ordinal=739_123, kronos=KRONOS_OK, fleet=FLEET_OK, langs=(lang,)
    ):
        assert len(spec.body) <= X_CHAR_LIMIT, (len(spec.body), spec.body)


# ── Disclaimer her post'ta ──


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_disclaimer_present(lang):
    for slot in range(3):
        for spec in build_cycle_drafts(
            slot=slot, day_ordinal=739_200, kronos=KRONOS_OK, fleet=FLEET_OK, langs=(lang,)
        ):
            assert DISCLAIMER[lang] in spec.body


def test_en_disclaimer_matches_engine_constant():
    """generators EN disclaimer'ı engine.content_jobs.COMPLIANCE_EN ile birebir."""
    from engine.content_jobs import COMPLIANCE_EN

    assert DISCLAIMER["en"] == COMPLIANCE_EN


# ── Rotasyon ──


def test_slot_rotation():
    assert slot_index_for_hour(0) == 0
    assert slot_index_for_hour(4) == 1
    assert slot_index_for_hour(23) == 5
    assert post_type_for_slot(0) == "market_update"
    assert post_type_for_slot(1) == "performance_recap"
    assert post_type_for_slot(2) == "educational"
    assert post_type_for_slot(3) == "market_update"


# ── Fallback davranışı ──


def test_market_update_without_kronos_falls_back_to_educational():
    specs = build_cycle_drafts(
        slot=0, day_ordinal=739_300, kronos=None, fleet=FLEET_OK, langs=("en",)
    )
    assert specs[0].post_type == "educational"
    assert specs[0].meta["wanted_type"] == "market_update"


def test_fleet_status_with_down_bot_falls_back_to_educational():
    fleet_down = {
        "bots": {
            "scalp": {"up": False, "tf": "5m/1h/12h"},
            "mid": {"up": True, "tf": "15m/1h/4h"},
            "long": {"up": True, "tf": "1h/8h/1w"},
        },
    }
    specs = build_cycle_drafts(
        slot=1, day_ordinal=739_300, kronos=None, fleet=fleet_down, langs=("en",)
    )
    assert specs[0].post_type == "educational"
    assert build_fleet_status(fleet_down, "en") is None


def test_market_update_reports_noise_for_unconfirmed():
    body = build_market_update(KRONOS_OK, "en")
    assert body is not None
    assert "ETH: mixed runs = noise" in body
    assert "BTC: up, narrow band" in body


def test_market_update_ru_localized():
    body = build_market_update(KRONOS_OK, "ru")
    assert body is not None
    assert "вверх" in body  # UP çevirisi
    assert DISCLAIMER["ru"] in body


# ── Meta / platform işaretleri ──


def test_meta_platforms_and_source():
    specs = build_cycle_drafts(
        slot=0,
        day_ordinal=739_400,
        kronos=KRONOS_OK,
        fleet=FLEET_OK,
        langs=("en", "ru"),
        platforms=("x", "instagram"),
    )
    assert len(specs) == 2
    for spec in specs:
        assert spec.meta["platforms"] == ["x", "instagram"]
        assert spec.meta["source"] == "social_content_routine"


def test_no_absolute_dollar_amounts_in_kronos_text():
    """Kronos verisinde fiyat olsa bile metne $ sızmamalı."""
    body_en = build_market_update(KRONOS_OK, "en") or ""
    body_ru = build_market_update(KRONOS_OK, "ru") or ""
    assert "$" not in body_en and "$" not in body_ru
