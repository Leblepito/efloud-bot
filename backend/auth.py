"""Single-user password auth.

Flow:
- POST /api/login with {password} → set signed cookie "efloud_session" (30 days)
- All /api/* (except /login) require valid cookie
- /ws also requires cookie (browser sends automatically on same-origin)

Implementation: itsdangerous URLSafeTimedSerializer for cookie signing.
Constant-time password comparison to prevent timing attacks.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = logging.getLogger("efloud.auth")

COOKIE_NAME = "efloud_session"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days

# Login rate limiting (in-memory, single-user → simple dict)
# Sertleştirme (2026-08-12): uvicorn --forwarded-allow-ips '*' (B-5) ile
# X-Forwarded-For spoof'lanabilir → her deneme farklı "IP" görünüp per-IP
# limitini baypas edebilir ve dict'i sınırsız büyütebilirdi. Global pencere
# tavanı + izlenen IP sayısı tavanı bu iki açığı kapatır.
_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_WINDOW = 900  # 15 min
_GLOBAL_MAX_ATTEMPTS = 25   # pencere içi TÜM IP'lerin toplam başarısız denemesi
_MAX_TRACKED_IPS = 1000     # bellek tavanı (spoof'lanmış benzersiz IP seli)


def _prune_stale_attempts(now: float) -> None:
    """Pencere dışı kayıtları hem listelerden hem dict'ten düş (bellek)."""
    for ip in list(_login_attempts):
        attempts = _login_attempts[ip]
        attempts[:] = [t for t in attempts if now - t < _LOCKOUT_WINDOW]
        if not attempts:
            del _login_attempts[ip]


def _get_serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SESSION_SECRET")
    is_dev = os.environ.get("ENV", "dev") == "dev"
    if not is_dev:
        if not secret or secret == "dev-only-secret-do-not-use-in-prod":
            raise RuntimeError("SESSION_SECRET must be set to a secure value in production mode")
    if not secret:
        # Dev fallback — production'da env zorunlu
        secret = "dev-only-secret-do-not-use-in-prod"
        log.warning("SESSION_SECRET not set — using dev fallback (UNSAFE)")
    return URLSafeTimedSerializer(secret, salt="efloud-session")


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    _prune_stale_attempts(now)
    attempts = _login_attempts.get(client_ip, [])
    if len(attempts) >= _MAX_ATTEMPTS:
        retry_in = int(_LOCKOUT_WINDOW - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {retry_in}s.",
        )
    # Global tavan: IP başına değil toplam — spoof'lanmış XFF ile her deneme
    # "yeni IP"den gelse bile brute-force pencere içinde durdurulur.
    total = sum(len(v) for v in _login_attempts.values())
    if total >= _GLOBAL_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )


def _record_failed_attempt(client_ip: str) -> None:
    _login_attempts.setdefault(client_ip, []).append(time.time())
    if len(_login_attempts) > _MAX_TRACKED_IPS:
        # En eski son-denemesi olan IP'leri at (bellek tavanı)
        overflow = len(_login_attempts) - _MAX_TRACKED_IPS
        for ip in sorted(_login_attempts, key=lambda k: _login_attempts[k][-1])[:overflow]:
            del _login_attempts[ip]


def verify_password(password: str) -> bool:
    """Constant-time comparison against DASHBOARD_PASSWORD env."""
    expected = os.environ.get("DASHBOARD_PASSWORD", "")
    if not expected:
        log.error("DASHBOARD_PASSWORD not set — login disabled")
        return False
    return hmac.compare_digest(password.encode(), expected.encode())


def issue_session_cookie(response: Response) -> None:
    serializer = _get_serializer()
    token = serializer.dumps({"v": 1, "ts": int(time.time())})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=os.environ.get("ENV", "dev") != "dev",  # HTTPS only in prod
        samesite="lax",
    )


def login(request: Request, response: Response, password: str) -> bool:
    """Returns True if login successful (cookie set), False otherwise."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    if not verify_password(password):
        _record_failed_attempt(client_ip)
        return False

    # Başarılı login geçmiş başarısız denemeleri affeder — meşru operatör
    # kilitlenmeye 1 deneme mesafede yaşamasın.
    _login_attempts.pop(client_ip, None)
    issue_session_cookie(response)
    return True


def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def is_authenticated(session_cookie: Optional[str]) -> bool:
    if not session_cookie:
        return False
    try:
        serializer = _get_serializer()
        serializer.loads(session_cookie, max_age=COOKIE_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


# FastAPI dependency
async def require_auth(
    efloud_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    authorization: Optional[str] = Header(default=None),
) -> None:
    # Cookie path (web)
    if efloud_session and is_authenticated(efloud_session):
        return
    # Bearer token path (mobile)
    if authorization and authorization.lower().startswith("bearer "):
        if validate_token(authorization[7:]):
            return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


# ── Bearer token auth (mobile) ──
# Cookie session ile AYNI serializer secret'ini paylaşır. Token = imzalı
# payload, cookie ile aynı; sadece header ile taşınır. Ayrı sır YOK.


def issue_token() -> str:
    """Mobil istemci için Bearer token üret."""
    serializer = _get_serializer()
    return serializer.dumps({"v": 1, "ts": int(time.time()), "m": 1})  # m=mobile


def validate_token(token: str) -> bool:
    try:
        serializer = _get_serializer()
        serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False
