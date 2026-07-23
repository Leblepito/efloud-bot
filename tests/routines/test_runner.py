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
