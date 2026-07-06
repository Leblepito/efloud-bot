"""Tests for trade-horizon timeframe profile resolution (resolve_timeframes).

Spec: docs/superpowers/specs/2026-05-31-trade-horizon-profiles-design-spec.md
Profiles: scalp=5m/1h/4h, mid=15m/4h/12h, long=1h/8h/1d (operatör 2026-07-06). Chain must be
strictly monotonically increasing. Missing/`custom` profile → explicit fallback
(backward compatible). Unknown profile or non-monotonic chain → ValueError.
"""
import pytest

from data.timeframes import resolve_timeframes, PROFILES


@pytest.mark.parametrize("profile,entry,mtf,htf", [
    ("scalp", "5m", "1h", "4h"),
    ("mid", "15m", "4h", "12h"),
    ("long", "1h", "8h", "1d"),
])
def test_profile_resolves_to_canonical_triple(profile, entry, mtf, htf):
    cfg = {"timeframes": {"profile": profile, "kline_limit": 500}}
    out = resolve_timeframes(cfg)
    assert out["entry"] == entry
    assert out["mtf"] == mtf
    assert out["htf"] == htf
    assert out["profile"] == profile


def test_profiles_constant_matches_spec():
    assert PROFILES["scalp"] == ("5m", "1h", "4h")
    assert PROFILES["mid"] == ("15m", "4h", "12h")
    assert PROFILES["long"] == ("1h", "8h", "1d")


def test_missing_profile_uses_explicit_backward_compat():
    # No `profile` key → behave exactly as before (existing config.phase2_1k.yaml).
    cfg = {"timeframes": {"entry": "15m", "mtf": "1h", "htf": "4h", "kline_limit": 500}}
    out = resolve_timeframes(cfg)
    assert (out["entry"], out["mtf"], out["htf"]) == ("15m", "1h", "4h")
    assert out["profile"] == "custom"


def test_custom_profile_uses_explicit():
    cfg = {"timeframes": {"profile": "custom", "entry": "5m", "mtf": "30m", "htf": "2h"}}
    out = resolve_timeframes(cfg)
    assert (out["entry"], out["mtf"], out["htf"]) == ("5m", "30m", "2h")


def test_profile_takes_precedence_over_explicit():
    # When a named profile is set, explicit entry/mtf/htf are ignored.
    cfg = {"timeframes": {"profile": "scalp", "entry": "15m", "mtf": "1h", "htf": "4h"}}
    out = resolve_timeframes(cfg)
    assert (out["entry"], out["mtf"], out["htf"]) == ("5m", "1h", "4h")


def test_unknown_profile_raises():
    cfg = {"timeframes": {"profile": "swing"}}
    with pytest.raises(ValueError):
        resolve_timeframes(cfg)


def test_non_monotonic_custom_raises():
    # mtf <= entry → invalid chain, fail fast.
    cfg = {"timeframes": {"entry": "1h", "mtf": "15m", "htf": "4h"}}
    with pytest.raises(ValueError):
        resolve_timeframes(cfg)


def test_equal_levels_non_monotonic_raises():
    cfg = {"timeframes": {"entry": "1h", "mtf": "1h", "htf": "4h"}}
    with pytest.raises(ValueError):
        resolve_timeframes(cfg)


def test_mutates_cfg_in_place_for_all_consumers():
    # All entry points (main.py, bot_runner.py, backtest) read cfg["timeframes"]
    # directly; resolution must write resolved values back into the dict.
    cfg = {"timeframes": {"profile": "scalp", "kline_limit": 500}}
    resolve_timeframes(cfg)
    tf = cfg["timeframes"]
    assert tf["entry"] == "5m"
    assert tf["mtf"] == "1h"
    assert tf["htf"] == "4h"


def test_kline_limit_capped_for_weekly_htf():
    # long artık 1d; weekly cap davranışı custom 1w chain ile korunarak test edilir.
    cfg = {"timeframes": {"profile": "custom", "entry": "1h", "mtf": "8h", "htf": "1w", "kline_limit": 500}}
    out = resolve_timeframes(cfg)
    assert out["kline_limit"] == 250  # weekly history cap


def test_kline_limit_preserved_for_long_daily_htf():
    cfg = {"timeframes": {"profile": "long", "kline_limit": 500}}
    out = resolve_timeframes(cfg)
    assert out["kline_limit"] == 500


def test_kline_limit_preserved_for_non_weekly():
    cfg = {"timeframes": {"profile": "mid", "kline_limit": 500}}
    out = resolve_timeframes(cfg)
    assert out["kline_limit"] == 500


def test_kline_limit_default_when_absent():
    cfg = {"timeframes": {"profile": "mid"}}
    out = resolve_timeframes(cfg)
    assert out["kline_limit"] == 500
