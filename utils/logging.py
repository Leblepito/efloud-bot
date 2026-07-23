"""Structured JSON logging + trace_id propagation.

Used by the bot to produce machine-readable log lines suitable for the
alerter sidecar (Aşama 2 Step 4) and the daily-report cron (Step 5).

Trace IDs are 12-char hex (uuid4 truncated; ~62 bits of entropy, collision
risk negligible at this scale). They flow via contextvars.ContextVar so
async tasks each have their own copy.

Configure with `configure_json_logging()` at process startup if env var
EFLOUD_LOGGING_FORMAT == "json"; otherwise no-op (default plain logging).
"""
from __future__ import annotations

import json
import logging
import os
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────
# trace_id contextvar
# ─────────────────────────────────────────────────────────────────────

_trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def get_trace_id() -> Optional[str]:
    """Return current trace_id, or None if unset."""
    return _trace_id_ctx.get()


def set_trace_id(value: Optional[str]) -> None:
    """Set trace_id for the current async task / context."""
    _trace_id_ctx.set(value)


def new_trace_id() -> str:
    """Generate a new 12-char hex trace_id."""
    return uuid.uuid4().hex[:12]


# ─────────────────────────────────────────────────────────────────────
# JSON formatter
# ─────────────────────────────────────────────────────────────────────

_RESERVED_LOGRECORD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
    "taskName",  # Python 3.12+ adds this; treat as reserved
}


class JsonFormatter(logging.Formatter):
    """Format LogRecord as a single-line JSON object.

    Always includes: ts, level, logger, message.
    Includes trace_id if set on contextvar.
    Includes exception if exc_info present.
    Includes any non-reserved attributes set on the record (extras).
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        out: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        tid = get_trace_id()
        if tid:
            out["trace_id"] = tid
        if record.exc_info:
            out["exception"] = "".join(traceback.format_exception(*record.exc_info))
        for k, v in record.__dict__.items():
            if k in _RESERVED_LOGRECORD_FIELDS or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                out[k] = repr(v)
        # Single line, replace embedded newlines from message
        return json.dumps(out, ensure_ascii=False).replace("\n", "\\n")


# ─────────────────────────────────────────────────────────────────────
# Configuration helper
# ─────────────────────────────────────────────────────────────────────

def configure_json_logging(level: int = logging.INFO) -> None:
    """Configure root logger to emit JSON. Call once at process startup.

    Idempotent: removes any existing handlers, sets a single StreamHandler
    with JsonFormatter. Respects EFLOUD_LOGGING_FORMAT env var:
    if not "json", this function is a no-op (preserves prior config).
    """
    if os.environ.get("EFLOUD_LOGGING_FORMAT", "").lower() != "json":
        return

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(level)


# ─────────────────────────────────────────────────────────────────────
# R-13 (2026-07-18): yapısal event helper'ı + JSON dosya handler'ı
# ─────────────────────────────────────────────────────────────────────

def log_event(logger: logging.Logger, event: str, *,
              level: int = logging.INFO, **fields: Any) -> None:
    """Overseer/alerter'ın eşleyebileceği yapısal event satırı at.

    JsonFormatter ile satır `{"event": "<event>", ...fields, "ts": ISO, ...}`
    olur (extra alanlar format()'ta merge edilir); düz formatter'da mesaj
    event adıdır (zararsız tek satır). `fields` anahtarları LogRecord'un
    rezerve attr'larıyla (message/name/args/...) ÇAKIŞMAMALI — logging
    KeyError fırlatır; çağıran taraf alan adlarını sade tutar
    (symbol/old/new/cycle_n gibi)."""
    logger.log(level, event, extra={"event": event, **fields})


def attach_json_file_handler(path: str,
                             max_bytes: int = 50 * 1024 * 1024,
                             backup_count: int = 5) -> logging.Handler:
    """Root logger'a JSON-formatlı RotatingFileHandler ekle ve handler'ı döndür.

    R-13: backend Docker yolunda log DOSYASI hiç yazılmıyordu —
    configure_json_logging yalnız stdout kurar; compose'taki overseer ise
    EFLOUD_LOG_FILE'ı (/app/logs/efloud_bot.log) OKUMAYA çalışıyordu (okuyan
    var, yazan yok → JsonLogTail hep boş → log-tabanlı kurallar ölü).
    backend/main.py EFLOUD_LOG_FILE set ise bunu çağırır (env yoksa çağrılmaz
    → davranış birebir eski, default-OFF).

    Dosya MAKİNE yüzeyidir: stdout formatından bağımsız olarak HER ZAMAN
    JSON yazılır — operatör `docker logs`'ta okunaklı düz metni korurken
    overseer parse edilebilir satır alır."""
    from logging.handlers import RotatingFileHandler
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(path, maxBytes=max_bytes,
                             backupCount=backup_count, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(fh)
    return fh
