"""T-20261106-05: end-to-end guard for "TP placement exhausted retries".

Scenario (live order path): entry + SL succeed, TP1 placement hits only
transient errors until `_retry_tp_order` gives up. The position must stay
tracked with SL, and the NEXT reconcile cycle must re-send TP1
(`_repair_missing_protection_orders`). While TP1 is unplaced, its id must
never be treated as a live Binance order:

  - reconcile TP1-hit detection must not fire (no phantom BE move),
  - `_estimate_exit_price` must not attribute a close to TP1,
  - `_cancel_position_siblings` must not call cancel on it.

These assertions are representation-agnostic on purpose (`_is_real_oid`
instead of `== ""`): they pin the behavior the uncommitted TP_FAILED-sentinel
WIP (main checkout, 2026-11-06) claimed to add, and show master already
provides it with the empty-string id.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from exchange import BinanceClient, OrderManager


TRANSIENT = RuntimeError("Request timed out")


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.exchange.price_to_precision = MagicMock(side_effect=lambda s, p: p)
    client.exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: a)
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    client.get_price = MagicMock(return_value=95500.0)
    return client


@pytest.fixture
def mgr(mock_client):
    om = OrderManager(mock_client, dry_run=False)
    om._persist = MagicMock()
    return om


def _open_with_tp1_exhausted(mgr, mock_client):
    """Entry + SL ok, TP1 transient x3 (exhausted), TP2 ok."""
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0},
        {"id": "SL-1"},
        TRANSIENT, TRANSIENT, TRANSIENT,
        {"id": "TP2-1"},
    ]
    with patch("exchange._time.sleep"):
        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )
    assert pos is not None, "SL-protected position must stay tracked"
    assert pos.sl_order_id == "SL-1"
    assert pos.tp2_order_id == "TP2-1"
    assert mock_client.exchange.create_order.call_count == 6
    return pos


def _exchange_state(mock_client, *, size, algo_ids):
    mock_client.get_open_positions = MagicMock(
        return_value=[{"symbol": "BTC/USDT:USDT", "contracts": size, "side": "long"}]
    )
    mock_client.exchange.fetch_open_orders = MagicMock(return_value=[])
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders = MagicMock(
        return_value=[{"algoId": a} for a in algo_ids]
    )


def test_exhausted_tp1_id_is_not_a_live_order(mgr, mock_client):
    pos = _open_with_tp1_exhausted(mgr, mock_client)
    assert not mgr._is_real_oid(pos.tp1_order_id)


def test_next_reconcile_resends_exhausted_tp1(mgr, mock_client):
    pos = _open_with_tp1_exhausted(mgr, mock_client)
    _exchange_state(mock_client, size=1.0, algo_ids=["SL-1", "TP2-1"])
    mock_client.exchange.create_order.reset_mock()
    mock_client.exchange.create_order.side_effect = None
    mock_client.exchange.create_order.return_value = {"id": "TP1-REPAIR"}

    mgr.reconcile()

    assert pos.tp1_order_id == "TP1-REPAIR"
    assert pos.tp1_hit is False, "unplaced TP1 must not be read as a TP1 fill"
    calls = mock_client.exchange.create_order.call_args_list
    assert len(calls) == 1, "only TP1 is missing — SL/TP2 must not be re-sent"
    assert calls[0].args[1] == "TAKE_PROFIT_MARKET"
    assert calls[0].kwargs["params"]["stopPrice"] == 96000
    assert calls[0].args[3] == pytest.approx(0.5)


def test_failed_repair_retries_again_next_cycle(mgr, mock_client):
    pos = _open_with_tp1_exhausted(mgr, mock_client)
    _exchange_state(mock_client, size=1.0, algo_ids=["SL-1", "TP2-1"])
    mock_client.exchange.create_order.reset_mock()
    mock_client.exchange.create_order.side_effect = ValueError("bad params")

    mgr.reconcile()  # repair fails (non-transient, single attempt)
    assert not mgr._is_real_oid(pos.tp1_order_id)

    mock_client.exchange.create_order.side_effect = None
    mock_client.exchange.create_order.return_value = {"id": "TP1-REPAIR-2"}
    mgr.reconcile()

    assert pos.tp1_order_id == "TP1-REPAIR-2"


def test_close_with_exhausted_tp1_no_tp1_attribution_or_cancel(mgr, mock_client):
    pos = _open_with_tp1_exhausted(mgr, mock_client)
    # Attribution: SL + TP2 still live, TP1 never placed -> market price, not TP1.
    exit_price = mgr._estimate_exit_price(pos, {"SL-1", "TP2-1"}, fetch_ok=True)
    assert exit_price == 95500.0

    with patch.object(mgr, "_cancel_order_any", return_value="cancelled") as cancel:
        result = mgr._cancel_position_siblings(pos, "BTC/USDT:USDT", reason="TEST")
    cancelled_ids = [c.args[0] for c in cancel.call_args_list]
    assert cancelled_ids == ["SL-1", "TP2-1"]
    assert "TP1" in result["missing"]
