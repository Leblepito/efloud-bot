"""OverseerDedup — thin wrapper over ops.alerter.dedup.Dedup that adds
overseer-default DB path + default window. The underlying SQLite dedup
semantics (should_fire) are inherited unchanged so callers get a single
behaviour-compatible API across alerter + overseer."""
from __future__ import annotations


def test_overseer_dedup_uses_overseer_default_path(tmp_path, monkeypatch):
    """No env, no arg → DEFAULT_DB_PATH wins (overseer ships a sensible default)."""
    # Clear the env so default-resolution path runs; redirect the default to
    # tmp_path so the real /app/state/... is never touched on the dev box.
    monkeypatch.delenv("EFLOUD_OVERSEER_DEDUP_DB", raising=False)
    default_target = tmp_path / "overseer_dedup_default.sqlite"
    monkeypatch.setattr(
        "ops.overseer.dedup.DEFAULT_DB_PATH", str(default_target)
    )

    from ops.overseer.dedup import OverseerDedup
    d = OverseerDedup()
    assert d.db_path == str(default_target)
    assert default_target.exists()


def test_overseer_dedup_env_override(tmp_path, monkeypatch):
    """EFLOUD_OVERSEER_DEDUP_DB env beats DEFAULT_DB_PATH — supports ops overrides."""
    target = tmp_path / "from_env.sqlite"
    monkeypatch.setenv("EFLOUD_OVERSEER_DEDUP_DB", str(target))

    from ops.overseer.dedup import OverseerDedup
    d = OverseerDedup()
    assert d.db_path == str(target)
    assert target.exists()


def test_overseer_dedup_window_default_30min(tmp_path, monkeypatch):
    """Default window 1800s (30 min) — Phase A2 reviewer recommendation."""
    monkeypatch.setenv("EFLOUD_OVERSEER_DEDUP_DB", str(tmp_path / "x.sqlite"))
    from ops.overseer.dedup import OverseerDedup, DEFAULT_WINDOW_SECONDS
    assert DEFAULT_WINDOW_SECONDS == 1800
    d = OverseerDedup()
    assert d.default_window_seconds == 1800


def test_overseer_dedup_explicit_args_override_env(tmp_path, monkeypatch):
    """Explicit kwargs win over env — supports tests + ad-hoc CLI use."""
    env_target = tmp_path / "env.sqlite"
    arg_target = tmp_path / "arg.sqlite"
    monkeypatch.setenv("EFLOUD_OVERSEER_DEDUP_DB", str(env_target))

    from ops.overseer.dedup import OverseerDedup
    d = OverseerDedup(db_path=str(arg_target), window_seconds=42)
    assert d.db_path == str(arg_target)
    assert d.default_window_seconds == 42
    # env-pointed file must NOT have been created (explicit arg won)
    assert not env_target.exists()


def test_overseer_dedup_inherits_should_fire_within_window(tmp_path, monkeypatch):
    """Same key fired twice inside window → 2nd call returns False.
    Verifies the inherited SQLite dedup semantics still work."""
    monkeypatch.setenv("EFLOUD_OVERSEER_DEDUP_DB", str(tmp_path / "d.sqlite"))
    from ops.overseer.dedup import OverseerDedup
    d = OverseerDedup(window_seconds=1800)
    assert d.should_fire("alert.key.A", 1800) is True
    assert d.should_fire("alert.key.A", 1800) is False  # duplicate inside window
    # Different key still allowed
    assert d.should_fire("alert.key.B", 1800) is True


def test_overseer_dedup_should_fire_uses_default_window_when_omitted(tmp_path, monkeypatch):
    """When caller omits window_sec, the OverseerDedup default (1800) applies.
    Avoids forcing every callsite to repeat the magic number."""
    monkeypatch.setenv("EFLOUD_OVERSEER_DEDUP_DB", str(tmp_path / "d.sqlite"))
    from ops.overseer.dedup import OverseerDedup
    d = OverseerDedup(window_seconds=1800)
    # First fire allowed with default window
    assert d.should_fire("alert.X") is True
    # Immediate retry blocked by default window (1800s)
    assert d.should_fire("alert.X") is False
