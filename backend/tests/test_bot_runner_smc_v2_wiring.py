"""Regression test: backend.bot_runner must wire setup_state_store into SafeOrchestrator.

Background (2026-05-25 production observation):
PR #S6 (cdd01c5) added _build_setup_state_store to main.py (CLI entrypoint) and
wired it into the CLI's SafeOrchestrator construction. But backend/bot_runner.py
(FastAPI production path) was missed — its SafeOrchestrator() call did not pass
setup_state_store, so v2 stayed inert in production regardless of config.yaml.

Discovered when Phase 2 shadow activation produced no shadow log signals after
10+ minutes of bot operation with smc_version=v2, smc_v2_symbols=["*"],
smc_v2_shadow=true. Grep on backend/ confirmed no setup_state_store reference
in bot_runner.

This test reads bot_runner.py source and asserts the wiring is present, so any
regression (a refactor that loses the kwarg) fails CI before deploy.
"""
from __future__ import annotations

import inspect

from backend import bot_runner


def test_bot_runner_wires_setup_state_store_into_safe_orchestrator():
    """BotRunner.start() must pass setup_state_store= kwarg to SafeOrchestrator().

    We assert against the source text rather than mocking the full start() path
    (which requires Binance creds, DB pool, FastAPI app context, etc).
    """
    src = inspect.getsource(bot_runner)
    assert "_build_setup_state_store" in src, (
        "bot_runner.py must import _build_setup_state_store (from main). "
        "Without it, FastAPI production path never activates v2 — see PR #S6 wiring gap."
    )
    assert "setup_state_store=setup_state_store" in src, (
        "bot_runner.py must pass setup_state_store kwarg to SafeOrchestrator(). "
        "Without it, v2 stays inert regardless of config.yaml smc_version=v2."
    )


def test_bot_runner_imports_build_helper_from_main():
    """The helper lives in main.py (CLI entry); bot_runner imports it.

    Centralizing the v2 wiring logic in main._build_setup_state_store avoids
    drift between CLI and FastAPI activation semantics.
    """
    src = inspect.getsource(bot_runner)
    assert "from main import _build_setup_state_store" in src, (
        "bot_runner must reuse main._build_setup_state_store to keep CLI and "
        "FastAPI v2 activation semantics identical."
    )
