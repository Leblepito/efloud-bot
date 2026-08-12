"""backend/tests ortak fixture'ları."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_auth_rate_limit():
    """Login rate-limit state'i module-level dict'te yaşar; test dosyaları
    arası sızıntı 429 kirliliği yaratıyordu (test_api_smoke →
    test_api_bot_control sıralamasında _login_attempts dolu kalıyordu)."""
    from backend import auth

    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()
