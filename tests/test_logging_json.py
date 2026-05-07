"""JSON log formatter — ensure required fields always present."""
from __future__ import annotations

import json
import logging

import pytest

from utils.logging import JsonFormatter, get_trace_id, set_trace_id


def make_record(level=logging.INFO, msg="hello", extra=None):
    return logging.LogRecord(
        name="test", level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


def test_basic_fields_present():
    rec = make_record()
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    for key in ("ts", "level", "logger", "message"):
        assert key in parsed, f"missing field: {key}"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "hello"


def test_trace_id_picked_up_from_context():
    set_trace_id("xyz789")
    try:
        rec = make_record()
        out = JsonFormatter().format(rec)
        parsed = json.loads(out)
        assert parsed.get("trace_id") == "xyz789"
    finally:
        set_trace_id(None)


def test_trace_id_absent_when_unset():
    set_trace_id(None)
    rec = make_record()
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert "trace_id" not in parsed or parsed["trace_id"] is None


def test_extra_fields_merged():
    rec = make_record()
    rec.symbol = "BTC/USDT"
    rec.pnl_usdt = 12.5
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert parsed["symbol"] == "BTC/USDT"
    assert parsed["pnl_usdt"] == 12.5


def test_exception_serialised():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            name="test", level=logging.ERROR, pathname=__file__,
            lineno=1, msg="error", args=(), exc_info=sys.exc_info(),
        )
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert "exception" in parsed
    assert "ValueError" in parsed["exception"]


def test_output_is_single_line():
    rec = make_record(msg="multi\nline")
    out = JsonFormatter().format(rec)
    assert "\n" not in out, "JsonFormatter must produce single-line output"
