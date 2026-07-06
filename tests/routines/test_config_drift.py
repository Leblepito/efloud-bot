from scripts.routines.config_drift import evaluate, run

def test_drift_detected():
    _, b = evaluate({"min_confluence": 50}, {"min_confluence": 80}, ["min_confluence"])
    assert any(x["severity"] == "warn" for x in b)
    assert "50" in b[0]["body"]
    assert "80" in b[0]["body"]

def test_in_sync_silent():
    _, b = evaluate({"min_confluence": 80}, {"min_confluence": 80}, ["min_confluence"])
    assert b == []

def test_nested_drift_detected():
    live = {"safety": {"weekly_drawdown_limit_pct": 5}}
    repo = {"safety": {"weekly_drawdown_limit_pct": 8}}
    _, b = evaluate(live, repo, ["safety.weekly_drawdown_limit_pct"])
    assert any(x["severity"] == "warn" for x in b)
    assert "5" in b[0]["body"]
    assert "8" in b[0]["body"]


def test_run_baselines_against_efloud_config_path(tmp_path, monkeypatch):
    """Baseline must be the instance's ACTIVE config (EFLOUD_CONFIG_PATH), not
    root config.yaml — long/scalp load configs/config.phase2_*_1k.yaml, so a
    root-yaml baseline reports systematic false-positive drift."""
    import scripts.routines._base as base

    cfg_file = tmp_path / "instance.yaml"
    cfg_file.write_text("min_confluence: 42\n", encoding="utf-8")
    monkeypatch.setenv("EFLOUD_CONFIG_PATH", str(cfg_file))

    # Live config matches the instance config exactly → zero drift expected.
    monkeypatch.setattr(base, "get_api", lambda path, params=None: {"min_confluence": 42})
    monkeypatch.setattr(base, "write_report", lambda *a, **k: None)
    monkeypatch.setattr(base, "write_snapshot", lambda *a, **k: None)

    result = run()
    assert result.ok
    # Root config.yaml has min_confluence 55 — a breach here means the routine
    # compared against the wrong baseline file.
    assert not any(x["key"] == "drift:min_confluence" for x in result.breaches)
