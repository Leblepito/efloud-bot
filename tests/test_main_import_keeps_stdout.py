"""Importing main.py must not replace sys.stdout/sys.stderr.

On Windows main.py used to wrap stdout/stderr in a new TextIOWrapper at import
time. Under pytest the old capture stream then got closed, so any run that
imported main crashed with "ValueError: I/O operation on closed file" before a
single test ran. The UTF-8 console fix now runs only when main.py is the
entry point (same pattern as preflight.py).
"""
from __future__ import annotations

import importlib
import sys
from unittest import mock


def test_import_main_leaves_std_streams_alone():
    sys.modules.pop("main", None)
    out, err = sys.stdout, sys.stderr
    with mock.patch.object(sys, "platform", "win32"):
        importlib.import_module("main")
    assert sys.stdout is out
    assert sys.stderr is err


def test_utf8_console_helper_still_wraps_on_windows():
    import main

    fake_out, fake_err = mock.MagicMock(), mock.MagicMock()
    with mock.patch.object(sys, "platform", "win32"), \
            mock.patch.object(sys, "stdout", fake_out), \
            mock.patch.object(sys, "stderr", fake_err), \
            mock.patch("io.TextIOWrapper") as wrapper:
        main._force_utf8_console()
        assert wrapper.call_count == 2
        assert sys.stdout is wrapper.return_value
        assert sys.stderr is wrapper.return_value
