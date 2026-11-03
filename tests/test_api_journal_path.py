from pathlib import Path

from backend import api


def test_journal_path_follows_runner_state_dir(monkeypatch):
    monkeypatch.delenv("EFLOUD_TRADE_JOURNAL", raising=False)
    monkeypatch.setattr(api.runner, "cfg", {"operation": {"state_dir": "./state_1k"}})
    assert Path(api._journal_path()) == Path("./state_1k/trade_journal.jsonl")


def test_journal_path_reads_config_file_when_runner_idle(monkeypatch, tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("operation:\n  state_dir: /x/state_long\n", encoding="utf-8")
    monkeypatch.delenv("EFLOUD_TRADE_JOURNAL", raising=False)
    monkeypatch.setenv("EFLOUD_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(api.runner, "cfg", None)
    assert Path(api._journal_path()) == Path("/x/state_long/trade_journal.jsonl")


def test_journal_path_env_override(monkeypatch):
    monkeypatch.setenv("EFLOUD_TRADE_JOURNAL", "/tmp/j.jsonl")
    assert api._journal_path() == "/tmp/j.jsonl"
