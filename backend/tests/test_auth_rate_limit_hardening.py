"""Login rate-limit sertleştirmesi (2026-08-12 audit).

Tehdit modeli: uvicorn `--forwarded-allow-ips '*'` ile koşar (B-5, Caddy
dinamik IP). X-Forwarded-For spoof'lanabilir → saldırgan her denemede farklı
"IP" görünerek (1) per-IP limitini baypas eder, (2) _login_attempts dict'ini
sınırsız büyütür. Savunma: global pencere tavanı + izlenen IP sayısı tavanı.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend import auth


def _fill(ip: str, n: int) -> None:
    for _ in range(n):
        auth._record_failed_attempt(ip)


def test_per_ip_limit_still_blocks():
    _fill("10.0.0.1", auth._MAX_ATTEMPTS)
    with pytest.raises(HTTPException) as e:
        auth._check_rate_limit("10.0.0.1")
    assert e.value.status_code == 429


def test_global_cap_blocks_spoofed_unique_ips():
    """Her denemede farklı IP görünen saldırgan per-IP limitine hiç takılmaz;
    global tavan yine de 429 üretmeli."""
    for i in range(auth._GLOBAL_MAX_ATTEMPTS):
        _fill(f"192.0.2.{i}", 1)
    with pytest.raises(HTTPException) as e:
        auth._check_rate_limit("198.51.100.99")  # taze, hiç denememiş IP
    assert e.value.status_code == 429


def test_tracked_ip_count_is_bounded():
    for i in range(auth._MAX_TRACKED_IPS + 500):
        auth._record_failed_attempt(f"203.0.{i // 256}.{i % 256}")
    assert len(auth._login_attempts) <= auth._MAX_TRACKED_IPS


def test_stale_attempts_fully_pruned(monkeypatch):
    """Pencere dışı kayıtlar hem sayaçtan hem dict'ten düşmeli (bellek)."""
    t = {"now": 1_000_000.0}
    monkeypatch.setattr(auth.time, "time", lambda: t["now"])
    _fill("10.9.9.9", auth._MAX_ATTEMPTS)
    t["now"] += auth._LOCKOUT_WINDOW + 1
    auth._check_rate_limit("10.9.9.9")  # raise etmemeli
    assert "10.9.9.9" not in auth._login_attempts


def test_env_unset_is_treated_as_production(monkeypatch):
    """ENV hiç set edilmemişse dev fallback secret'ına DÜŞMEMELİ (fail-closed).
    issue_session_cookie'nin Secure flag'i unset'i zaten prod sayıyordu;
    serializer dev sayıyordu — bilinen secret'la imza = oturum sahteciliği."""
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        auth._get_serializer()


def test_successful_login_clears_failed_counter(monkeypatch):
    """Meşru operatör yanlış şifre denemelerinden sonra doğru girince sayaç
    sıfırlanmalı — yoksa kilitlenmeye 1 deneme mesafede yaşar."""
    monkeypatch.setenv("DASHBOARD_PASSWORD", "correct-pw-123456")
    monkeypatch.setenv("SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("ENV", "dev")

    class _Client:
        host = "10.1.2.3"

    class _Req:
        client = _Client()

    class _Resp:
        def set_cookie(self, **kw):
            pass

    _fill("10.1.2.3", auth._MAX_ATTEMPTS - 1)
    assert auth.login(_Req(), _Resp(), "correct-pw-123456") is True
    assert "10.1.2.3" not in auth._login_attempts
