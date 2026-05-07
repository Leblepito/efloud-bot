"""generate_signals — per-symbol confluence threshold override.

Aggressive Mode v1 needs to apply DIFFERENT confluence thresholds to different
symbols (good coins: conf=70 for more action; weak coins: conf=85-90 to be
selective). This test pins the contract for `symbol_confluence_overrides`.

The override is a dict {symbol: threshold}. The signal-generation gate uses
the per-symbol value if present, else falls back to the global `min_confluence`.

These tests don't run the full SMC pipeline — they isolate the threshold
lookup logic via a small helper exposed for testing.
"""
import pytest

from engine.signals import resolve_min_confluence


def test_no_override_uses_global_default():
    threshold = resolve_min_confluence(
        symbol="BTC/USDT",
        global_min=70,
        symbol_overrides=None,
    )
    assert threshold == 70


def test_empty_overrides_uses_global_default():
    threshold = resolve_min_confluence(
        symbol="BTC/USDT",
        global_min=70,
        symbol_overrides={},
    )
    assert threshold == 70


def test_explicit_symbol_override_wins():
    threshold = resolve_min_confluence(
        symbol="ETH/USDT",
        global_min=70,
        symbol_overrides={"ETH/USDT": 75, "BNB/USDT": 90},
    )
    assert threshold == 75


def test_unlisted_symbol_falls_back_to_global():
    """ADA not in overrides table — gets global default."""
    threshold = resolve_min_confluence(
        symbol="ADA/USDT",
        global_min=70,
        symbol_overrides={"ETH/USDT": 75, "BNB/USDT": 90},
    )
    assert threshold == 70


def test_weak_symbol_high_threshold():
    """Bot's weakest coin gets a near-impossible threshold."""
    threshold = resolve_min_confluence(
        symbol="BNB/USDT",
        global_min=70,
        symbol_overrides={"BNB/USDT": 90},
    )
    assert threshold == 90


def test_symbol_format_normalization():
    """Tolerate `ETHUSDT` (no slash) form too — exchange APIs sometimes return that."""
    # If the implementation normalizes both keys and queries to a canonical form,
    # these should both resolve. We pick "with slash" as canonical.
    threshold = resolve_min_confluence(
        symbol="ETHUSDT",
        global_min=70,
        symbol_overrides={"ETH/USDT": 75},
    )
    assert threshold == 75


def test_zero_override_means_zero_not_falsy_global():
    """Edge case: override=0 (literally zero, not None) should be respected.
    A naive `or` would fall back to global. Must use explicit None/missing check.
    """
    threshold = resolve_min_confluence(
        symbol="LINK/USDT",
        global_min=70,
        symbol_overrides={"LINK/USDT": 0},
    )
    assert threshold == 0
