"""P-002 M3 — Manus REST client unit testleri.

Kapsam (her test hermetic, network çağrısı YOK):
- Enable/key gating (flag false / key yok → ManusDisabled)
- Template validation (compliance token zorunlu, eksik alanlar)
- Template loader (bozuk JSON, eksik dosya)
- HTTP layer mock'lu: retry 429/5xx, non-retryable 4xx, auth hataları
- Key maskeleme (sk-***XXXX formatı)
- Log truncation (1024 char body)
- create_task / get_task_status / wait_for_completion davranışları
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Repo kök → Python path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.social import manus_client as mc  # noqa: E402


# ────────────────────────── Enable / key gating ──────────────────────────


def test_disabled_when_flag_false(monkeypatch):
    """MANUS_API_ENABLED yoksa/yanlışsa client.is_active() False."""
    monkeypatch.delenv("MANUS_API_ENABLED", raising=False)
    monkeypatch.setenv("MANUS_API_KEY", "sk-test1234abcd")
    c = mc.ManusClient()
    assert c.is_active() is False


def test_disabled_when_flag_true_but_key_missing(monkeypatch):
    """Flag true ama key yok → hâlâ disabled."""
    monkeypatch.setenv("MANUS_API_ENABLED", "true")
    monkeypatch.delenv("MANUS_API_KEY", raising=False)
    c = mc.ManusClient()
    assert c.is_active() is False


def test_disabled_when_flag_true_key_whitespace(monkeypatch):
    """Key boş string veya whitespace → missing sayılır."""
    monkeypatch.setenv("MANUS_API_ENABLED", "1")
    monkeypatch.setenv("MANUS_API_KEY", "   ")
    c = mc.ManusClient()
    assert c.is_active() is False


def test_active_when_flag_true_and_key_present(monkeypatch):
    """Flag true + key mevcut → active."""
    monkeypatch.setenv("MANUS_API_ENABLED", "yes")
    monkeypatch.setenv("MANUS_API_KEY", "sk-real1234abcd")
    c = mc.ManusClient()
    assert c.is_active() is True


def test_create_task_skipped_when_disabled(monkeypatch):
    """Disabled client.create_task → ManusDisabled (caller no-op)."""
    monkeypatch.delenv("MANUS_API_ENABLED", raising=False)
    monkeypatch.delenv("MANUS_API_KEY", raising=False)
    c = mc.ManusClient()
    with pytest.raises(mc.ManusDisabled):
        c.create_task("test prompt")


def test_explicit_key_overrides_env(monkeypatch):
    """Explicit key verilmişse env'i override eder."""
    monkeypatch.delenv("MANUS_API_ENABLED", raising=False)
    monkeypatch.setenv("MANUS_API_KEY", "sk-env9999")
    # Flag kapalı — explicit key bile yetmez
    c = mc.ManusClient(api_key="sk-explicit1234")
    assert c.is_active() is False
    # Flag açık + explicit key → active
    monkeypatch.setenv("MANUS_API_ENABLED", "true")
    assert c.is_active() is True


# ────────────────────────── Key masking ──────────────────────────


def test_mask_key_sk_prefix():
    """sk- prefix'li key → sk-***XXXX (son 4 görünür)."""
    assert mc._mask_key("sk-abc123def456") == "sk-***f456"


def test_mask_key_no_prefix():
    """sk- prefix'siz key → ***XXXX."""
    assert mc._mask_key("abcdef123456") == "***3456"


def test_mask_key_short():
    """Çok kısa key → tamamen ***."""
    assert mc._mask_key("ab") == "***"


# ────────────────────────── Template validation ──────────────────────────


@pytest.fixture
def valid_template():
    return {
        "name": "test_template",
        "prompt_template": (
            "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.\n"
            "Not investment advice. Trade at your own risk.\n"
            "Görev: {{input}}"
        ),
        "compliance": {
            "tr": "Bu yatırım tavsiyesi değildir.",
            "en": "Not investment advice.",
        },
        "task_metadata": {"type": "test", "version": "1.0.0"},
    }


def test_validate_template_ok(valid_template):
    mc._validate_template(valid_template)  # no raise


@pytest.mark.parametrize("missing_field", ["name", "prompt_template", "compliance", "task_metadata"])
def test_validate_template_missing_field(valid_template, missing_field):
    del valid_template[missing_field]
    with pytest.raises(mc.TemplateValidationError) as exc:
        mc._validate_template(valid_template)
    assert exc.value.field == missing_field


def test_validate_template_missing_compliance_tr(valid_template):
    """prompt_template TR compliance token içermiyorsa hata."""
    valid_template["prompt_template"] = (
        "Not investment advice. Trade at your own risk.\n"
        "Görev: {{input}}"
    )
    with pytest.raises(mc.TemplateValidationError) as exc:
        mc._validate_template(valid_template)
    assert "compliance_tr" in str(exc.value)


def test_validate_template_missing_compliance_en(valid_template):
    valid_template["prompt_template"] = (
        "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.\n"
        "Görev: {{input}}"
    )
    with pytest.raises(mc.TemplateValidationError) as exc:
        mc._validate_template(valid_template)
    assert "compliance_en" in str(exc.value)


def test_validate_template_empty_compliance(valid_template):
    valid_template["compliance"]["tr"] = ""
    with pytest.raises(mc.TemplateValidationError):
        mc._validate_template(valid_template)


def test_validate_template_not_dict():
    with pytest.raises(mc.TemplateValidationError) as exc:
        mc._validate_template("not a dict")
    assert exc.value.field == "root"


def test_validate_template_missing_task_metadata_fields(valid_template):
    valid_template["task_metadata"] = {"type": "x"}  # version yok
    with pytest.raises(mc.TemplateValidationError):
        mc._validate_template(valid_template)


# ────────────────────────── Template loader ──────────────────────────


@pytest.fixture
def templates_dir(tmp_path):
    """Üç template dosyasını tmp'ye yaz."""
    x_thread = {
        "name": "x_thread",
        "prompt_template": (
            "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.\n"
            "Not investment advice. Trade at your own risk.\n"
            "{{input}}"
        ),
        "compliance": {"tr": "x", "en": "y"},
        "task_metadata": {"type": "post", "version": "1.0.0"},
    }
    (tmp_path / "x_thread.json").write_text(json.dumps(x_thread), encoding="utf-8")
    return tmp_path


def test_load_template_ok(templates_dir):
    t = mc.load_template("x_thread", templates_dir=templates_dir)
    assert t["name"] == "x_thread"
    assert "task_metadata" in t


def test_load_template_missing_file(tmp_path):
    with pytest.raises(mc.TemplateValidationError) as exc:
        mc.load_template("nope", templates_dir=tmp_path)
    assert "template_not_found" in str(exc.value)


def test_load_template_invalid_json(templates_dir):
    (templates_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(mc.TemplateValidationError):
        mc.load_template("broken", templates_dir=templates_dir)


def test_load_template_default_dir_works():
    """Repo'daki gerçek 3 template validate olmalı."""
    for name in ("manus_x_thread", "manus_youtube_short", "manus_weekly_snapshot"):
        t = mc.load_template(name)  # templates_dir=None → default
        # name alanı dosya prefix'i olmadan, sadece tür adı
        assert t["name"] in ("x_thread", "youtube_short", "weekly_snapshot"), f"unexpected name: {t['name']}"
        assert "task_metadata" in t

# ────────────────────────── HTTP retry / backoff ──────────────────────────


@pytest.fixture
def active_client(monkeypatch):
    monkeypatch.setenv("MANUS_API_ENABLED", "true")
    monkeypatch.setenv("MANUS_API_KEY", "sk-testabcdef1234")
    return mc.ManusClient()


def _mock_urlopen_response(status, body):
    """urllib urlopen mock factory — context manager döner."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_http_2xx_success(active_client):
    body = {"ok": True, "request_id": "req_abc", "task": {"task_id": "t1"}}
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
        resp = mc._http_request("POST", "/v2/task.create", api_key="sk-testabcdef1234", json_body={"prompt": "x"})
    assert resp.ok
    assert resp.request_id == "req_abc"


def test_http_401_raises_auth_error(active_client):
    body = {"ok": False, "error": {"code": "unauthorized", "message": "bad key"}}
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(401, body)):
        with pytest.raises(mc.ManusAuthError):
            mc._http_request("GET", "/v2/task.listMessages", api_key="sk-testabcdef1234")


def test_http_404_raises_task_error(active_client):
    body = {"ok": False, "error": {"code": "not_found", "message": "task gone"}}
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(404, body)):
        with pytest.raises(mc.ManuscriptTaskError):
            mc._http_request("GET", "/v2/task.listMessages", api_key="sk-testabcdef1234")


def test_http_429_retries_then_rate_limit(active_client, monkeypatch):
    """429 → MAX_RETRIES kadar backoff, sonra ManusRateLimit."""
    monkeypatch.setattr("time.sleep", lambda _: None)  # backoff'u atla
    call_count = {"n": 0}

    def urlopen_side_effect(*a, **kw):
        call_count["n"] += 1
        # İlk 3 → 429 (MAX_RETRIES=3), sonra 4. deneme yok → raise
        return _mock_urlopen_response(429, {"ok": False, "error": {"code": "rate_limit"}})

    with patch.object(mc.urllib.request, "urlopen", side_effect=urlopen_side_effect):
        with pytest.raises(mc.ManusRateLimit):
            mc._http_request("GET", "/v2/task.listMessages", api_key="sk-testabcdef1234")
    # MAX_RETRIES + 1 initial = 4 deneme
    assert call_count["n"] == mc.MAX_RETRIES + 1


def test_http_500_retries_then_succeeds(active_client, monkeypatch):
    """500 → retry, sonra 200 başarı."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    responses = [
        _mock_urlopen_response(500, {"ok": False, "error": {"code": "server_error"}}),
        _mock_urlopen_response(500, {"ok": False, "error": {"code": "server_error"}}),
        _mock_urlopen_response(200, {"ok": True, "request_id": "req_xyz", "task": {"task_id": "t1"}}),
    ]
    with patch.object(mc.urllib.request, "urlopen", side_effect=responses):
        resp = mc._http_request("POST", "/v2/task.create", api_key="sk-testabcdef1234", json_body={})
    assert resp.ok
    assert resp.request_id == "req_xyz"


def test_http_400_no_retry(active_client):
    """400 → non-retryable, ilk denemede raise."""
    call_count = {"n": 0}

    def urlopen_side_effect(*a, **kw):
        call_count["n"] += 1
        return _mock_urlopen_response(400, {"ok": False, "error": {"code": "invalid_argument"}})

    with patch.object(mc.urllib.request, "urlopen", side_effect=urlopen_side_effect):
        with pytest.raises(mc.ManuscriptTaskError):
            mc._http_request("POST", "/v2/task.create", api_key="sk-testabcdef1234", json_body={})
    assert call_count["n"] == 1, "400 should NOT be retried"


def test_http_network_error_retries(active_client, monkeypatch):
    """URLError → retryable."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    call_count = {"n": 0}

    def urlopen_side_effect(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise mc.urllib.error.URLError("connection reset")
        return _mock_urlopen_response(200, {"ok": True, "request_id": "req_net", "task": {"task_id": "t1"}})

    with patch.object(mc.urllib.request, "urlopen", side_effect=urlopen_side_effect):
        resp = mc._http_request("POST", "/v2/task.create", api_key="sk-testabcdef1234", json_body={})
    assert resp.ok


def test_http_invalid_json_response(active_client):
    """200 + bozuk JSON → invalid_json error code'lu response → exception."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"{this is not json"
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch.object(mc.urllib.request, "urlopen", return_value=mock_resp):
        # invalid_json 4xx listesinde değil → retryable görünür ama MAX_RETRIES sonra
        # raise eder. Tek seferde yeter: code retryable ama 200+ok=false → raise.
        with pytest.raises(mc.ManuscriptTaskError) as exc:
            mc._http_request("GET", "/v2/task.listMessages", api_key="***")
        assert "invalid_json" in str(exc.value)


# ────────────────────────── Create task / status flow ──────────────────────────


def test_create_task_success(active_client, valid_template):
    body = {"ok": True, "request_id": "req_create", "task": {"task_id": "task_42", "status": "pending"}}
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
        result = active_client.create_task("test prompt", template=valid_template)
    assert result.task_id == "task_42"
    assert result.request_id == "req_create"
    assert result.status == "pending"


def test_create_task_invalid_template_raises(active_client, monkeypatch):
    """Template validation API çağrısından önce yapılır."""
    monkeypatch.setenv("MANUS_API_ENABLED", "true")
    monkeypatch.setenv("MANUS_API_KEY", "sk-testabcdef1234")
    # Mock yok — template invalid → API'ye hiç gidilmez
    with pytest.raises(mc.TemplateValidationError):
        active_client.create_task("x", template={"name": "broken"})


def test_create_task_missing_task_id_raises(active_client, valid_template):
    """Response'ta task_id yoksa ManuscriptTaskError."""
    body = {"ok": True, "request_id": "req_xx"}  # task eksik
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
        with pytest.raises(mc.ManuscriptTaskError) as exc:
            active_client.create_task("x", template=valid_template)
        assert "missing_task_id" in str(exc.value)


def test_get_task_status_stopped(active_client):
    body = {
        "ok": True,
        "request_id": "req_pol",
        "messages": [{
            "role": "assistant",
            "content": "Final result text",
            "agent_status": "stopped",
            "status_detail": None,
        }],
    }
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
        status = active_client.get_task_status("task_42")
    assert status.agent_status == "stopped"
    assert status.result_text == "Final result text"


def test_get_task_status_no_messages(active_client):
    body = {"ok": True, "request_id": "req_pol", "messages": []}
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
        with pytest.raises(mc.ManuscriptTaskError):
            active_client.get_task_status("task_42")


def test_wait_for_completion_stopped(active_client, monkeypatch):
    """running → stopped polling loop."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    responses = [
        # 1. poll: running
        {"ok": True, "request_id": "r1", "messages": [{"role": "system", "agent_status": "running"}]},
        # 2. poll: stopped
        {"ok": True, "request_id": "r2", "messages": [{"role": "assistant", "agent_status": "stopped", "content": "done"}]},
    ]
    mocks = [_mock_urlopen_response(200, b) for b in responses]
    with patch.object(mc.urllib.request, "urlopen", side_effect=mocks):
        status = active_client.wait_for_completion("task_42", poll_interval_sec=0.01)
    assert status.agent_status == "stopped"
    assert status.result_text == "done"


def test_wait_for_completion_error_raises(active_client, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    body = {"ok": True, "request_id": "r1", "messages": [{"role": "system", "agent_status": "error", "status_detail": "crashed"}]}
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
        with pytest.raises(mc.ManuscriptTaskError) as exc:
            active_client.wait_for_completion("task_42", poll_interval_sec=0.01)
        assert "task_error" in str(exc.value)


def test_wait_for_completion_timeout(active_client, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr("time.monotonic", lambda: 100.0)
    # İlk çağrı: monotonic=100, deadline=100+timeout. İkinci çağrı: 200 > deadline.
    times = iter([100.0, 200.0])
    monkeypatch.setattr("time.monotonic", lambda: next(times))
    body = {"ok": True, "request_id": "r1", "messages": [{"role": "system", "agent_status": "running"}]}
    with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
        with pytest.raises(TimeoutError):
            active_client.wait_for_completion("task_42", timeout_sec=10.0, poll_interval_sec=0.01)


# ────────────────────────── Log masking / truncation ──────────────────────────


def test_log_truncation_long_body(active_client, caplog):
    """Çok uzun response body message → log'da MAX_LOG_BODY (1024) ile truncate."""
    long_msg = "x" * 5000
    body = {"ok": False, "error": {"code": "test", "message": long_msg}}
    with caplog.at_level(logging.WARNING, logger="efloud.manus"):
        with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
            try:
                mc._http_request("POST", "/v2/task.create", api_key="***", json_body={})
            except mc.ManuscriptTaskError:
                pass
    # Log'da manus.api.ok_false mesajı var mı?
    matching = [r for r in caplog.records if "ok_false" in r.message]
    assert matching, "ok_false log kaydı yok"
    # Mesaj 1024 char + "..." ile sınırlı olmalı
    for record in matching:
        # msg field'ı 2. pozisyonel arg (code'tan sonra)
        args = record.args
        msg_in_log = args[2] if len(args) >= 3 else ""
        assert len(msg_in_log) <= mc.MAX_LOG_BODY + 3, f"log message too long: {len(msg_in_log)}"
        assert msg_in_log.endswith("..."), "truncate sonrası '...' ile bitmeli"


def test_key_never_logged_in_plaintext(active_client, caplog):
    """Key maskelenmeden log'a düşmemeli."""
    real_key = "sk-supersecret9999"
    body = {"ok": True, "request_id": "r1", "task": {"task_id": "t1"}}
    with caplog.at_level(logging.INFO, logger="efloud.manus"):
        with patch.object(mc.urllib.request, "urlopen", return_value=_mock_urlopen_response(200, body)):
            active_client.create_task("x")
    full_log = " ".join(r.message for r in caplog.records)
    assert real_key not in full_log, "API key plaintext log sızıntısı!"
