import pytest
from scripts.routines import runner

def test_run_one_dispatches(monkeypatch):
    runner.REGISTRY["dummy"] = lambda **kw: type("R", (), {"ok": True, "breaches": [], "name": "dummy", "error": None})()
    rc = runner.run_one("dummy", client=object(), alert=None, cfg={})
    assert rc == 0

def test_run_one_unknown_returns_2():
    assert runner.run_one("nope", client=object(), alert=None, cfg={}) == 2

def test_run_one_swallows_exception_returns_1():
    def boom(**kw):
        raise RuntimeError("boom!")
    runner.REGISTRY["boom"] = boom
    assert runner.run_one("boom", client=object(), alert=None, cfg={}) == 1
