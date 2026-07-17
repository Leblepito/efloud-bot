"""P-002 M1 — xurl CLI facade unit testleri.

Kapsam (her test hermetic, network/subprocess çağrısı YOK):
- Enable/credentials gating (XurlDisabled)
- Binary discovery (XurlNotInstalled)
- Compliance gate integration (BANNED phrases / money / perf-pct / unlabeled-sim)
- Char-limit enforcement
- Dry-run path (subprocess YAPILMAZ, would_execute=True)
- Shell-out happy path (subprocess mocked, response parsed)
- Shell-out failure (non-zero exit, stderr captured)
- Thread validation (her gövde ayrı validate)
- Credential masking + log sanitization
- Subprocess timeout (XurlSubprocessError)
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.social import xurl_client as xc  # noqa: E402


# ────────────────────────── Enable / credentials gating ──────────────────────────


def test_disabled_when_flag_false(monkeypatch):
    """X_API_ENABLED yoksa/yanlışsa client.is_active() False."""
    monkeypatch.delenv("X_API_ENABLED", raising=False)
    monkeypatch.setenv("X_API_KEY", "test")
    monkeypatch.setenv("X_API_SECRET", "test")
    monkeypatch.setenv("X_ACCESS_TOKEN", "test")
    monkeypatch.setenv("X_ACCESS_SECRET", "test")
    c = xc.XurlClient()
    assert c.is_active() is False


def test_disabled_when_flag_true_but_creds_missing(monkeypatch):
    """Flag true ama credentials eksik → hâlâ disabled."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.delenv("X_API_KEY", raising=False)
    monkeypatch.setenv("X_API_SECRET", "test")
    monkeypatch.setenv("X_ACCESS_TOKEN", "test")
    monkeypatch.setenv("X_ACCESS_SECRET", "test")
    c = xc.XurlClient()
    assert c.is_active() is False


def test_active_when_flag_true_and_all_creds_present(monkeypatch):
    """Flag true + 4 creds mevcut → active."""
    monkeypatch.setenv("X_API_ENABLED", "yes")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient()
    assert c.is_active() is True


def test_post_raises_when_disabled(monkeypatch):
    """Disabled client.post → XurlDisabled (caller no-op)."""
    monkeypatch.delenv("X_API_ENABLED", raising=False)
    c = xc.XurlClient()
    with pytest.raises(xc.XurlDisabled):
        c.post("hello world")


def test_mask_credential_short():
    """Kısa credential → tamamen ***."""
    assert xc._mask_credential("ab") == "***"
    assert xc._mask_credential("") == ""


def test_mask_credential_long():
    """Uzun credential → son 4 char görünür."""
    assert xc._mask_credential("abcdef1234567890") == "***7890"
    # 'sk-9KjVniYJzpV84RSvoGNzozHWTTpKxqYCQjp4kVxpAUKY63kQGxHLYuApekVXj3je1sEgmvgDPF6qBzC3OmK6xOnUxoz0'
    # → son 4: 'xoz0' → '***xoz0'
    assert xc._mask_credential("sk-9Kj...3OmK6xOnUxoz0") == "***xoz0"


# ────────────────────────── Binary discovery ──────────────────────────


@pytest.fixture(autouse=True)
def reset_bin_path_cache():
    """Her test'te binary cache reset — birbirini kirletmesin."""
    xc._BIN_PATH_CACHE = None
    yield
    xc._BIN_PATH_CACHE = None


def test_binary_not_installed_raises(monkeypatch):
    """Binary PATH'te yok + XURL_BIN_PATH unset → XurlNotInstalled.

    Not: `_binary_path()` None döner; exception `_run_xurl()` içinde raise edilir.
    Burada `_run_xurl()` üzerinden test ediyoruz (caller path).
    """
    monkeypatch.delenv("XURL_BIN_PATH", raising=False)
    fake_shutil = type("FakeShutil", (), {"which": staticmethod(lambda _: None)})()
    monkeypatch.setattr(xc, "shutil", fake_shutil)

    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient()
    # Active ama binary yok → dry_run False ise _run_xurl raise eder
    with pytest.raises(xc.XurlNotInstalled) as exc:
        c.post("test post", dry_run=False)
    assert xc.RUNBOOK_URL in str(exc.value)


def test_binary_found_via_env(monkeypatch, tmp_path):
    """XURL_BIN_PATH set ve executable → döner."""
    fake_bin = tmp_path / "xurl"
    fake_bin.write_text("#!/bin/sh\necho fake")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("XURL_BIN_PATH", str(fake_bin))
    monkeypatch.setattr(xc, "_BIN_PATH_CACHE", None)
    result = xc._binary_path()
    assert result == str(fake_bin)


# ────────────────────────── Compliance gate ──────────────────────────


def test_post_compliance_violation(monkeypatch):
    """Banned phrase içeren post → XurlComplianceViolation."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient()
    # "Garantili getiri" Türkçe banned phrase (CMP-3 list)
    with pytest.raises(xc.XurlComplianceViolation) as exc:
        c.post("Bu strateji garantili getiri vaat ediyor.")
    assert "banned_phrase" in str(exc.value)


def test_post_english_banned_phrase(monkeypatch):
    """EN banned phrase → XurlComplianceViolation."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient()
    with pytest.raises(xc.XurlComplianceViolation) as exc:
        c.post("guaranteed profit with our SMC strategy")
    assert "banned_phrase" in str(exc.value)


def test_post_text_too_long(monkeypatch):
    """280 char'dan uzun post → XurlComplianceViolation."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient(char_limit=50)
    with pytest.raises(xc.XurlComplianceViolation) as exc:
        c.post("a" * 100)
    assert "text_too_long" in str(exc.value)


def test_post_empty_text(monkeypatch):
    """Boş post → XurlComplianceViolation (empty_text)."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient()
    with pytest.raises(xc.XurlComplianceViolation) as exc:
        c.post("   ")
    assert "empty_text" in str(exc.value)


# ────────────────────────── Dry-run path ──────────────────────────


def test_post_dry_run_no_subprocess(monkeypatch):
    """dry_run=True → subprocess YAPILMAZ, would_execute=True."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient(dry_run=True)
    # subprocess.run çağrılırsa patlar — patch'le ve assert et
    with patch.object(xc.subprocess, "run") as mock_run:
        resp = c.post("clean post")
        mock_run.assert_not_called()
    assert resp.ok
    assert resp.dry_run
    assert resp.would_execute


# ────────────────────────── Shell-out happy / sad path ──────────────────────────


def _fake_proc(returncode=0, stdout="", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def test_post_shellout_success(monkeypatch):
    """Real call: xurl exit 0 + stdout'ta post ID → ok=True, post_id döner."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    monkeypatch.setattr(xc, "_BIN_PATH_CACHE", "/usr/local/bin/xurl")
    c = xc.XurlClient()
    proc = _fake_proc(
        returncode=0,
        stdout="Tweet posted: id=1234567890123456789 url=https://x.com/efloud/status/1234567890123456789",
    )
    with patch.object(xc.subprocess, "run", return_value=proc) as mock_run:
        resp = c.post("clean post about SMC concepts")
    assert resp.ok
    assert resp.post_id == "1234567890123456789"
    assert "x.com/efloud/status" in (resp.post_url or "")
    assert mock_run.called


def test_post_shellout_failure(monkeypatch):
    """Real call: xurl exit !=0 → ok=False + stderr captured."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    monkeypatch.setattr(xc, "_BIN_PATH_CACHE", "/usr/local/bin/xurl")
    c = xc.XurlClient()
    proc = _fake_proc(returncode=1, stderr="auth failed: token expired")
    with patch.object(xc.subprocess, "run", return_value=proc):
        resp = c.post("clean post")
    assert resp.ok is False
    assert resp.exit_code == 1
    assert "auth failed" in resp.stderr


def test_post_shellout_timeout(monkeypatch):
    """subprocess.TimeoutExpired → XurlSubprocessError."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    monkeypatch.setattr(xc, "_BIN_PATH_CACHE", "/usr/local/bin/xurl")
    c = xc.XurlClient(subprocess_timeout=2.0)
    with patch.object(xc.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd=["xurl"], timeout=2.0)):
        with pytest.raises(xc.XurlSubprocessError):
            c.post("clean post")


# ────────────────────────── Thread ──────────────────────────


def test_thread_compliance_propagates_index(monkeypatch):
    """Thread'de 2. post banned phrase → XurlComplianceViolation with [1] index."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient()
    with pytest.raises(xc.XurlComplianceViolation) as exc:
        c.thread(["clean first post about SMC concepts", "ikinci: garantili getiri"])
    assert "thread[1]" in str(exc.value)


def test_thread_dry_run(monkeypatch):
    """thread dry_run=True → subprocess YOK, would_execute=True."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient(dry_run=True)
    with patch.object(xc.subprocess, "run") as mock_run:
        resp = c.thread(["post 1", "post 2"])
        mock_run.assert_not_called()
    assert resp.dry_run
    assert resp.would_execute


def test_thread_empty(monkeypatch):
    """Empty thread list → XurlComplianceViolation."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    c = xc.XurlClient()
    with pytest.raises(xc.XurlComplianceViolation) as exc:
        c.thread([])
    assert "empty_thread" in str(exc.value)


# ────────────────────────── Log sanitization ──────────────────────────


def test_sanitize_for_log_redacts_credentials():
    """Log'da credential geçen argüman maskelenir.

    Regex `X_API_KEY=...` / `--api-key ...` style credential env-passing'i maskeler.
    Tek başına token (40+ char) için regex `[A-Za-z0-9_-]{40,}` ile match eder.
    """
    # Case 1: env-passing pattern
    raw = "xurl post --X_API_KEY=abcdef1234567890XYZ_abcdef1234567890XYZ --text hello"  # gitleaks:allow — test dummy, not a real key
    sanitized = xc._sanitize_for_log(raw)
    assert "abcdef1234567890XYZ_abcdef1234567890XYZ" not in sanitized
    assert "REDACTED" in sanitized
    assert "hello" in sanitized  # text maskelenmedi

    # Case 2: standalone long token (≥40 char)
    long_token = "a" * 50
    sanitized2 = xc._sanitize_for_log(long_token)
    assert long_token not in sanitized2
    assert "REDACTED" in sanitized2


def test_credentials_masked_property(monkeypatch):
    """Client.credentials_masked() → son 4 char görünür."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "abcdef1234567890XYZ")
    monkeypatch.setenv("X_API_SECRET", "shhhh-secret-value-9999")
    monkeypatch.setenv("X_ACCESS_TOKEN", "AT-zzzz-9999")
    monkeypatch.setenv("X_ACCESS_SECRET", "AS-yyyy-1234")
    c = xc.XurlClient()
    masked = c.credentials_masked()
    assert masked["X_API_KEY"].endswith("XYZ")
    assert "abcdef" not in masked["X_API_KEY"]
    assert masked["X_ACCESS_SECRET"].endswith("1234")
    assert "AS-yyyy" not in masked["X_ACCESS_SECRET"]


# ────────────────────────── CLI smoke ──────────────────────────


def test_cli_dry_run_post(monkeypatch, capsys):
    """python -m backend.social.xurl_client post --dry-run --text 'hi' exit 0 + JSON."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    exit_code = xc._cli(["post", "--text", "smoke test post", "--dry-run"])
    assert exit_code == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["dry_run"] is True
    assert parsed["would_execute"] is True


def test_cli_compliance_violation(monkeypatch, capsys):
    """CLI compliance violation → exit 1."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    monkeypatch.setenv("X_API_KEY", "k")
    monkeypatch.setenv("X_API_SECRET", "s")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_SECRET", "as")
    # "garantili getiri" TR banned phrase
    exit_code = xc._cli(["post", "--text", "bu strateji garantili getiri vaat ediyor"])
    assert exit_code == 1
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["ok"] is False


# ── B-3 (2026-07-17): post_draft unified interface ──────────────────────────

def test_post_draft_delegates_to_post(monkeypatch):
    """publishing_worker `client.post_draft(draft)` çağırır — XurlClient'ta
    bu metod yoktu → default platform 'x' AttributeError'la sonsuz retry'a
    giriyordu. post_draft, draft.body/lang'i post()'a köprülemeli."""
    monkeypatch.setenv("X_API_ENABLED", "true")
    for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        monkeypatch.setenv(k, "x")
    c = xc.XurlClient()
    assert hasattr(c, "post_draft")

    captured = {}
    def fake_post(text, *, dry_run=None, lang="all"):
        captured["text"] = text
        captured["lang"] = lang
        return "SENTINEL"
    c.post = fake_post

    class _Draft:
        body = "gm frens"
        lang = "en"
    out = c.post_draft(_Draft())
    assert out == "SENTINEL"
    assert captured["text"] == "gm frens"
    assert captured["lang"] == "en"
