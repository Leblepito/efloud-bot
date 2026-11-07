"""Pins for CI hardening from the 2026-11-06 security audit (T-20261107-08).

- claude-review: everything that runs with ANTHROPIC_API_KEY (workflow
  definition + script) must come from the base branch, never from the PR under
  review; the PR diff is read as data via the API; SDK version pinned.
- hermes-review: workflow inputs reach shell only through env, never inline
  `${{ }}` expression interpolation inside `run:`.
- scheduled-review: the gitleaks auto-baseline (which adds fingerprints to the
  ignore list) only runs on a manual dispatch, so a new real leak can't turn
  into a self-suppressing PR from the daily schedule.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def _steps(wf: dict):
    for job in wf["jobs"].values():
        yield from job.get("steps", [])


def test_claude_review_runs_reviewer_with_pr_number_via_env():
    wf = _load("claude-review.yml")
    calls = [s for s in _steps(wf) if "claude_review.py" in s.get("run", "")]
    assert calls, "claude_review.py is no longer invoked"
    for s in calls:
        assert '"$PR_NUMBER"' in s["run"]
        assert s.get("env", {}).get("PR_NUMBER") == "${{ github.event.pull_request.number }}"


def test_claude_review_pins_anthropic_sdk():
    runs = [s.get("run", "") for s in _steps(_load("claude-review.yml"))]
    installs = [r for r in runs if "pip install" in r and "anthropic" in r]
    assert installs and all(re.search(r"anthropic==\d+\.\d+\.\d+", r) for r in installs)


def test_hermes_review_inputs_not_interpolated_into_shell():
    for step in _steps(_load("hermes-review.yml")):
        run = step.get("run", "")
        assert "${{ github.event." not in run, step.get("name")


# ── review round 2: the workflow file itself is PR-controlled on pull_request ──
# Only pull_request_target runs the BASE branch's workflow definition, so the
# key-bearing jobs must use it, check out base only, read the PR diff through
# the API (data, never executed) and skip fork PRs (they get secrets there).

def test_claude_review_uses_pull_request_target_only():
    wf = _load("claude-review.yml")
    on = wf.get("on", wf.get(True))  # PyYAML parses bare `on:` as True
    assert set(on) == {"pull_request_target"}


def test_claude_review_never_checks_out_pr_code_and_skips_forks():
    wf = _load("claude-review.yml")
    for name, job in wf["jobs"].items():
        assert job.get("if") and "head.repo.full_name == github.repository" in job["if"], name
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout"):
                opts = step.get("with") or {}
                assert "ref" not in opts and "repository" not in opts, (name, opts)
            assert "${{ github.event" not in step.get("run", ""), (name, step.get("name"))


def test_gitleaks_baseline_gate_is_equality():
    steps = {s.get("name"): s for s in _steps(_load("scheduled-review.yml"))}
    for name in ("gitleaks auto-baseline", "Commit gitleaks baseline"):
        assert "github.event_name == 'workflow_dispatch'" in str(steps[name]["if"]), name


def _load_reviewer(monkeypatch):
    import importlib.util
    import sys
    import types

    monkeypatch.setitem(sys.modules, "anthropic", types.ModuleType("anthropic"))
    path = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "claude_review.py"
    spec = importlib.util.spec_from_file_location("_ci_claude_review_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reviewer_reads_pr_diff_from_api(monkeypatch):
    mod = _load_reviewer(monkeypatch)
    calls = []

    class Done:
        stdout = "diff --git a/x b/x\n+line\n"

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return Done()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert "+line" in mod.get_pr_diff("123")
    assert calls == [["gh", "pr", "diff", "123"]]


def test_reviewer_comments_instead_of_failing_when_diff_unavailable(monkeypatch):
    """The API refuses very large diffs (HTTP 406); that must not fail the job."""
    mod = _load_reviewer(monkeypatch)

    def boom(cmd, **kw):
        raise mod.subprocess.CalledProcessError(1, cmd, stderr="HTTP 406: diff too large")

    posted = []
    monkeypatch.setattr(mod.subprocess, "run", boom)
    monkeypatch.setattr(mod, "post_pr_comment", lambda pr, agent, body: posted.append((pr, agent, body)))
    monkeypatch.setattr(mod, "run_review", lambda *a: (_ for _ in ()).throw(AssertionError("LLM called")))
    monkeypatch.setattr(mod.sys, "argv", ["claude_review.py", "risk-safety-auditor", "42"])
    assert mod.main() == 0
    assert len(posted) == 1 and posted[0][:2] == ("42", "risk-safety-auditor")
    assert "manual review" in posted[0][2].lower()


def test_claude_review_trigger_paths_preserved():
    wf = _load("claude-review.yml")
    on = wf.get("on", wf.get(True))
    paths = set(on["pull_request_target"]["paths"])
    assert {"engine/safety/**", "engine/risk/**", "exchange/**", "configs/**", "engine/smc_v2/**"} <= paths


def test_paths_filter_pinned_to_commit_sha():
    for step in _steps(_load("claude-review.yml")):
        uses = str(step.get("uses", ""))
        if uses.startswith("dorny/paths-filter"):
            assert re.fullmatch(r"dorny/paths-filter@[0-9a-f]{40}", uses), uses
