"""PR A — preflight flat-book gate. A pending margin/position-mode change is
rejected by Binance while any position or order is open, so preflight must FAIL
in that case rather than let the operator half-apply the switch."""
from preflight import evaluate_flat_book


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
