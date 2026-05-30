"""Tests for SL repair precision rounding in _repair_missing_protection_orders.

The SL repair path ("SL order completely missing") must protect the FULL
position. Before this fix it sent the raw ``pos.size`` without applying the
exchange's amount precision, while the TP1/TP2 repair paths in the same method
DID apply ``amount_to_precision``. Unrounded sizes can hit Binance
stepSize/lotSize precision errors and get rejected, leaving the position
unprotected.

Safety-critical invariant: the SL repair amount must equal the FULL
``pos.size`` (rounded) — NEVER half / tp2_size. Scaling the SL to half the
position would leave a naked half-position.

These tests drive the REAL ``_repair_missing_protection_orders`` method with a
mocked exchange client (matching the fixture style in ``test_sl_retry.py``),
giving genuine regression protection rather than testing a re-implemented
snippet.
"""
from unittest.mock import MagicMock
import pytest

from exchange import BinanceClient, OrderManager, Position


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    return client


@pytest.fixture
def mgr(mock_client):
    return OrderManager(mock_client, dry_run=False)


def _make_pos(size=1.23456, tp1_hit=False, tp2=97000):
    """Position with a MISSING SL order (sl_order_id=='') so repair triggers.

    TP1/TP2 order IDs are set so the SL repair is the only path exercised.
    """
    return Position(
        symbol="BTC/USDT", direction="LONG",
        entry=95000, sl=94000, tp1=96000, tp2=tp2,
        size=size,
        order_id="ENTRY-1", sl_order_id="",  # Missing SL!
        tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        tp1_hit=tp1_hit,
    )


def _sl_create_call(mock_client):
    """Return the create_order call_args for the STOP_MARKET (SL) order."""
    for call in mock_client.exchange.create_order.call_args_list:
        if call.args[1] == "STOP_MARKET":
            return call
    return None


def _sl_amount(call):
    """Extract the amount argument (positional index 3) from a create_order call."""
    return call.args[3]


# ─────────────────────────────────────────────────────────────
# Safety-critical: SL repair must keep the FULL position size
# ─────────────────────────────────────────────────────────────


def test_sl_repair_keeps_full_size(mgr, mock_client):
    """Even when tp1_hit is True, SL repair amount == FULL pos.size (rounded),
    NOT tp2_size / half. This is the key naked-half-position safety assertion.
    """
    # amount_to_precision echoes the value back rounded to 3 dp as a string.
    mock_client.exchange.amount_to_precision.side_effect = (
        lambda sym, amt: f"{amt:.3f}"
    )
    mock_client.exchange.create_order.return_value = {"id": "SL-REPAIR"}

    pos = _make_pos(size=2.0, tp1_hit=True, tp2=97000)
    mgr.positions.append(pos)

    mgr._repair_missing_protection_orders(bn_order_ids={"TP1-1", "TP2-1"})

    sl_call = _sl_create_call(mock_client)
    assert sl_call is not None, "SL STOP_MARKET repair order was not sent"
    # Full size 2.0 rounded to 3dp == 2.0, NOT 1.0 (half / tp2_size).
    assert _sl_amount(sl_call) == 2.0
    assert pos.sl_order_id == "SL-REPAIR"


def test_sl_repair_applies_precision(mgr, mock_client):
    """amount_to_precision returning '1.234' for 1.23456 → SL sent with 1.234."""
    def _to_precision(sym, amt):
        # Emulate exchange truncation to 3 decimals.
        return "1.234" if abs(amt - 1.23456) < 1e-9 else f"{amt:.3f}"

    mock_client.exchange.amount_to_precision.side_effect = _to_precision
    mock_client.exchange.create_order.return_value = {"id": "SL-REPAIR"}

    pos = _make_pos(size=1.23456)
    mgr.positions.append(pos)

    mgr._repair_missing_protection_orders(bn_order_ids={"TP1-1", "TP2-1"})

    sl_call = _sl_create_call(mock_client)
    assert sl_call is not None
    assert _sl_amount(sl_call) == 1.234
    # Precision was actually consulted for the SL size.
    assert any(
        abs(c.args[1] - 1.23456) < 1e-9
        for c in mock_client.exchange.amount_to_precision.call_args_list
    ), "amount_to_precision was never called with the raw SL size"


def test_sl_repair_dry_run_skips_precision():
    """dry_run True → no amount_to_precision call; SL sent with raw pos.size."""
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    client.exchange.create_order.return_value = {"id": "SL-REPAIR"}

    mgr = OrderManager(client, dry_run=True)
    pos = _make_pos(size=1.23456)
    mgr.positions.append(pos)

    mgr._repair_missing_protection_orders(bn_order_ids={"TP1-1", "TP2-1"})

    client.exchange.amount_to_precision.assert_not_called()


def test_sl_repair_precision_failure_falls_back_to_raw(mgr, mock_client):
    """If amount_to_precision raises, fall back to raw pos.size — no crash,
    SL still attempted with the full raw size.
    """
    mock_client.exchange.amount_to_precision.side_effect = RuntimeError("boom")
    mock_client.exchange.create_order.return_value = {"id": "SL-REPAIR"}

    pos = _make_pos(size=1.23456)
    mgr.positions.append(pos)

    mgr._repair_missing_protection_orders(bn_order_ids={"TP1-1", "TP2-1"})

    sl_call = _sl_create_call(mock_client)
    assert sl_call is not None, "SL repair must still be attempted after precision error"
    assert _sl_amount(sl_call) == 1.23456  # raw, unrounded
    assert pos.sl_order_id == "SL-REPAIR"
