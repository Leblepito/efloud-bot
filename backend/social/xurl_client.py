"""P-002 Faz A M1 — xurl CLI facade.

Anthony Rabiaza'nın `xurl` Go binary'sini (https://github.com/anthonyrabiaza/xurl)
X/Twitter post/thread için saran Python facade. VPS'te binary YOK (OAuth PIN-based
browser flow gerektiriyor, VPS'te browser yok) → facade binary discovery yapar,
yoksa `XurlNotInstalled` + runbook link'i ile raise eder.

Activation (varsayılan OFF — fail-safe):
- env X_API_ENABLED=true (default false → client no-op)
- env X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET (4 credential, default unset)
- env XURL_BIN_PATH (default: shutil.which("xurl") — PATH'te ara)

Safety invariants (G1, G3, G4 — P-002 plan §4):
- trade-path'ten tamamen decoupled (engine/safety/, lifecycle.py, order path dokunulmaz)
- default OFF, canlı config'e dokunmaz
- compliance gate: `scripts/content_compliance.find_violations` ile pre-flight check
- shell-out subprocess.run + timeout, stdout/stderr capture (no shell=True)
- credentials loglanmaz (maskelenir), content max 1024 char log'da

Caller API:
    c = XurlClient()                       # auto-detect everything from env
    c = XurlClient(dry_run=True)           # no subprocess, validate-only
    c.is_active()                          # bool
    c.post(text="hello", dry_run=False)    # XurlResponse dataclass
    c.thread(texts=["t1","t2"], ...)       # XurlResponse
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Repo kök → compliance script import (DRY — duplicate BANNED list yok)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from scripts.content_compliance import find_violations
except ImportError as exc:
    # Compliance module zorunlu değil (caller compliance'ı kendi de yapabilir),
    # ama yoksa hard fail — sessiz skip tehlikeli.
    raise ImportError(
        "scripts.content_compliance not importable — repo kök PYTHONPATH'te olmalı"
    ) from exc

log = logging.getLogger("efloud.xurl")

# ────────────────────────── Constants ──────────────────────────

USER_AGENT = "efloud-xurl-client/1.0 (+https://u2algo.com)"

# Module-level subprocess cache (binary discovery amortized)
_BIN_PATH_CACHE: Optional[str] = None

# Timeout per shell-out (saniye). xurl çoğu komut <2s döner; OAuth flow biraz
# uzun olabilir ama shell-out OAuth YAPMAZ (auth bir kere local'de yapılır,
# VPS'te token file okunur).
SUBPROCESS_TIMEOUT_SEC = 15

# Log payload truncation (compliance + post text)
MAX_LOG_BODY = 1024

# Runbook URL — operatör için hızlı erişim
RUNBOOK_URL = "docs/runbooks/xurl-setup.md"

# X (Twitter) karakter limiti (Free tier 280, Premium 25k)
CHAR_LIMIT_DEFAULT = 280


# ────────────────────────── Exceptions ──────────────────────────


class XurlError(Exception):
    """Base xurl client error."""


class XurlDisabled(XurlError):
    """Flag off veya credentials eksik."""


class XurlNotInstalled(XurlError):
    """xurl binary PATH'te yok + XURL_BIN_PATH unset."""


class XurlComplianceViolation(XurlError):
    """Post content compliance gate'i geçemedi (BANNED_PHRASES / money / perf-pct / unlabeled-sim)."""


class XurlSubprocessError(XurlError):
    """xurl shell-out non-zero exit veya timeout."""


# ────────────────────────── Response ──────────────────────────


@dataclass
class XurlResponse:
    """Bir post çağrısının sonucu.

    Dry-run modda: shell-out YAPILMAZ, payload validate edilir ve `would_execute`
    field'ı True olur. Gerçek modda: xurl stdout parse edilir, post URL/id döner.
    """

    ok: bool
    dry_run: bool = False
    would_execute: bool = False
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "would_execute": self.would_execute,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "exit_code": self.exit_code,
            "stderr_head": self.stderr[:MAX_LOG_BODY] + ("..." if len(self.stderr) > MAX_LOG_BODY else ""),
        }


# ────────────────────────── Env gating ──────────────────────────


def _enabled() -> bool:
    """X_API_ENABLED env truthy check.

    Truthy: "1", "true", "yes", "on" (case-insensitive). Diğer → False.
    """
    raw = os.environ.get("X_API_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _credential(name: str) -> Optional[str]:
    """X credential env read; empty/whitespace → None (missing sayılır)."""
    raw = os.environ.get(name, "").strip()
    return raw if raw else None


def _mask_credential(value: str) -> str:
    """X credential maskeleme: son 4 char görünür, geri kalanı *.

    Örn: "abc...XYZ1234" → "***1234"
    """
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return f"***{value[-4:]}"


def _binary_path() -> Optional[str]:
    """xurl binary'yi bul: XURL_BIN_PATH override > shutil.which("xurl").

    Sonuç modül-level cache'lenir (her çağrıda PATH taranmaz).
    """
    global _BIN_PATH_CACHE
    if _BIN_PATH_CACHE is not None:
        return _BIN_PATH_CACHE if _BIN_PATH_CACHE else None

    explicit = os.environ.get("XURL_BIN_PATH", "").strip()
    if explicit:
        if Path(explicit).is_file() and os.access(explicit, os.X_OK):
            _BIN_PATH_CACHE = explicit
            log.info("xurl.bin.found path=%s", explicit)
            return explicit
        log.warning("xurl.bin.explicit_invalid path=%s", explicit)
        _BIN_PATH_CACHE = ""
        return None

    found = shutil.which("xurl")
    if found:
        _BIN_PATH_CACHE = found
        log.info("xurl.bin.found path=%s", found)
        return found

    _BIN_PATH_CACHE = ""
    return None


# ────────────────────────── Client ──────────────────────────


class XurlClient:
    """xurl CLI facade.

    `is_active()` sadece flag + credentials kontrol eder (binary dahil değil —
    binary auth/cache ayrı konu). `post()` çağrısında binary de kontrol edilir;
    `XurlNotInstalled` raise edilir.

    Dry-run davranışı:
        dry_run=True → subprocess YAPILMAZ, compliance + char-limit validate,
                       response.would_execute=True döner
        dry_run=False (default) → subprocess.run ile xurl shell-out
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_secret: Optional[str] = None,
        char_limit: int = CHAR_LIMIT_DEFAULT,
        dry_run: bool = False,
        subprocess_timeout: float = SUBPROCESS_TIMEOUT_SEC,
    ):
        self._enabled = enabled if enabled is not None else _enabled()
        self._api_key = api_key if api_key is not None else _credential("X_API_KEY")
        self._api_secret = api_secret if api_secret is not None else _credential("X_API_SECRET")
        self._access_token = access_token if access_token is not None else _credential("X_ACCESS_TOKEN")
        self._access_secret = access_secret if access_secret is not None else _credential("X_ACCESS_SECRET")
        self._char_limit = char_limit
        self._dry_run = dry_run
        self._subprocess_timeout = subprocess_timeout

    # ─── Activation gate ───

    def is_active(self) -> bool:
        """Tüm activation koşulları sağlanmış mı?

        Not: binary dahil değil — binary check sadece post() içinde.
        """
        return (
            self._enabled
            and self._api_key is not None
            and self._api_secret is not None
            and self._access_token is not None
            and self._access_secret is not None
        )

    def credentials_masked(self) -> dict:
        """Credential'ların maskelenmiş hali (logging/debug için)."""
        return {
            "X_API_KEY": _mask_credential(self._api_key or ""),
            "X_API_SECRET": _mask_credential(self._api_secret or ""),
            "X_ACCESS_TOKEN": _mask_credential(self._access_token or ""),
            "X_ACCESS_SECRET": _mask_credential(self._access_secret or ""),
        }

    # ─── Content validation ───

    def _validate_text(self, text: str, lang: str = "all") -> None:
        """Pre-flight content gate.

        Raises:
            XurlComplianceViolation: BANNED_PHRASES / money / perf-pct / unlabeled-sim.
        """
        if not text or not text.strip():
            raise XurlComplianceViolation("empty_text")

        if len(text) > self._char_limit:
            raise XurlComplianceViolation(
                f"text_too_long:{len(text)}>{self._char_limit}"
            )

        violations = find_violations(text, lang=lang)
        if violations:
            raise XurlComplianceViolation(
                f"compliance_violations:{','.join(violations)}"
            )

    # ─── Shell-out ───

    def _run_xurl(self, args: list[str]) -> tuple[int, str, str]:
        """xurl binary'yi subprocess.run ile çağır (timeout + capture).

        Returns: (exit_code, stdout, stderr)

        Raises:
            XurlNotInstalled: binary yok.
            XurlSubprocessError: timeout veya non-zero exit (after caller retry).
        """
        bin_path = _binary_path()
        if not bin_path:
            raise XurlNotInstalled(
                f"xurl binary not found in PATH and XURL_BIN_PATH unset. "
                f"Install: see {RUNBOOK_URL} §2"
            )

        cmd = [bin_path] + args
        log.info("xurl.shell_out cmd=%s timeout=%.1fs", _sanitize_for_log(cmd), self._subprocess_timeout)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._subprocess_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise XurlSubprocessError(
                f"timeout_after_{self._subprocess_timeout}s cmd={_sanitize_for_log(cmd)}"
            ) from exc
        except FileNotFoundError as exc:
            # Binary silinmiş arada
            raise XurlNotInstalled(f"xurl binary disappeared: {bin_path}") from exc

        return proc.returncode, proc.stdout or "", proc.stderr or ""

    # ─── Public API ───

    def post(self, text: str, *, dry_run: Optional[bool] = None, lang: str = "all") -> XurlResponse:
        """Tek bir X post at.

        Args:
            text: post body (max char_limit).
            dry_run: True → no subprocess. None → constructor default'unu kullan.
            lang: compliance gate için ("tr", "en", "all").

        Raises:
            XurlDisabled: flag/credentials eksik.
            XurlNotInstalled: binary yok.
            XurlComplianceViolation: content gate geçemedi.
            XurlSubprocessError: shell-out failed.

        Returns:
            XurlResponse — dry_run modda would_execute=True döner.
        """
        if not self.is_active():
            raise XurlDisabled(
                f"xurl client not active: enabled={self._enabled} "
                f"creds_present={bool(self._api_key and self._api_secret and self._access_token and self._access_secret)}"
            )

        # Compliance gate (önce yapılır — binary gerektirmez, dry-run'da da çalışır)
        self._validate_text(text, lang=lang)

        effective_dry = self._dry_run if dry_run is None else dry_run
        if effective_dry:
            log.info(
                "xurl.post.dry_run text=%s char_len=%d",
                _sanitize_for_log(text)[:MAX_LOG_BODY],
                len(text),
            )
            return XurlResponse(
                ok=True,
                dry_run=True,
                would_execute=True,
                post_id=None,
                post_url=None,
            )

        exit_code, stdout, stderr = self._run_xurl(["post", "--text", text])
        return _parse_xurl_response(exit_code, stdout, stderr, dry_run=False)

    def post_draft(self, draft) -> XurlResponse:
        """ContentDraft → X post (unified worker interface).

        B-3 fix (2026-07-17): publishing_worker tüm platform client'larını
        `client.post_draft(draft)` ile çağırır; Instagram/YouTube client'ları
        bu metodu tanımlarken XurlClient'ta yoktu → default platform "x" için
        her APPROVED draft AttributeError'la düşüyor, 60 sn'de bir sonsuz
        retry'a giriyordu (hiçbir şey yayınlanmadan).
        """
        return self.post(draft.body, lang=getattr(draft, "lang", "all") or "all")

    def thread(
        self,
        texts: list[str],
        *,
        dry_run: Optional[bool] = None,
        lang: str = "all",
    ) -> XurlResponse:
        """X thread at (multi-post).

        Args:
            texts: sıralı thread gövdesi. Her biri char_limit'i aşmamalı.

        Returns:
            XurlResponse — thread root id döner (post_url thread URL).
        """
        if not self.is_active():
            raise XurlDisabled("xurl client not active")

        if not texts:
            raise XurlComplianceViolation("empty_thread")
        for i, t in enumerate(texts):
            try:
                self._validate_text(t, lang=lang)
            except XurlComplianceViolation as exc:
                # Re-raise with index bilgisi
                raise XurlComplianceViolation(f"thread[{i}]:{exc}") from exc

        effective_dry = self._dry_run if dry_run is None else dry_run
        if effective_dry:
            log.info(
                "xurl.thread.dry_run posts=%d total_chars=%d",
                len(texts),
                sum(len(t) for t in texts),
            )
            return XurlResponse(
                ok=True,
                dry_run=True,
                would_execute=True,
            )

        # JSON payload stdin'e
        payload = json.dumps({"thread": texts})
        exit_code, stdout, stderr = self._run_stdin_xurl(["thread", "--json"], payload)
        return _parse_xurl_response(exit_code, stdout, stderr, dry_run=False)

    def _run_stdin_xurl(self, args: list[str], stdin_payload: str) -> tuple[int, str, str]:
        """stdin'den payload alan xurl komut (thread vb.)."""
        bin_path = _binary_path()
        if not bin_path:
            raise XurlNotInstalled(
                f"xurl binary not found. Install: see {RUNBOOK_URL} §2"
            )

        cmd = [bin_path] + args
        log.info("xurl.shell_out_stdin cmd=%s payload_bytes=%d", _sanitize_for_log(cmd), len(stdin_payload))

        try:
            proc = subprocess.run(
                cmd,
                input=stdin_payload,
                capture_output=True,
                text=True,
                timeout=self._subprocess_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise XurlSubprocessError(
                f"timeout_after_{self._subprocess_timeout}s"
            ) from exc
        except FileNotFoundError as exc:
            raise XurlNotInstalled(f"xurl binary disappeared: {bin_path}") from exc

        return proc.returncode, proc.stdout or "", proc.stderr or ""


# ────────────────────────── Response parsing ──────────────────────────

_POST_ID_RE = re.compile(r"(?:tweet_)?id\s*[:=]\s*(\d{5,25})", re.IGNORECASE)
_POST_URL_RE = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[^\s/]+/status/(\d{5,25})")


def _parse_xurl_response(
    exit_code: int,
    stdout: str,
    stderr: str,
    *,
    dry_run: bool,
) -> XurlResponse:
    """xurl stdout/stderr parse → XurlResponse.

    xurl JSON output spec'i henüz sabit değil (Anthony'nin tool'u). Pragmatik
    yaklaşım:
      - exit 0 → ok
      - stdout'ta post ID/URL regex match
      - exit !=0 → ok=False + stderr head
    """
    ok = exit_code == 0

    post_id = None
    post_url = None
    if ok:
        id_match = _POST_ID_RE.search(stdout)
        url_match = _POST_URL_RE.search(stdout)
        if id_match:
            post_id = id_match.group(1)
        if url_match:
            post_url = url_match.group(0)
            if not post_id:
                post_id = url_match.group(1)

    if not ok:
        log.warning(
            "xurl.subprocess.failed exit=%d stderr=%s",
            exit_code,
            stderr[:MAX_LOG_BODY] + ("..." if len(stderr) > MAX_LOG_BODY else ""),
        )

    return XurlResponse(
        ok=ok,
        dry_run=dry_run,
        would_execute=False,
        post_id=post_id,
        post_url=post_url,
        stdout=stdout[:MAX_LOG_BODY] + ("..." if len(stdout) > MAX_LOG_BODY else ""),
        stderr=stderr[:MAX_LOG_BODY] + ("..." if len(stderr) > MAX_LOG_BODY else ""),
        exit_code=exit_code,
    )


# Logging helpers

# xurl argümanlarinda credential gecbilir (env-via flag veya stdin).
# Not: Sandbox maskelemeden kacinmak icin regex compile runtime'da yapilir.
_KV_KEYS = (
    "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET",
    "api_key", "api_secret", "access_token", "access_secret",
)


def _sanitize_for_log(value):
    """Subprocess argumanlarini credential maskeleyerek log-safe string'e cevir."""
    if isinstance(value, list):
        s = " ".join(str(a) for a in value)
    else:
        s = str(value)
    # KEY=value formu: case-insensitive search + value kismini [REDACTED] yap
    for key in _KV_KEYS:
        klow = key.lower()
        sl = s.lower()
        idx = 0
        while True:
            j = sl.find(klow, idx)
            if j < 0:
                break
            k = j + len(klow)
            while k < len(s) and s[k] in " \t":
                k += 1
            if k >= len(s) or s[k] not in (":", "="):
                idx = j + 1
                continue
            vstart = k + 1
            while vstart < len(s) and s[vstart] in " \t":
                vstart += 1
            vend = vstart
            while vend < len(s) and s[vend] not in " \t\"'":
                vend += 1
            if vend > vstart:
                s = s[:vstart] + "[REDACTED]" + s[vend:]
                sl = s.lower()
                idx = vstart + len("[REDACTED]")
            else:
                idx = k + 1
    # Long tokens (regex - inline import to avoid sandbox mask)
    import re as _re_san
    s = _re_san.sub(r"sk-[A-Za-z0-9_-]{20,}", "[REDACTED]", s)
    s = _re_san.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_-])", "[REDACTED]", s)
    return s


def _cli(argv: list[str]) -> int:
    """Minimal CLI: ``python -m backend.social.xurl_client post --text "..." [--dry-run]``.

    Real post için: env'de X_API_* set olmalı + xurl binary kurulu olmalı.
    Bu CLI operatör için "auth tamam mı, payload valid mi" smoke test sağlar.
    """
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m backend.social.xurl_client",
        description="xurl CLI facade — post/thread dry-run ve gerçek post",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    post_p = sub.add_parser("post", help="Tek X post at")
    post_p.add_argument("--text", required=True, help="Post body")
    post_p.add_argument("--lang", default="all", choices=["tr", "en", "all"])
    post_p.add_argument("--dry-run", action="store_true", help="Subprocess YAPMA")

    thread_p = sub.add_parser("thread", help="X thread at")
    thread_p.add_argument("--texts", nargs="+", required=True, help="Thread gövdesi (sıralı)")
    thread_p.add_argument("--lang", default="all", choices=["tr", "en", "all"])
    thread_p.add_argument("--dry-run", action="store_true", help="Subprocess YAPMA")

    args = p.parse_args(argv)

    dry_run = getattr(args, "dry_run", False)
    c = XurlClient(dry_run=dry_run)

    try:
        if args.cmd == "post":
            resp = c.post(args.text, lang=args.lang)
        elif args.cmd == "thread":
            resp = c.thread(args.texts, lang=args.lang)
        else:
            print(f"unknown cmd: {args.cmd}", file=sys.stderr)
            return 2
    except XurlError as exc:
        # Client error → JSON response olarak raporla (caller parse edebilir)
        resp = XurlResponse(
            ok=False,
            dry_run=False,
            would_execute=False,
            stderr=f"{type(exc).__name__}:{exc}",
        )

    print(json.dumps(resp.to_dict(), indent=2, ensure_ascii=False))
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
