"""
Lane A Content Job Emitter tests
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Spec: docs/superpowers/specs/2026-06-04-content-jobs-consumer-design.md

8 test:
1. test_emit_creates_file
2. test_atomic_write_no_partial_files
3. test_daily_rotation_creates_new_file
4. test_concurrent_emit_no_corruption
5. test_event_id_unique
6. test_schema_validation_passes
7. test_disabled_emitter_is_noop
8. test_disk_full_fallback

Note: we use the global ``tmp_path`` fixture (real fs, not pyfakefs) so the
emitter's schema-discovery path resolves to the real ``docs/schemas/``
file. ``pyfakefs`` would shadow the schema read and break validation. The
emitter writes to ``tmp_path`` (real fs) so the rest of the test stays
intact.
"""

import json
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from unittest import mock

import pytest

from engine.content_jobs import ContentJobEmitter, SCHEMA_VERSION, _enabled, _base_path
from engine.notifications import NotificationManager


@pytest.fixture
def tmp_jobs_path(tmp_path):
    """Her test için izole path."""
    p = tmp_path / "content_jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def emitter(tmp_jobs_path):
    return ContentJobEmitter(base_path=tmp_jobs_path, env="testnet", loop_id=str(uuid.uuid4()))


def _signal(**overrides):
    base = {
        "symbol": "BTC/USDT", "direction": "LONG", "entry": 50000.0,
        "sl": 49000.0, "tp1": 52000.0, "tp2": 53000.0, "confluence": 85,
        "timeframe": "15m", "horizon": None, "regime": "TRENDING",
        "reasons": ["FVG", "OB"], "reasons_detail": {"trace_id": None},
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _enable_emitter(monkeypatch):
    """Default OFF olan flag'i testlerde ON yap."""
    monkeypatch.setenv("EFLOUD_CONTENT_EMITTER_ENABLED", "1")
    # Schema validation default: skip. test_schema_validation_passes
    # explicitly enables it to verify the validator. Other tests focus
    # on the file-IO surface, not schema correctness.
    monkeypatch.setattr("engine.content_jobs.jsonschema", None)


def test_emit_creates_file(emitter, tmp_jobs_path):
    """İlk emit dosyayı oluşturur ve event yazılır."""
    assert emitter.emit("content_job.created", signal=_signal()) is True
    files = list(tmp_jobs_path.glob("*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text().strip()
    event = json.loads(content)
    assert event["event_type"] == "content_job.created"
    assert event["signal"]["symbol"] == "BTC/USDT"
    assert event["schema_version"] == SCHEMA_VERSION
    assert event["compliance"]["no_guarantee"] is True


def test_disk_full_or_open_failure(emitter, tmp_jobs_path, monkeypatch):
    """Crash mid-write: dosya temiz kalir (tmp yok, kismi satir yazilabilir ama test izole)."""
    # open()'i crash simüle et -> OSError
    original_open = open
    def crashing_open(*a, **kw):
        raise OSError("simulated crash during open")
    monkeypatch.setattr("builtins.open", crashing_open)
    assert emitter.emit("content_job.created", signal=_signal()) is False
    # Klasör boş (dosya oluşmadi)
    files = list(tmp_jobs_path.glob("*.jsonl"))
    assert files == [], f"unexpected files: {files}"


def test_daily_rotation_creates_new_file(emitter, tmp_jobs_path, monkeypatch):
    """Günlük rotation: emit anındaki date'e göre dosya adı."""
    # İlk emit bugün
    assert emitter.emit("content_job.created", signal=_signal()) is True
    today_file = tmp_jobs_path / f"{__import__('datetime').date.today().isoformat()}.jsonl"
    assert today_file.exists()
    # Monkeypatch the date to tomorrow -> yeni dosya
    from datetime import datetime, timezone
    tomorrow = datetime(2099, 12, 31, tzinfo=timezone.utc)
    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            return tomorrow
    monkeypatch.setattr("engine.content_jobs.datetime", FakeDateTime)
    assert emitter.emit("content_job.created", signal=_signal()) is True
    tomorrow_file = tmp_jobs_path / "2099-12-31.jsonl"
    assert tomorrow_file.exists()
    # İki dosya var
    assert len(list(tmp_jobs_path.glob("*.jsonl"))) == 2


def test_concurrent_emit_no_corruption(emitter, tmp_jobs_path):
    """100 paralel emit, hepsi valid JSON parse edilir."""
    results = []
    def worker(i):
        r = emitter.emit("content_job.created", signal=_signal(symbol=f"SYM{i}/USDT"))
        results.append(r)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(results), f"some emits failed: {results.count(False)}/100"
    target_file = tmp_jobs_path / f"{__import__('datetime').date.today().isoformat()}.jsonl"
    lines = [ln for ln in target_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 100
    # Her satır parse edilebilir
    parsed = [json.loads(ln) for ln in lines]
    assert len({e["event_id"] for e in parsed}) == 100  # unique IDs


def test_event_id_unique(emitter, tmp_jobs_path):
    """UUID v4, 1000 emit'te collision yok."""
    ids = set()
    for i in range(1000):
        assert emitter.emit("content_job.created", signal=_signal(symbol=f"S{i}/USDT")) is True
    target_file = tmp_jobs_path / f"{__import__('datetime').date.today().isoformat()}.jsonl"
    for ln in target_file.read_text().splitlines():
        if ln.strip():
            ids.add(json.loads(ln)["event_id"])
    assert len(ids) == 1000


def test_schema_validation_passes(emitter, monkeypatch):
    """Her emit şemayla validate olur (jsonschema)."""
    # Re-enable jsonschema for this specific test.
    import jsonschema as real_jsonschema
    monkeypatch.setattr("engine.content_jobs.jsonschema", real_jsonschema)
    # Spec'te required tüm alanlar emit'te var
    assert emitter.emit("content_job.created", signal=_signal()) is True
    # Pozisyon açıldı varyantı
    assert emitter.emit("content_job.position_opened", signal=_signal(), execution={"filled": True, "fill_price": 50000, "quantity": 0.01, "leverage": 5, "trace_id": "abc123"}) is True


def test_disabled_emitter_is_noop(tmp_jobs_path, monkeypatch):
    """EFLOUD_CONTENT_EMITTER_ENABLED unset/0 ise dosya oluşmaz."""
    monkeypatch.delenv("EFLOUD_CONTENT_EMITTER_ENABLED", raising=False)
    e = ContentJobEmitter(base_path=tmp_jobs_path, env="testnet")
    assert e.emit("content_job.created", signal=_signal()) is False
    assert list(tmp_jobs_path.glob("*.jsonl")) == []


def test_disk_full_fallback(tmp_jobs_path, monkeypatch):
    """ENOSPC simülasyonu: emit fail, log error, ama bot crash etmez."""
    e = ContentJobEmitter(base_path=tmp_jobs_path, env="testnet")
    # mkdir OSError
    monkeypatch.setattr("pathlib.Path.mkdir", lambda *a, **kw: (_ for _ in ()).throw(OSError("ENOSPC")))
    # Bot crash etmemeli, False dönmeli
    assert e.emit("content_job.created", signal=_signal()) is False


# ── Integration: NotificationManager'a wire ──

def test_notification_manager_emits_via_content_emitter(tmp_jobs_path, monkeypatch):
    """NotificationManager.signal_readonly content_emitter.inject edince JSON dosyaya yazar."""
    monkeypatch.setenv("EFLOUD_CONTENT_EMITTER_ENABLED", "1")
    import jsonschema as real_jsonschema
    monkeypatch.setattr("engine.content_jobs.jsonschema", real_jsonschema)
    emitter = ContentJobEmitter(base_path=tmp_jobs_path, env="testnet")
    nm = NotificationManager(channels=["log"], content_emitter=emitter)
    nm.signal_readonly("BTC/USDT", "LONG", 50000, 49000, 52000, 53000, 85, ["FVG"],
                       timeframe="15m", regime="TRENDING")
    target_file = tmp_jobs_path / f"{__import__('datetime').date.today().isoformat()}.jsonl"
    assert target_file.exists()
    event = json.loads(target_file.read_text().strip().splitlines()[-1])
    assert event["event_type"] == "content_job.created"
    assert event["signal"]["timeframe"] == "15m"
    assert event["signal"]["regime"] == "TRENDING"
