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


# ─────────────────────────────────────────────────────────────────────
# R-13 (2026-07-18): log_event + attach_json_file_handler
# Overseer'ın log yüzeyi için: (1) yapısal event satırı üreten helper,
# (2) backend Docker yolunda /app/logs/efloud_bot.log'u YAZAN dosya handler'ı
# (configure_json_logging yalnız stdout kuruyordu — dosya hiç yazılmıyordu,
# overseer'ın JsonLogTail'i boş dosyaya bakıyordu).
# ─────────────────────────────────────────────────────────────────────


def test_log_event_emits_event_field_via_json_formatter():
    from utils.logging import log_event
    logger = logging.getLogger("test.r13.log_event")
    logger.setLevel(logging.INFO)
    records = []

    class _Cap(logging.Handler):
        def emit(self, record):
            records.append(record)

    h = _Cap()
    logger.addHandler(h)
    try:
        log_event(logger, "cycle_start", cycle_n=7)
    finally:
        logger.removeHandler(h)
    assert len(records) == 1
    out = json.loads(JsonFormatter().format(records[0]))
    assert out["event"] == "cycle_start"
    assert out["cycle_n"] == 7
    assert out["message"] == "cycle_start"
    assert "ts" in out


def test_log_event_plain_formatter_safe():
    """JSON formatter yokken de kırılmamalı — mesaj düz event adıdır."""
    from utils.logging import log_event
    logger = logging.getLogger("test.r13.plain")
    logger.setLevel(logging.INFO)
    log_event(logger, "regime_change", symbol="BTC/USDT", old="TREND", new="RANGE")


def test_attach_json_file_handler_writes_json_lines(tmp_path):
    from utils.logging import attach_json_file_handler, log_event
    log_file = tmp_path / "logs" / "efloud_bot.log"  # parent da oluşturulmalı
    logger = logging.getLogger("test.r13.filehandler")
    logger.setLevel(logging.INFO)
    fh = attach_json_file_handler(str(log_file))
    try:
        log_event(logger, "cycle_start", cycle_n=3)
        fh.flush()
    finally:
        logging.getLogger().removeHandler(fh)
        fh.close()
    lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 1
    rec = json.loads(lines[-1])
    assert rec["event"] == "cycle_start"
    assert rec["cycle_n"] == 3
    assert rec["level"] == "INFO"
    assert "ts" in rec


def test_attach_json_file_handler_always_json_regardless_of_env(tmp_path, monkeypatch):
    """Dosya makine yüzeyidir: EFLOUD_LOGGING_FORMAT json OLMASA da dosyaya
    JSON yazılır (stdout formatı ne olursa olsun overseer parse edebilmeli)."""
    monkeypatch.delenv("EFLOUD_LOGGING_FORMAT", raising=False)
    from utils.logging import attach_json_file_handler
    log_file = tmp_path / "bot.log"
    logger = logging.getLogger("test.r13.envfree")
    logger.setLevel(logging.INFO)
    fh = attach_json_file_handler(str(log_file))
    try:
        logger.info("plain message", extra={"event": "x"})
        fh.flush()
    finally:
        logging.getLogger().removeHandler(fh)
        fh.close()
    rec = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["message"] == "plain message"
    assert rec["event"] == "x"
