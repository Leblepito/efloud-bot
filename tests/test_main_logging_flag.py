"""When EFLOUD_LOGGING_FORMAT=json, root logger emits JSON; otherwise plain."""
from __future__ import annotations

import io
import logging
import os
from unittest import mock

from utils.logging import configure_json_logging


def test_no_op_when_env_flag_unset(caplog):
    os.environ.pop("EFLOUD_LOGGING_FORMAT", None)
    # Set a plain handler, then call configure
    root = logging.getLogger()
    initial_handlers = list(root.handlers)
    configure_json_logging()
    assert root.handlers == initial_handlers, (
        "configure_json_logging() must be no-op when EFLOUD_LOGGING_FORMAT != 'json'"
    )


def test_emits_json_when_flag_set():
    with mock.patch.dict(os.environ, {"EFLOUD_LOGGING_FORMAT": "json"}):
        # Reset handlers
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_json_logging()
        assert len(root.handlers) == 1
        # Capture output
        buf = io.StringIO()
        root.handlers[0].stream = buf
        logging.getLogger("test").info("hello")
        line = buf.getvalue().strip()
        import json
        parsed = json.loads(line)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"


def test_setup_logging_uses_json_formatter_when_flag_set(tmp_path):
    """main.setup_logging() must honor EFLOUD_LOGGING_FORMAT=json,
    otherwise the bot's own logging override would clobber configure_json_logging().
    """
    import json
    from main import setup_logging

    log_path = tmp_path / "efloud_test.log"
    with mock.patch.dict(os.environ, {"EFLOUD_LOGGING_FORMAT": "json"}):
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        setup_logging(level="INFO", log_file=str(log_path))
        # Capture stream output
        buf = io.StringIO()
        # First handler is StreamHandler(stdout); swap its stream
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert stream_handlers, "expected a StreamHandler on root after setup_logging()"
        stream_handlers[0].stream = buf
        logging.getLogger("efloud.test").info("smoke")
        line = buf.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["message"] == "smoke"
        assert parsed["level"] == "INFO"
    # Cleanup file handlers so tmp_path can be removed
    for h in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
