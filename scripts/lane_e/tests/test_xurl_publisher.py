"""xurl publisher — hermetic unit tests (subprocess mock'lanır)."""
from __future__ import annotations

import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scripts.lane_e.publishers.xurl import XurlPublisher
from scripts.lane_e.publishers.base import PublishResult, Publisher


# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────


def test_xurl_publisher_is_publisher_protocol():
    p = XurlPublisher()
    assert isinstance(p, Publisher)
    assert p.name == "xurl"


def test_xurl_publisher_default_disabled():
    """Default OFF — config yoksa noop."""
    p = XurlPublisher()
    assert p.enabled is False


def test_xurl_publisher_can_be_enabled():
    p = XurlPublisher(enabled=True)
    assert p.enabled is True


# ─────────────────────────────────────────────────────────────────────────────
# Publish disabled (default OFF)
# ─────────────────────────────────────────────────────────────────────────────


def test_publish_disabled_returns_noop_ok():
    p = XurlPublisher(enabled=False)
    result = p.publish({"draft_id": "x", "body": "hello"})
    assert result.ok is True
    assert result.ref is None
    assert result.platform == "xurl"


# ─────────────────────────────────────────────────────────────────────────────
# Publish enabled ama binary yok
# ─────────────────────────────────────────────────────────────────────────────


def test_publish_enabled_no_binary_returns_error():
    p = XurlPublisher(enabled=True)
    with patch("shutil.which", return_value=None):
        result = p.publish({"draft_id": "x", "body": "hello"})
    assert result.ok is False
    assert result.error is not None
    assert "xurl binary bulunamadı" in result.error


# ─────────────────────────────────────────────────────────────────────────────
# Publish enabled + binary var (subprocess mock)
# ─────────────────────────────────────────────────────────────────────────────


def _fake_completed(stdout: str = "Posted: https://x.com/u/status/123"):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = 0
    return m


def test_publish_single_tweet_succeeds():
    p = XurlPublisher(enabled=True)
    with patch("shutil.which", return_value="/usr/local/bin/xurl"), \
         patch("subprocess.run", return_value=_fake_completed()) as run_mock:
        result = p.publish({"draft_id": "x", "body": "hello world"})
    assert result.ok is True
    assert result.ref == "123"
    # subprocess.run tek çağrı (thread yok)
    assert run_mock.call_count == 1
    cmd = run_mock.call_args[0][0]
    assert cmd[0] == "/usr/local/bin/xurl"
    assert cmd[1] == "post"
    assert "hello world" in cmd


def test_publish_with_media_passes_urls():
    p = XurlPublisher(enabled=True)
    with patch("shutil.which", return_value="/usr/local/bin/xurl"), \
         patch("subprocess.run", return_value=_fake_completed()) as run_mock:
        result = p.publish({
            "draft_id": "x", "body": "with chart",
            "media": ["https://cdn.tv/chart.png"],
        })
    assert result.ok is True
    cmd = run_mock.call_args[0][0]
    assert "--media" in cmd
    assert "https://cdn.tv/chart.png" in cmd


def test_publish_thread_chains_replies():
    p = XurlPublisher(enabled=True)
    replies = [
        _fake_completed("Posted: https://x.com/u/status/100"),
        _fake_completed("Posted: https://x.com/u/status/101"),
        _fake_completed("Posted: https://x.com/u/status/102"),
    ]
    with patch("shutil.which", return_value="/usr/local/bin/xurl"), \
         patch("subprocess.run", side_effect=replies) as run_mock:
        result = p.publish({
            "draft_id": "x", "body": "first tweet",
            "thread": ["second tweet", "third tweet"],
        })
    assert result.ok is True
    assert result.ref == "100"
    # 3 çağrı: first + 2 thread
    assert run_mock.call_count == 3
    # Son reply --reply-to önceki ref olmalı
    last_cmd = run_mock.call_args_list[-1][0][0]
    assert "--reply-to" in last_cmd
    assert "101" in last_cmd


def test_publish_reply_to_chain():
    p = XurlPublisher(enabled=True)
    with patch("shutil.which", return_value="/usr/local/bin/xurl"), \
         patch("subprocess.run", return_value=_fake_completed("Posted: https://x.com/u/status/200")) as run_mock:
        result = p.publish({
            "draft_id": "x", "body": "reply",
            "reply_to": "previous_post_id_123",
        })
    assert result.ok is True
    cmd = run_mock.call_args[0][0]
    assert "--reply-to" in cmd
    assert "previous_post_id_123" in cmd


def test_publish_subprocess_timeout_returns_error():
    p = XurlPublisher(enabled=True)
    # subprocess.run check=True ile TimeoutExpired'ı kendisi raise eder.
    # Publisher'ın dış try/except'i bunu yakalayıp PublishResult.error'a çevirmeli.
    with patch("shutil.which", return_value="/usr/local/bin/xurl"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["xurl"], timeout=30)):
        result = p.publish({"draft_id": "x", "body": "hello"})
    assert result.ok is False
    assert result.error is not None


def test_publish_subprocess_called_process_error_returns_error():
    p = XurlPublisher(enabled=True)
    # CalledProcessError: subprocess.run check=True ile raise eder
    err = subprocess.CalledProcessError(returncode=1, cmd=["xurl"], stderr="auth failed")
    with patch("shutil.which", return_value="/usr/local/bin/xurl"), \
         patch("subprocess.run", side_effect=err):
        result = p.publish({"draft_id": "x", "body": "hello"})
    assert result.ok is False
    assert result.error is not None


def test_publish_stdout_without_status_url():
    """xurl sadece ID dönerse fallback parsing."""
    p = XurlPublisher(enabled=True)
    with patch("shutil.which", return_value="/usr/local/bin/xurl"), \
         patch("subprocess.run", return_value=_fake_completed("1234567890")):
        result = p.publish({"draft_id": "x", "body": "hello"})
    assert result.ok is True
    assert result.ref == "1234567890"


# ─────────────────────────────────────────────────────────────────────────────
# Lane topology guard (publisher'lar backend/social'a dokunmamalı)
# ─────────────────────────────────────────────────────────────────────────────


def test_xurl_publisher_no_backend_social_import():
    """Publisher, research lane'e (backend/social/tier2_renderers) dokunmamalı."""
    from pathlib import Path
    src = Path(__file__).parent.parent / "publishers" / "xurl.py"
    text = src.read_text(encoding="utf-8")
    assert "tier2_renderers" not in text
    assert "tv_manifest" not in text
    assert "content_queue" not in text
