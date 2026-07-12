"""RateLimiter guard hijyeni (2026-07-11 review, ertelenen kalem).

1) Boş token listesi + block=True + kapasite üstü weight → self.tokens[0]
   IndexError (canlı loop crash).
2) weight > max hiçbir bekleme ile SIĞAMAZ — eski kod block=True'da
   IndexError/sonsuz bekleme, block=False'ta sonsuza dek False üretiyordu.
   Fix: fail-closed açık ValueError (repo'daki tek gerçek çağrı weight=4,
   max=1000 — canlı yol etkilenmez).
"""
from __future__ import annotations

import pytest

from engine.safety.guard import RateLimiter


def test_oversized_weight_raises_not_indexerror():
    rl = RateLimiter(max_per_minute=10)
    with pytest.raises(ValueError):
        rl.acquire(weight=25, block=True)   # eski kod: IndexError


def test_oversized_weight_raises_nonblocking_too():
    rl = RateLimiter(max_per_minute=10)
    with pytest.raises(ValueError):
        rl.acquire(weight=11, block=False)


def test_exact_capacity_weight_admitted():
    rl = RateLimiter(max_per_minute=10)
    assert rl.acquire(weight=10, block=False) is True
    # Bucket doldu — sıradaki non-blocking istek reddedilir (mevcut semantik)
    assert rl.acquire(weight=1, block=False) is False


def test_normal_flow_unchanged():
    rl = RateLimiter(max_per_minute=10)
    for _ in range(10):
        assert rl.acquire(weight=1, block=False) is True
    assert rl.acquire(weight=1, block=False) is False
