from scripts.routines.breaker_watch import evaluate

def test_halt_transition_pages():
    rep, b = evaluate({"state": "OPEN"}, {"state": "HALTED", "reason": "weekly_dd"})
    assert any(x["severity"] == "critical" for x in b)
    assert "HALTED" in rep

def test_no_change_silent():
    rep, b = evaluate({"state": "OPEN"}, {"state": "OPEN"})
    assert b == []

def test_recovery_info():
    rep, b = evaluate({"state": "HALTED"}, {"state": "OPEN"})
    assert any(x["severity"] == "info" for x in b)


# ── R-1 (2026-07-17): StateStore zarfı + canlı state_dir ────────────────────

def test_run_reads_statestore_envelope_from_live_state_dir(tmp_path, monkeypatch):
    """Canlı bot breaker.json'ı StateStore zarfıyla ({saved_at, data:{…}})
    ve cfg operation.state_dir altına yazar. Rutin zarfı açmadan sabit
    state/breaker.json okuyunca HALT geçişi HİÇ görülmüyordu."""
    import json
    from scripts.routines import breaker_watch as bw

    monkeypatch.chdir(tmp_path)
    live_dir = tmp_path / "state_1k"
    live_dir.mkdir()
    (live_dir / "breaker.json").write_text(json.dumps({
        "saved_at": "2026-07-17T00:00:00",
        "data": {"state": "HALTED", "reason": "weekly_dd",
                 "current_balance": 900.0, "peak_balance": 1000.0},
    }), encoding="utf-8")

    cfg = {"operation": {"state_dir": str(live_dir)}}
    res = bw.run(cfg=cfg)
    assert any(b["severity"] == "critical" and "HALTED" in b["title"]
               for b in res.breaches), "zarflı HALTED state görülmedi (R-1 regresyonu)"


def test_env_state_dir_overrides_cfg(tmp_path, monkeypatch):
    import json
    from scripts.routines import breaker_watch as bw

    monkeypatch.chdir(tmp_path)
    env_dir = tmp_path / "from_env"
    env_dir.mkdir()
    (env_dir / "breaker.json").write_text(json.dumps({
        "saved_at": "x", "data": {"state": "HALTED", "reason": "daily"},
    }), encoding="utf-8")
    monkeypatch.setenv("EFLOUD_STATE_DIR", str(env_dir))

    res = bw.run(cfg={"operation": {"state_dir": str(tmp_path / "bos")}})
    assert any(b["severity"] == "critical" for b in res.breaches)
