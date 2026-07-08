"""PR A — preflight flat-book gate. A pending margin/position-mode change is
rejected by Binance while any position or order is open, so preflight must FAIL
in that case rather than let the operator half-apply the switch."""
from unittest.mock import MagicMock

from preflight import evaluate_flat_book, count_open_book


def test_flat_book_ok_when_no_change_needed():
    ok, msg = evaluate_flat_book(mode_change_needed=False, open_positions=3, open_orders=2)
    assert ok is True


def test_flat_book_ok_when_change_needed_and_flat():
    ok, msg = evaluate_flat_book(mode_change_needed=True, open_positions=0, open_orders=0)
    assert ok is True


def test_flat_book_fails_when_change_needed_and_positions_open():
    ok, msg = evaluate_flat_book(mode_change_needed=True, open_positions=1, open_orders=0)
    assert ok is False
    assert "flat" in msg.lower()


def test_flat_book_fails_when_change_needed_and_orders_open():
    ok, msg = evaluate_flat_book(mode_change_needed=True, open_positions=0, open_orders=5)
    assert ok is False
    assert "flat" in msg.lower()


def test_importing_preflight_has_no_side_effects(capsys):
    # Importing preflight must NOT run the banner/API checks (body is under main()).
    import importlib
    import preflight
    importlib.reload(preflight)
    out = capsys.readouterr().out
    assert "PRE-FLIGHT CHECK" not in out


# -- count_open_book -- 2026-07-08 debug session -----------------------------
# Bug: preflight's flat-book check only called ex.fetch_open_orders(), which
# does NOT include Binance's server-side ALGO orders (STOP_MARKET /
# TAKE_PROFIT_MARKET -- exactly how this bot places SL/TP). A leftover algo
# SL/TP from a previously-closed position made preflight report "0 open
# orders" (falsely flat) while Binance's own dualSidePosition change still
# rejected because the book genuinely wasn't flat. This mirrors the fix
# already applied to the reconcile path (exchange/__init__.py,
# fapiPrivateGetOpenAlgoOrders) for the 2026-05-09 LTC/ADA incident.

def _mock_exchange(positions=None, regular_orders=None, algo_orders=None,
                    regular_orders_raises=False, algo_raises=False):
    ex = MagicMock()
    if regular_orders_raises:
        ex.fetch_positions.side_effect = RuntimeError("network error")
    else:
        ex.fetch_positions.return_value = positions or []
        ex.fetch_open_orders.return_value = regular_orders or []
    if algo_raises:
        ex.fapiPrivateGetOpenAlgoOrders.side_effect = RuntimeError("algo endpoint down")
    else:
        ex.fapiPrivateGetOpenAlgoOrders.return_value = algo_orders or []
    return ex


def test_count_open_book_includes_algo_orders_in_total():
    """The exact bug scenario: 0 regular orders, but 1 leftover algo SL/TP --
    must be counted, not silently dropped."""
    ex = _mock_exchange(
        positions=[], regular_orders=[],
        algo_orders=[{"algoId": "1", "symbol": "BTCUSDT", "type": "STOP_MARKET"}],
    )
    n_pos, n_ord, regular_ok, algo_ok = count_open_book(ex)
    assert n_pos == 0
    assert n_ord == 1  # would have been 0 with the old plain fetch_open_orders() call
    assert regular_ok is True
    assert algo_ok is True


def test_count_open_book_regular_fetch_failure_fails_open():
    ex = _mock_exchange(regular_orders_raises=True)
    n_pos, n_ord, regular_ok, algo_ok = count_open_book(ex)
    assert (n_pos, n_ord) == (0, 0)
    assert regular_ok is False
    assert algo_ok is False


def test_count_open_book_algo_fetch_failure_flags_undercount_not_silent_zero():
    """Regular fetch succeeds (0 orders) but algo fetch fails -- must NOT report
    a confident flat book; algo_ok=False tells the caller the count may be an
    undercount rather than a verified zero."""
    ex = _mock_exchange(positions=[], regular_orders=[], algo_raises=True)
    n_pos, n_ord, regular_ok, algo_ok = count_open_book(ex)
    assert n_pos == 0
    assert n_ord == 0
    assert regular_ok is True
    assert algo_ok is False


def test_count_open_book_counts_open_positions_by_nonzero_contracts():
    ex = _mock_exchange(
        positions=[{"contracts": "0.5"}, {"contracts": "0"}, {"contracts": 0}],
        regular_orders=[],
    )
    n_pos, n_ord, regular_ok, algo_ok = count_open_book(ex)
    assert n_pos == 1
