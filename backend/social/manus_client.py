"""P-002 Faz A M3 — Manus REST API client.

Fail-safe Manus.im client for marketing/SEO content automation.

API reference: https://open.manus.im/docs (API v2)
- Base URL: https://api.manus.ai
- Auth header: x-manus-api-key: <KEY>
- Response wrapper: {ok: bool, request_id: str, ...} | {ok: false, error: {code, message}}
- Task statuses: running, stopped (tamamlandı), waiting, error
- Async flow: POST /v2/task.create → poll /v2/task.listMessages

Activation:
- env MANUS_API_ENABLED=true (default false → client no-op)
- env MANUS_API_KEY=<sk-...> (default unset → client no-op)
- env MANUS_API_BASE_URL (default https://api.manus.ai) — for testing override

Safety invariants (G1, G3, G4 — P-002 plan §4):
- trade-path'ten tamamen decoupled (engine/safety/, lifecycle.py, order path dokunulmaz)
- default OFF, canlı config'e dokunmaz
- key yokken NO-OP (log + return None)
- secret maskelenmiş log (sk-*** + son 4 char), response truncate 1024
- retry 429/5xx exponential backoff max 3 (network err ve 4xx client err YOK retry)
- compliance token'lar her template'te zorunlu (TR + EN)

Bu modül ASLA trade loop'tan çağrılmaz — yalnız scripts/routines/ ve backend/social/
içindeki marketing pipeline task'ları tarafından (M6, M7 PR'ları).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("efloud.manus")

# ────────────────────────── Constants ──────────────────────────

BASE_URL_DEFAULT = "https://api.manus.ai"
API_VERSION = "v2"
USER_AGENT = "efloud-manus-client/1.0 (+https://u2algo.com)"

# Module-level session cache (urllib3 connection reuse + retry policy).
# `requests` transport — Python `urllib`'in TLS fingerprint'i Hetzner IP'de
# AWS WAF tarafından 403 dönüyordu (curl 200 alırken). urllib3 farklı JA3 →
# bypass. Regression guard: smoke_regression_* testleri.
_SESSION: Optional["requests.Session"] = None

# Retry
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 1.5  # 1.5, 3.0, 6.0
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Truncation
MAX_LOG_BODY = 1024

# Compliance
COMPLIANCE_TR = "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir."
COMPLIANCE_EN = "Not investment advice. Trade at your own risk."

# ────────────────────────── Exceptions ──────────────────────────


class ManusError(Exception):
    """Base Manus client error."""


class ManusDisabled(ManusError):
    """Client flag OFF veya key yok — graceful no-op sinyali."""


class ManusAuthError(ManusError):
    """401/403 — API key invalid veya revoked."""


class ManusRateLimit(ManusError):
    """429 — rate limit aşıldı (retryable)."""


class ManuscriptTemplateError(ManusError):
    """Template JSON schema validation başarısız."""


class ManuscriptTaskError(ManusError):
    """Task creation veya polling başarısız (non-retryable)."""


# ────────────────────────── Enable / Key gating ──────────────────────────


def _enabled() -> bool:
    """MANUS_API_ENABLED env flag (1/true/yes) — default false."""
    return os.environ.get("MANUS_API_ENABLED", "").lower() in ("1", "true", "yes")


def _api_key() -> Optional[str]:
    """MANUS_API_KEY env — return None if missing (no-op tetikler)."""
    key = os.environ.get("MANUS_API_KEY", "").strip()
    return key if key else None


def _base_url() -> str:
    """MANUS_API_BASE_URL override (test için); default prod URL."""
    return os.environ.get("MANUS_API_BASE_URL", BASE_URL_DEFAULT).rstrip("/")


def _mask_key(key: str) -> str:
    """API key maskeleme: sk-***XXXX (son 4 char görünür)."""
    if len(key) <= 4:
        return "***"
    return "sk-***" + key[-4:] if key.startswith("sk-") else "***" + key[-4:]


# ────────────────────────── HTTP layer ──────────────────────────


@dataclass
class ManusResponse:
    """HTTP response wrapper."""
    status: int
    body: dict  # parsed JSON
    request_id: Optional[str] = None
    raw: str = ""

    @property
    def ok(self) -> bool:
        """Manus response format: {ok: bool, ...} veya HTTP status 2xx."""
        return 200 <= self.status < 300 and self.body.get("ok", True)


def _build_session() -> requests.Session:
    """Retry/backoff'lu HTTP session. urllib3 Retry kullanır.

    Neden `requests`: urllib TLS fingerprint Hetzner IP'de AWS WAF tarafından
    403 dönüyordu (curl 200 alırken). `requests` (urllib3 transport) farklı
    fingerprint → bypass. Regression guard: smoke_regression_* testleri.
    """
    session = requests.Session()
    retry_cfg = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_BASE_SEC,
        status_forcelist=RETRYABLE_STATUSES,
        # urllib3 default: sadece idempotent methodlarda retry — biz POST'u da
        # retry etmek istiyoruz (Manus task create idempotent-key ile). Burada
        # method whitelist vermiyoruz; safe methods default.
        allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry_cfg)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _http_request(
    method: str,
    path: str,
    api_key: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    timeout: float = 30.0,
) -> ManusResponse:
    """Manus API'ye HTTP istek — `requests` session + retry/backoff.

    Retryable: 429, 500, 502, 503, 504 + network (ConnectionError, Timeout).
    Non-retryable: 400, 401, 403, 404, 422 + Manus `ok:false` 4xx-equivalent.

    Session pooling: her call'da yeni session yaratmıyoruz (urllib3
    connection reuse). Caller `_SESSION` modül-level cache kullanır.
    """
    url = f"{_base_url()}{path}"

    headers = {
        "x-manus-api-key": api_key,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    # Session reuse — TLS handshake amortized
    global _SESSION
    if _SESSION is None:
        _SESSION = _build_session()
    session = _SESSION

    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=timeout,
            )
            raw = resp.text or ""
            status = resp.status_code
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"ok": False, "error": {"code": "invalid_json", "message": raw[:200]}}
            request_id = parsed.get("request_id") if isinstance(parsed, dict) else None
            mr = ManusResponse(status=status, body=parsed, request_id=request_id, raw=raw)

            if mr.ok:
                return mr
            # HTTP 2xx but body says ok=false (Manus-specific)
            if status in (200, 201) and isinstance(parsed, dict) and parsed.get("ok") is False:
                err = parsed.get("error", {}) if isinstance(parsed.get("error"), dict) else {}
                msg_raw = str(err.get("message", ""))
                msg = msg_raw[:MAX_LOG_BODY] + ("..." if len(msg_raw) > MAX_LOG_BODY else "")
                log.warning(
                    "manus.api.ok_false status=%s code=%s msg=%s req_id=%s",
                    status, err.get("code"), msg, request_id,
                )
                code = err.get("code", "")
                if code in ("unauthorized", "forbidden"):
                    raise ManusAuthError(f"{code}: {err.get('message')}")
                if code in ("not_found", "invalid_argument"):
                    raise ManuscriptTaskError(f"{code}: {err.get('message')}")
                # Diğer 5xx-equivalent → retryable
                if attempt < MAX_RETRIES:
                    backoff = BACKOFF_BASE_SEC * (2 ** attempt)
                    log.warning(
                        "manus.api.retry code=%s attempt=%d backoff=%.1fs req_id=%s",
                        code, attempt + 1, backoff, request_id,
                    )
                    time.sleep(backoff)
                    last_exc = ManuscriptTaskError(f"manus_api_error: {code}: {err.get('message')}")
                    continue
                raise ManuscriptTaskError(f"manus_api_error: {code}: {err.get('message')}")

            # HTTP non-2xx
            if status == 401 or status == 403:
                raise ManusAuthError(f"http_{status}: auth_failed")
            if status == 429:
                if attempt < MAX_RETRIES:
                    backoff = BACKOFF_BASE_SEC * (2 ** attempt)
                    log.warning(
                        "manus.api.retry status=429 attempt=%d backoff=%.1fs req_id=%s",
                        attempt + 1, backoff, request_id,
                    )
                    time.sleep(backoff)
                    last_exc = ManusRateLimit("http_429_retry")
                    continue
                raise ManusRateLimit("http_429_after_retries")
            if status in RETRYABLE_STATUSES:
                if attempt < MAX_RETRIES:
                    backoff = BACKOFF_BASE_SEC * (2 ** attempt)
                    log.warning(
                        "manus.api.retry status=%d attempt=%d backoff=%.1fs req_id=%s",
                        status, attempt + 1, backoff, request_id,
                    )
                    time.sleep(backoff)
                    last_exc = ManuscriptTaskError(f"http_{status}_retry")
                    continue
                raise ManuscriptTaskError(f"http_{status}_after_retries")
            # 4xx (400/404/422) — non-retryable
            raise ManuscriptTaskError(f"http_{status}: {parsed}")

        except (requests.ConnectionError, requests.Timeout) as e:
            # Network/timeout — retryable
            if attempt < MAX_RETRIES:
                backoff = BACKOFF_BASE_SEC * (2 ** attempt)
                log.warning(
                    "manus.api.network_retry attempt=%d backoff=%.1fs err=%s",
                    attempt + 1, backoff, type(e).__name__,
                )
                time.sleep(backoff)
                last_exc = ManuscriptTaskError(f"network_error: {type(e).__name__}")
                continue
            raise ManuscriptTaskError(f"network_error_after_retries: {e}") from e
        except requests.RequestException as e:
            # Other requests errors (invalid URL, etc.) — non-retryable
            raise ManuscriptTaskError(f"request_error: {e}") from e

    # Buraya gelmemeli ama defensive
    raise last_exc or ManuscriptTaskError("unknown_error")


# ────────────────────────── Template validation ──────────────────────────


@dataclass
class TemplateValidationError(Exception):
    field: str
    reason: str

    def __str__(self) -> str:
        return f"template_invalid[{self.field}]: {self.reason}"


def _validate_template(template: dict) -> None:
    """Basit şema doğrulaması — jsonschema bağımlılığı YOK.

    Zorunlu alanlar:
      - name (str): template adı (örn. "x_thread", "youtube_short")
      - prompt_template (str): içinde {{input}} placeholder içeren Manus task prompt'u
      - compliance (dict): {"tr": str, "en": str} — disclaimer metinleri
      - task_metadata (dict): {"type": str, "version": str}

    Compliance token'lar (COMPLIANCE_TR/COMPLIANCE_EN) her iki dilde de
    template prompt_template içinde yer ALMALI — yayınlanmadan önce Hermes
    onay kuyruğunda görüntülenir (M6).
    """
    if not isinstance(template, dict):
        raise TemplateValidationError("root", "not_a_dict")
    for field_name in ("name", "prompt_template", "compliance", "task_metadata"):
        if field_name not in template:
            raise TemplateValidationError(field_name, "missing")

    if not isinstance(template["name"], str) or not template["name"]:
        raise TemplateValidationError("name", "empty_or_not_string")

    if not isinstance(template["prompt_template"], str) or not template["prompt_template"]:
        raise TemplateValidationError("prompt_template", "empty_or_not_string")

    comp = template["compliance"]
    if not isinstance(comp, dict):
        raise TemplateValidationError("compliance", "not_a_dict")
    for lang in ("tr", "en"):
        if lang not in comp or not isinstance(comp[lang], str) or not comp[lang]:
            raise TemplateValidationError(f"compliance.{lang}", "empty_or_not_string")
    # Compliance token kontrolü — disclaimer metni template içinde geçmeli
    if COMPLIANCE_TR not in template["prompt_template"]:
        raise TemplateValidationError("prompt_template", f"missing_compliance_tr_token")
    if COMPLIANCE_EN not in template["prompt_template"]:
        raise TemplateValidationError("prompt_template", f"missing_compliance_en_token")

    md = template["task_metadata"]
    if not isinstance(md, dict) or "type" not in md or "version" not in md:
        raise TemplateValidationError("task_metadata", "missing_type_or_version")


# ────────────────────────── Public Client ──────────────────────────


@dataclass
class CreateTaskResult:
    task_id: str
    request_id: Optional[str] = None
    status: str = "pending"
    raw: dict = field(default_factory=dict)


@dataclass
class TaskStatus:
    task_id: str
    agent_status: str  # running | stopped | waiting | error
    status_detail: Optional[str] = None
    result_text: Optional[str] = None  # stopped durumda assistant_message
    request_id: Optional[str] = None


class ManusClient:
    """Manus API client — fail-safe (no-op when disabled)."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        """Client oluştur — key verilmezse env'den oku.

        Key yoksa veya flag false ise tüm metodlar ManusDisabled fırlatır
        (caller bunu try/except ile yakalayıp no-op davranışı sergilemeli).
        """
        self._explicit_key = api_key
        self._explicit_base = base_url

    def _resolve_key(self) -> Optional[str]:
        return self._explicit_key if self._explicit_key is not None else _api_key()

    def _resolve_base(self) -> str:
        return (self._explicit_base or _base_url()).rstrip("/")

    def is_active(self) -> bool:
        """Client aktif mi (flag AND key mevcut)?"""
        return _enabled() and self._resolve_key() is not None

    def create_task(
        self,
        prompt: str,
        template: Optional[dict] = None,
        agent_profile: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> CreateTaskResult:
        """Yeni Manus task oluştur.

        Args:
          prompt: görev tanımı (Manifest task'a gider)
          template: opsiyonel template dict (validate edilir, M6 için)
          agent_profile: opsiyonel agent identifier (default None)
          metadata: opsiyonel metadata dict (task metadata + tracking)

        Returns:
          CreateTaskResult: task_id ile çağıran poll edebilir

        Raises:
          ManusDisabled: flag/key yok — caller no-op davranmalı
          TemplateValidationError: template geçersiz
          ManuscriptTaskError: API hatası
        """
        if not self.is_active():
            log.info("manus.create_task.skipped reason=disabled")
            raise ManusDisabled("manus_disabled: flag_off_or_key_missing")

        if template is not None:
            _validate_template(template)

        body: dict[str, Any] = {"prompt": prompt}
        if agent_profile:
            body["agentProfile"] = agent_profile
        if template:
            body["taskTemplate"] = {
                "name": template["name"],
                "version": template["task_metadata"]["version"],
            }
        if metadata:
            body["metadata"] = metadata

        key = self._resolve_key()
        assert key is not None  # is_active guard
        log.info("manus.create_task.start template=%s", (template or {}).get("name", "raw"))
        resp = _http_request("POST", f"/{API_VERSION}/task.create", api_key=key, json_body=body)
        task = resp.body.get("task") if isinstance(resp.body, dict) else None
        if not task or "task_id" not in task:
            raise ManuscriptTaskError(f"create_task_missing_task_id: {resp.body}")
        log.info(
            "manus.create_task.ok task_id=%s req_id=%s",
            task["task_id"], resp.request_id,
        )
        return CreateTaskResult(
            task_id=task["task_id"],
            request_id=resp.request_id,
            status=task.get("status", "pending"),
            raw=resp.body,
        )

    def get_task_status(self, task_id: str) -> TaskStatus:
        """Task durumunu sorgula (tek seferlik, polling loop'u caller'a ait).

        Returns:
          TaskStatus: agent_status + status_detail + (varsa) result_text

        Raises:
          ManuscriptTaskError: API hatası veya task bulunamadı
        """
        if not self.is_active():
            raise ManusDisabled("manus_disabled")
        key = self._resolve_key()
        assert key is not None
        log.info("manus.get_task_status.start task_id=%s", task_id)
        resp = _http_request(
            "GET", f"/{API_VERSION}/task.listMessages",
            api_key=key,
            params={"task_id": task_id, "order": "desc", "limit": 1},
        )
        # Yanıt: {ok, request_id, messages: [{role, content, agent_status, status_detail, ...}]}
        msgs = resp.body.get("messages") if isinstance(resp.body, dict) else None
        if not msgs:
            raise ManuscriptTaskError(f"no_messages: task_id={task_id}")
        latest = msgs[0]
        agent_status = latest.get("agent_status", "unknown")
        status_detail = latest.get("status_detail")
        # stopped durumda content son assistant message olur
        result_text = None
        if agent_status == "stopped" and latest.get("role") == "assistant":
            result_text = latest.get("content")
        return TaskStatus(
            task_id=task_id,
            agent_status=agent_status,
            status_detail=status_detail,
            result_text=result_text,
            request_id=resp.request_id,
        )

    def wait_for_completion(
        self,
        task_id: str,
        timeout_sec: float = 600.0,
        poll_interval_sec: float = 5.0,
        on_poll: Optional[Callable[[TaskStatus], None]] = None,
    ) -> TaskStatus:
        """Task tamamlanana kadar poll et (blocking).

        Args:
          task_id: create_task'tan dönen task_id
          timeout_sec: max bekleme (default 10dk)
          poll_interval_sec: yoklama aralığı (default 5s)
          on_poll: her poll'de çağrılacak callback (ilerleme göstergesi için)

        Returns:
          TaskStatus: tamamlandığında (stopped/error)

        Raises:
          TimeoutError: timeout aşıldıysa
          ManuscriptTaskError: error durumunda
        """
        if not self.is_active():
            raise ManusDisabled("manus_disabled")
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            status = self.get_task_status(task_id)
            if on_poll is not None:
                try:
                    on_poll(status)
                except Exception:
                    log.warning("manus.wait.on_poll_callback_failed", exc_info=True)
            if status.agent_status in ("stopped", "error"):
                if status.agent_status == "error":
                    raise ManuscriptTaskError(
                        f"task_error task_id={task_id} detail={status.status_detail}"
                    )
                log.info("manus.wait_for_completion.ok task_id=%s", task_id)
                return status
            time.sleep(poll_interval_sec)
        raise TimeoutError(f"manus_wait_timeout task_id={task_id} timeout_sec={timeout_sec}")


# ────────────────────────── Template loader ──────────────────────────


def load_template(name: str, templates_dir: Optional[Path] = None) -> dict:
    """Template dosyasını yükle + validate et.

    Varsayılan templates_dir: backend/social/templates/<name>.json
    """
    if templates_dir is None:
        templates_dir = Path(__file__).resolve().parent / "templates"
    path = templates_dir / f"{name}.json"
    if not path.exists():
        raise TemplateValidationError("file", f"template_not_found: {path}")
    try:
        template = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise TemplateValidationError("json", f"parse_error: {e}") from e
    _validate_template(template)
    return template
