"""Tests for SMCEngine.liquidity_pools and EqLevel dataclass.

EqLevel is the typed v2 equivalent of the existing dict-based equal_levels()
output. liquidity_pools() builds on equal_levels() to cluster equal H/L into
typed records consumed by tp_calc.
"""
import pandas as pd
import pytest

from engine.smc import SMCEngine, Swing


class TestEqLevelDataclass:
    """EqLevel must be importable from engine.smc and have the documented fields."""

    def test_eqlevel_has_price_and_kind_fields(self):
        from engine.smc import EqLevel
        e = EqLevel(price=100.0, kind="EQH", touches=2)
        assert e.price == 100.0
        assert e.kind == "EQH"
        assert e.touches == 2

    def test_eqlevel_kind_eql(self):
        from engine.smc import EqLevel
        e = EqLevel(price=50.0, kind="EQL", touches=3)
        assert e.kind == "EQL"
