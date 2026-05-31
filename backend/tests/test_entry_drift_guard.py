"""Entry-drift guard — reject market entries that have run too far from the signal.

Root cause (live incident 2026-05-31): the strategy computes entry/SL/TP from the
last CLOSED entry-bar's price, but the entry executes as a MARKET order at the
LIVE price. Inside the still-forming bar the live price can drift ~1-2% from the
signal. When it drifts toward TP, the take-profit target (anchored to the stale
signal price) is already passed → Binance rejects the TP with -2021 "Order would
immediately trigger" → the position is left with only an SL on the exchange.

Observed fills:
    SOL/USDT SHORT  signal=82.79  fill=81.95  drift=-1.0%  → TP1 81.99 already passed
    ADA/USDT SHORT  signal=0.2373 fill=0.2327 drift=-1.9%  → TP1 0.2357 above fill

Guard: before placing the market entry, compare the live price to the signal
entry. If it drifted beyond `max_entry_drift_pct`, or has already reached/passed
TP1 (making the TP unplaceable), reject the entry — do NOT open a position that
would be SL-only with a degraded/inverted reward.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from exchange import BinanceClient, OrderManager


# ── pure guard logic ──────────────────────────────────────────────

def test_allow_when_live_near_signal():
    """Small drift within threshold → no rejection."""
    reason = OrderManager._entry_drift_rejection(
        direction="SHORT", live_price=82.70, entry=82.79, tp1=81.99, max_drift_pct=0.5,
    )
    assert reason is None


def test_reject_when_drift_exceeds_threshold():
    """The live SOL case: 1% drift > 0.5% threshold → reject."""
    reason = OrderManager._entry_drift_rejection(
        direction="SHORT", live_price=81.95, entry=82.79, tp1=81.99, max_drift_pct=0.5,
    )
    assert reason is not None
    assert "drift" in reason.lower()


def test_reject_short_when_live_already_past_tp1_within_threshold():
    """Tight-TP trade: drift under threshold but live already at/below TP1
    (SHORT) → TP unplaceable → reject. Independent of the % check."""
    reason = OrderManager._entry_drift_rejection(
        direction="SHORT", live_price=99.6, entry=100.0, tp1=99.7, max_drift_pct=5.0,
    )
    assert reason is not None
    assert "tp1" in reason.lower()


def test_reject_long_when_live_already_past_tp1():
    reason = OrderManager._entry_drift_rejection(
        direction="LONG", live_price=100.4, entry=100.0, tp1=100.3, max_drift_pct=5.0,
    )
    assert reason is not None
    assert "tp1" in reason.lower()


def test_allow_long_when_live_below_tp1_and_within_threshold():
    reason = OrderManager._entry_drift_rejection(
        direction="LONG", live_price=100.1, entry=100.0, tp1=101.0, max_drift_pct=0.5,
    )
    assert reason is None


def test_disabled_when_threshold_zero():
    """max_drift_pct <= 0 disables the guard entirely (backward-compat)."""
    reason = OrderManager._entry_drift_rejection(
        direction="SHORT", live_price=50.0, entry=82.79, tp1=81.99, max_drift_pct=0.0,
    )
    assert reason is None


def test_unevaluable_prices_do_not_block():
    """Non-positive entry/live can't be evaluated → never block (fail-open;
    a missing price must not silently halt trading)."""
    assert OrderManager._entry_drift_rejection(
        direction="SHORT", live_price=0.0, entry=82.79, tp1=81.99, max_drift_pct=0.5,
    ) is None
    assert OrderManager._entry_drift_rejection(
        direction="SHORT", live_price=82.0, entry=0.0, tp1=81.99, max_drift_pct=0.5,
    ) is None


# ── open_position integration ─────────────────────────────────────

def _live_order_mgr(get_price_value: float, max_drift_pct: float) -> tuple:
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.get_price.return_value = get_price_value
    client.to_ccxt_symbol.return_value = "SOL/USDT:USDT"
    mgr = OrderManager(
        client, dry_run=False, hedge_mode=True,
        max_entry_drift_pct=max_drift_pct,
    )
    return mgr, client


def test_open_position_rejected_on_drift_places_no_orders():
    """The whole point: a drifted entry returns None and places NO exchange
    order (no market entry, no SL, no TP)."""
    mgr, client = _live_order_mgr(get_price_value=81.95, max_drift_pct=0.5)

    result = mgr.open_position(
        symbol="SOL/USDT", direction="SHORT", size=2.6,
        entry=82.79, sl=83.09, tp1=81.99, tp2=81.84,
    )

    assert result is None
    client.exchange.create_order.assert_not_called()
    assert mgr.positions == []


def test_open_position_guard_inert_when_disabled():
    """max_entry_drift_pct=0 → guard never fetches a live price; existing
    behavior (attempt the entry) is preserved."""
    mgr, client = _live_order_mgr(get_price_value=81.95, max_drift_pct=0.0)
    # Make the market entry succeed so the flow proceeds past the (absent) guard.
    client.exchange.create_order.return_value = {"id": "1", "average": 81.95}
    client.exchange.amount_to_precision.return_value = "2.6"

    mgr.open_position(
        symbol="SOL/USDT", direction="SHORT", size=2.6,
        entry=82.79, sl=83.09, tp1=81.99, tp2=81.84,
    )

    client.get_price.assert_not_called()       # guard disabled → no live fetch
    client.exchange.create_order.assert_called()  # entry was attempted
