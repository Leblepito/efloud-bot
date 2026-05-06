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
