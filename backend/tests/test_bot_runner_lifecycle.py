"""BotRunner lifecycle tests — idempotency, error capture, restart semantics.

Bu testler runner instance'ını izole tutar (module singleton'a dokunmaz),
gerçek bir BotRunner() yaratır ve config-not-found path'iyle non-startup
davranışlarını doğrular.
"""
from __future__ import annotations

import pytest

from backend.bot_runner import BotRunner


@pytest.fixture
def fresh_runner(monkeypatch):
    """Yeni BotRunner instance, geçersiz config path ile."""
    monkeypatch.setenv("EFLOUD_CONFIG_PATH", "configs/__nonexistent__.yaml")
    return BotRunner()


@pytest.mark.asyncio
async def test_start_with_missing_config_records_last_error(fresh_runner):
    """Config bulunamadığında start() last_error string'ini doldurmalı."""
    await fresh_runner.start()
    assert fresh_runner.running is False
    assert fresh_runner.last_error is not None
    assert "config" in fresh_runner.last_error.lower()


@pytest.mark.asyncio
async def test_start_is_idempotent_when_already_running(fresh_runner):
    """Bot zaten running iken start() çağrılırsa hiçbir state değişmemeli."""
    fresh_runner.running = True
    fresh_runner.cycle_count = 42
    await fresh_runner.start()
    # Hala "running" — start ikinci kez init yapmadı
    assert fresh_runner.running is True
    assert fresh_runner.cycle_count == 42  # değişmedi


@pytest.mark.asyncio
async def test_stop_then_start_resets_stopped_flag(fresh_runner):
    """stop() sonrası start() çağrılınca stopped flag false olmalı."""
    fresh_runner.stopped = True
    fresh_runner.running = False
    # start() config-not-found path'ten dönecek ama stopped reset'lenmeli
    await fresh_runner.start()
    assert fresh_runner.stopped is False


@pytest.mark.asyncio
async def test_idempotent_start_preserves_last_error(fresh_runner):
    """Bot zaten running iken start() çağrılırsa erken dönmeli, last_error'a dokunmamalı."""
    fresh_runner.last_error = "previous error"
    fresh_runner.running = True
    fresh_runner.stopped = False
    await fresh_runner.start()
    # Idempotent path last_error'a dokunmamalı (early return)
    assert fresh_runner.last_error == "previous error"
    assert fresh_runner.running is True


@pytest.mark.asyncio
async def test_start_clears_previous_last_error_when_attempting(fresh_runner):
    """Bot stopped iken start() çağrılırsa eski last_error temizlenmeli (yeni deneme)."""
    fresh_runner.last_error = "old failure"
    fresh_runner.running = False
    fresh_runner.stopped = True
    await fresh_runner.start()
    # Yeni deneme yapıldı → eski hata temizlenip yeni durum yazıldı
    # (config-not-found olduğu için yeni last_error config ile ilgili olmalı)
    assert fresh_runner.last_error != "old failure"
    assert "config" in (fresh_runner.last_error or "").lower()


@pytest.mark.asyncio
async def test_status_snapshot_includes_last_error(fresh_runner):
    """status_snapshot() last_error field'ı taşımalı."""
    fresh_runner.last_error = "something broke"
    snap = fresh_runner.status_snapshot()
    assert snap.get("last_error") == "something broke"
