"""Telegram inline-keyboard + reply_markup — PR #16 (Phase 5 approval gate).

Additive to the send-only client: an `inline_keyboard` helper builds the
reply_markup, and `send_message` gains an optional `reply_markup` param. Buttons
carry `callback_data = draft_id|action` (Telegram caps callback_data at 64 bytes).
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from ops.alerter.telegram_client import inline_keyboard, send_message


def test_inline_keyboard_builds_telegram_structure():
    kb = inline_keyboard([
        [("✅ Approve", "d123|approve"), ("❌ Reject", "d123|reject")],
        [("✏️ Edit", "d123|edit")],
    ])
    assert kb == {"inline_keyboard": [
        [{"text": "✅ Approve", "callback_data": "d123|approve"},
         {"text": "❌ Reject", "callback_data": "d123|reject"}],
        [{"text": "✏️ Edit", "callback_data": "d123|edit"}],
    ]}


def test_callback_data_over_64_bytes_raises():
    with pytest.raises(ValueError):
        inline_keyboard([[("x", "d|" + "a" * 70)]])


def test_send_message_serializes_reply_markup():
    fake = mock.MagicMock()
    fake.__enter__.return_value.status = 200
    fake.__enter__.return_value.read.return_value = b'{"ok":true}'
    kb = inline_keyboard([[("✅", "d1|approve")]])
    with mock.patch("ops.alerter.telegram_client.urllib.request.urlopen",
                    return_value=fake) as urlopen:
        ok = send_message(token="TOK", chat_id="1", text="hi", reply_markup=kb)
    assert ok is True
    data = urlopen.call_args[0][0].data.decode("utf-8")
    assert "reply_markup" in data
    assert "d1%7Capprove" in data or "d1|approve" in data  # urlencoded pipe


def test_send_message_without_reply_markup_omits_it():
    fake = mock.MagicMock()
    fake.__enter__.return_value.status = 200
    fake.__enter__.return_value.read.return_value = b'{"ok":true}'
    with mock.patch("ops.alerter.telegram_client.urllib.request.urlopen",
                    return_value=fake) as urlopen:
        send_message(token="TOK", chat_id="1", text="hi")
    data = urlopen.call_args[0][0].data.decode("utf-8")
    assert "reply_markup" not in data
