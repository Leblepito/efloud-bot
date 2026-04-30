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

from fastapi import Cookie, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = logging.getLogger("efloud.auth")

COOKIE_NAME = "efloud_session"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days

# Login rate limiting (in-memory, single-user → simple dict)
_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_WINDOW = 900  # 15 min


def _get_serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        # Dev fallback — production'da env zorunlu
        secret = "dev-only-secret-do-not-use-in-prod"
        log.warning("SESSION_SECRET not set — using dev fallback (UNSAFE)")
    return URLSafeTimedSerializer(secret, salt="efloud-session")


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    attempts = _login_attempts.setdefault(client_ip, [])
    # Prune old attempts
    attempts[:] = [t for t in attempts if now - t < _LOCKOUT_WINDOW]
    if len(attempts) >= _MAX_ATTEMPTS:
        retry_in = int(_LOCKOUT_WINDOW - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {retry_in}s.",
        )


def _record_failed_attempt(client_ip: str) -> None:
    _login_attempts.setdefault(client_ip, []).append(time.time())


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
async def require_auth(efloud_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)) -> None:
    if not is_authenticated(efloud_session):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
