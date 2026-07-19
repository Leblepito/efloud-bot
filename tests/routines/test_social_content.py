"""scripts.routines.social_content — gate, dedup, outbox, autopilot testleri."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import scripts.routines.social_content as sc


FLEET_OK = {
    "bots": {
        "scalp": {"up": True, "tf": "5m/1h/12h"},
        "mid": {"up": True, "tf": "15m/1h/4h"},
        "long": {"up": True, "tf": "1h/8h/1w"},
    },
    "open_positions": 3,
    "signals_24h": 40,
}


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """Testler gerçek HTTP/DB/dosya sistemine dokunmasın."""
    monkeypatch.chdir(tmp_path)
    for var in (
        "SOCIAL_CONTENT_ENABLED",
        "SOCIAL_AUTOPILOT",
        "DATABASE_URL",
        "EFLOUD_STATE_DIR",
        "KRONOS_OUTPUT_PATH",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EFLOUD_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(sc, "collect_fleet", lambda: FLEET_OK)
    monkeypatch.setattr(sc, "load_kronos", lambda: None)
    return tmp_path


def _outbox(tmp_path) -> Path:
    return tmp_path / sc.OUTBOX_PATH


# ── Gate: default OFF (fail-closed) ──


def test_disabled_by_default_is_noop(isolated_env):
    result = sc.main()
    assert result.ok is True
    assert result.breaches == []
    assert not _outbox(isolated_env).exists()


# ── Enabled + DB'siz → outbox, pending_review ──


def test_enabled_writes_outbox_pending(isolated_env, monkeypatch):
    monkeypatch.setenv("SOCIAL_CONTENT_ENABLED", "1")
    result = sc.main()
    assert result.ok is True
    lines = _outbox(isolated_env).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # en + ru
    records = [json.loads(l) for l in lines]
    assert {r["lang"] for r in records} == {"en", "ru"}
    assert all(r["status"] == "pending_review" for r in records)
    assert any(b["severity"] == "info" for b in result.breaches)


# ── Autopilot → approved ──


def test_autopilot_writes_approved(isolated_env, monkeypatch):
    monkeypatch.setenv("SOCIAL_CONTENT_ENABLED", "1")
    monkeypatch.setenv("SOCIAL_AUTOPILOT", "1")
    sc.main()
    records = [
        json.loads(l)
        for l in _outbox(isolated_env).read_text(encoding="utf-8").strip().splitlines()
    ]
    assert all(r["status"] == "approved" for r in records)


# ── Slot dedup: aynı slotta ikinci koşu üretmez ──


def test_slot_dedup(isolated_env, monkeypatch):
    monkeypatch.setenv("SOCIAL_CONTENT_ENABLED", "1")
    sc.main()
    first = _outbox(isolated_env).read_text(encoding="utf-8")
    result2 = sc.main()
    assert result2.ok is True
    assert _outbox(isolated_env).read_text(encoding="utf-8") == first  # değişmedi


# ── Compliance drop: ihlalli draft kuyruğa girmez ──


def test_compliance_violation_dropped(isolated_env, monkeypatch):
    monkeypatch.setenv("SOCIAL_CONTENT_ENABLED", "1")

    from backend.social.generators import DraftSpec

    def bad_drafts(**kwargs):
        return [
            DraftSpec(
                body="Guaranteed profit! Deposit $500 today.",
                lang="en",
                post_type="promo",
                meta={},
            )
        ]

    import backend.social.generators as gen

    monkeypatch.setattr(gen, "build_cycle_drafts", bad_drafts)
    result = sc.main()
    assert result.ok is True
    assert not _outbox(isolated_env).exists()
    assert any(b["severity"] == "warning" for b in result.breaches)
    # Hiçbir şey yazılmadıysa slot işaretlenmemeli → sonraki tur yeniden dener.
    state = json.loads(
        (Path(os.environ["EFLOUD_STATE_DIR"]) / sc.STATE_PATH_NAME).read_text()
    ) if (Path(os.environ["EFLOUD_STATE_DIR"]) / sc.STATE_PATH_NAME).exists() else {}
    assert "last_slot_key" not in state


# ── Kronos bayatlık ──


def test_load_kronos_stale(tmp_path, monkeypatch):
    """Fixture'sız — load_kronos'un gerçek davranışı: 8h'den eski JSON → None."""
    kf = tmp_path / "kronos.json"
    kf.write_text(
        json.dumps(
            {"generated_at": "2020-01-01T00:00:00+00:00", "symbols": {"BTC": {}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KRONOS_OUTPUT_PATH", str(kf))
    assert sc.load_kronos() is None  # 2020 tarihli → bayat


def test_load_kronos_fresh(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    kf = tmp_path / "kronos.json"
    kf.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "symbols": {"BTC": {"aligned": True, "layers": {}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KRONOS_OUTPUT_PATH", str(kf))
    data = sc.load_kronos()
    assert data is not None and "BTC" in data["symbols"]


def test_runner_registration():
    """Rutin REGISTRY'ye ve CADENCES'a kayıtlı olmalı."""
    from scripts.routines.runner import CADENCES, REGISTRY

    assert "social_content" in REGISTRY
    assert CADENCES.get("social_content") == 14400
