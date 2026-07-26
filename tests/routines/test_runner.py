import pytest
from scripts.routines import runner


class _StubAlert:
    """Hermetik alert stub'u — run_one, alert=None verilirse AlertRouter.from_env()
    ile GERCEK state/routines_dedup.sqlite yolunu acar. Cowork sandbox'inda eski
    oturumlarin sahipligindeki dosya okunamayinca (disk I/O error) test ortam
    yuzunden kirilir. Dispatch testinin konusu alert kurulumu degil — stub yeter.
    (2026-07-12: 'bilinen kirik' 7 testin kok nedeni bu tur state/ artefaktlariydi.)"""
    def send(self, **kw):
        pass


def test_run_one_dispatches(monkeypatch):
    runner.REGISTRY["dummy"] = lambda **kw: type("R", (), {"ok": True, "breaches": [], "name": "dummy", "error": None})()
    rc = runner.run_one("dummy", client=object(), alert=_StubAlert(), cfg={})
    assert rc == 0

def test_run_one_unknown_returns_2():
    assert runner.run_one("nope", client=object(), alert=None, cfg={}) == 2

def test_run_one_swallows_exception_returns_1():
    def boom(**kw):
        raise RuntimeError("boom!")
    runner.REGISTRY["boom"] = boom
    assert runner.run_one("boom", client=object(), alert=_StubAlert(), cfg={}) == 1


# ── R-12+ (2026-07-18): import-hatası startup alert'i ───────────────────────

def test_emit_import_failure_alerts_sends_per_module(monkeypatch):
    """IMPORT_FAILURES doluysa her modül için bir alert atılır (dep-drift'te
    rutin sessizce düşerse operatör haberdar olsun)."""
    from scripts.routines import runner

    class FakeRouter:
        def __init__(self): self.calls = []
        def send(self, severity, key, title, body):
            self.calls.append((severity, key, title, body)); return True

    monkeypatch.setattr(runner, "IMPORT_FAILURES",
                        {"market_collect": "ImportError: No module named pandas",
                         "resolve_signals": "SyntaxError: bad"})
    r = FakeRouter()
    n = runner.emit_import_failure_alerts(r)
    assert n == 2
    keys = [c[1] for c in r.calls]
    assert "routine_import_fail:market_collect" in keys
    assert "routine_import_fail:resolve_signals" in keys
    assert all(c[0] == "critical" for c in r.calls)


def test_emit_import_failure_alerts_noop_when_clean(monkeypatch):
    from scripts.routines import runner

    class FakeRouter:
        def __init__(self): self.calls = []
        def send(self, *a): self.calls.append(a); return True

    monkeypatch.setattr(runner, "IMPORT_FAILURES", {})
    r = FakeRouter()
    assert runner.emit_import_failure_alerts(r) == 0
    assert r.calls == []


def test_emit_import_failure_alerts_swallows_send_error(monkeypatch):
    """Alert transport patlarsa watcher açılışı çökmemeli."""
    from scripts.routines import runner

    class BoomRouter:
        def send(self, *a): raise RuntimeError("telegram down")

    monkeypatch.setattr(runner, "IMPORT_FAILURES", {"x": "err"})
    # raise etmemeli
    assert runner.emit_import_failure_alerts(BoomRouter()) == 0
