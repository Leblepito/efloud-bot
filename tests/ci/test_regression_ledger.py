"""Pins for the module regression ledger (REGRESSION.md, T-20261107-12).

The ledger is generated from `scripts/regression_ledger.py`: module table +
a reproducible AST import scan of tracked files. These tests keep it honest:
every first-party code file belongs to a module, the rendered ledger matches
the committed REGRESSION.md, and propagation pulls in downstream consumers
(including the runtime log-parsing edges the import scan cannot see).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def ledger():
    spec = importlib.util.spec_from_file_location(
        "regression_ledger", ROOT / "scripts" / "regression_ledger.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["regression_ledger"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def graph(ledger):
    return ledger.build_graph(ROOT)


@pytest.mark.parametrize(
    "path, module",
    [
        ("engine/safety/breaker.py", "safety"),
        ("engine/smc_v2/zones.py", "smc-v2"),
        ("engine/signals.py", "smc-v1"),
        ("engine/safe_orchestrator.py", "orchestrator"),
        ("exchange/adapter.py", "exchange"),
        ("backend/api.py", "backend-api"),
        ("backend/migrations/001_init.sql", "backend-db"),
        ("backend/social/__init__.py", "backend-social"),
        ("ops/alerter/rules.py", "alerter"),
        ("hooks/live_write_gate.py", "live-write-gate"),
        ("u2algo-site/server.js", "u2algo-site"),
        ("frontend/package.json", "frontend"),
        ("configs/config.phase2_1k.yaml", "configs"),
        (".github/workflows/ci.yml", "ci"),
        ("backtest/engine.py", "backtest"),
        ("docs/OPERATOR_GUIDE.md", None),
    ],
)
def test_path_maps_to_module(ledger, path, module):
    assert ledger.module_of(path) == module


def test_every_first_party_code_file_has_a_module(ledger, graph):
    code_roots = ("engine/", "backend/", "exchange/", "ops/", "data/", "utils/",
                  "risk/", "panel/", "hooks/", "scripts/", "tools/", "backtest/")
    orphans = [
        f for f in graph.files
        if f.endswith(".py") and f.startswith(code_roots)
        and not ledger.is_test_file(f) and ledger.module_of(f) is None
    ]
    assert orphans == []


def test_python_modules_have_tests_or_are_declared_gaps(ledger, graph):
    untested = {
        m.id for m in ledger.MODULES
        if not m.commands and not graph.tests_for(m.id)
    }
    assert untested == set(ledger.KNOWN_GAPS)


def test_committed_ledger_is_current(ledger, graph):
    rendered = ledger.render(graph)
    committed = (ROOT / "REGRESSION.md").read_text(encoding="utf-8")
    assert committed == rendered, (
        "REGRESSION.md is stale: run `python scripts/regression_ledger.py render`"
    )


def test_breaker_change_propagates_to_orchestrator_and_alerter(ledger, graph):
    plan = ledger.plan_for(graph, ["engine/safety/breaker.py"])
    assert {"safety", "orchestrator", "alerter"} <= plan.modules
    assert "alerter" in plan.unverified_included
    assert not plan.full_suite


def test_global_test_config_change_runs_full_suite(ledger, graph):
    assert ledger.plan_for(graph, ["tests/conftest.py"]).full_suite
    assert ledger.plan_for(graph, ["pyproject.toml"]).full_suite


def test_changed_test_file_is_run_directly(ledger, graph):
    plan = ledger.plan_for(graph, ["tests/hooks/test_live_write_gate.py"])
    assert "tests/hooks/test_live_write_gate.py" in plan.test_files


def test_docs_only_change_needs_no_regression_run(ledger, graph):
    plan = ledger.plan_for(graph, ["docs/OPERATOR_GUIDE.md"])
    assert not plan.modules and not plan.test_files and not plan.full_suite
    assert plan.unmapped == ["docs/OPERATOR_GUIDE.md"]


def test_runtime_edges_have_live_evidence(ledger):
    import shlex
    import subprocess

    for consumer, provider, _why, evidence in ledger.MANUAL_EDGES:
        assert consumer in {m.id for m in ledger.MODULES}
        assert provider in {m.id for m in ledger.MODULES}
        out = subprocess.run(shlex.split(evidence), cwd=ROOT, capture_output=True,
                             text=True, encoding="utf-8").stdout
        assert out.strip(), f"evidence went stale for {consumer} <- {provider}: {evidence}"
