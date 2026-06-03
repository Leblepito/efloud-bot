"""C3: open_position must persist AFTER SL/TP verification, not before.

open_position appended the position and `_persist()`-ed it BEFORE
`_verify_and_repair_protection`. The verify can take verify_delay×attempts
(~7.5s). A crash in that window left the on-disk state claiming a possibly-bare
position is open+protected. Persisting only AFTER verify confirms protection
means a crash mid-verify leaves no false "protected" record — the position is an
exchange-only orphan that orphan_protection adopts on restart. (The rollback path
persists its own flattened state inside _verify_and_repair_protection's finally.)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from exchange import BinanceClient, OrderManager


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


def test_persist_happens_after_verify_on_successful_open(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0},  # entry
        {"id": "SL-1"},                     # SL
        {"id": "TP1-1"},                    # TP1
        {"id": "TP2-1"},                    # TP2
    ]
    order = []
    with patch.object(mgr, "_persist", side_effect=lambda *a, **k: order.append("persist")), \
         patch.object(mgr, "_verify_and_repair_protection",
                      side_effect=lambda *a, **k: (order.append("verify"), {})[1]):
        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0, entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

    assert pos is not None
    assert order == ["verify", "persist"], (
        f"C3: persist must follow verify (only a verified-protected position is "
        f"written to disk), got {order}"
    )
