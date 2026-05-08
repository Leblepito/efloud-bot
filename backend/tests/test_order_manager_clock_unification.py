"""Clock-unification regression: opened_at / closed_at must be TZ-aware UTC.

Background: `pd.Timestamp.now()` writes a local-wall-clock TZ-naive ISO string.
On a non-UTC container this silently corrupts age math (PR #17 reader is
TZ-tolerant but cannot reconstruct UTC from a misattributed local string).
Three writer spots must produce TZ-aware UTC ISO strings:

  exchange/__init__.py:244  open_position DRY path
  exchange/__init__.py:305  open_position live path
  exchange/__init__.py:446  _record_close
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from exchange import BinanceClient, OrderManager, Position


def _assert_iso_is_utc_aware(value: str) -> None:
    """ISO timestamp must parse as TZ-aware and resolve to UTC offset zero."""
    assert value, "timestamp must not be empty"
    raw = value[:-1] if value.endswith("Z") else value
    parsed = datetime.fromisoformat(raw)
    assert parsed.tzinfo is not None, (
        f"expected TZ-aware UTC ISO string, got TZ-naive: {value!r}"
    )
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed), (
        f"expected UTC offset, got {parsed.utcoffset()}: {value!r}"
    )


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


class TestOpenedAtClockUnification:
    def test_dry_run_writes_utc_aware_opened_at(self, mock_client):
        mgr = OrderManager(mock_client, dry_run=True)
        pos = mgr.open_position(
            symbol="BTC/USDT", direction="LONG",
            size=1.0, entry=95000, sl=94000, tp1=96000, tp2=97000,
        )
        assert pos is not None
        _assert_iso_is_utc_aware(pos.opened_at)

    def test_live_writes_utc_aware_opened_at(self, mock_client):
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY"}, {"id": "SL"}, {"id": "TP1"}, {"id": "TP2"},
        ]
        mgr = OrderManager(mock_client, dry_run=False)
        pos = mgr.open_position(
            symbol="BTC/USDT", direction="LONG",
            size=1.0, entry=95000, sl=94000, tp1=96000, tp2=97000,
        )
        assert pos is not None
        _assert_iso_is_utc_aware(pos.opened_at)


class TestClosedAtClockUnification:
    def test_record_close_writes_utc_aware_closed_at(self, mock_client):
        mgr = OrderManager(mock_client, dry_run=False)
        pos = Position("BTC/USDT", "LONG", 95000, 94000, 96000, 97000, 1.0)
        mgr.positions.append(pos)
        mgr._record_close(pos, exit_price=97000, reason="TP2")
        _assert_iso_is_utc_aware(pos.closed_at)
