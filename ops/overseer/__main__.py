"""Overseer CLI entry point.

Sub-commands:
  watch          — long-running asyncio loop (sidecar default)
  summarize      — one-shot hourly summary; print to stdout (Week 3+ wires LLM)
  report         — one-shot daily report; send via email + telegram (Week 3+)
  extract-phase0 — one-shot Phase 0 evidence extraction; JSON status to stdout
  self-check     — diagnostic: import smoke + state read; exit 0/1

Env-driven config (all reads happen *inside* main(), never at import time,
so `python -m ops.overseer self-check` works in a fresh container with
only EFLOUD_OVERSEER_STATE_DB set):

  EFLOUD_LOG_FILE                — required for `watch`
  EFLOUD_HEALTHZ_URL             — required for `watch`
  EFLOUD_OVERSEER_JOURNAL_PATH   — required for `watch`
  EFLOUD_OVERSEER_DEDUP_DB       — optional; OverseerDedup default
  EFLOUD_OVERSEER_HEARTBEAT_FILE — optional; overseer mirrors heartbeat here
  EFLOUD_OVERSEER_STATE_DB       — defaults to /app/state/overseer_state.sqlite
  EFLOUD_OVERSEER_LLM_DAILY_CAP  — int; default 500
  EFLOUD_OVERSEER_DRY_RUN        — 1/true/yes/on → log-only mode (no sinks)
  ANTHROPIC_API_KEY              — required iff LLM not offline (Week 3+)
  EFLOUD_SMTP_*                  — required for `report` (Week 3+)

Design notes:
- Modules with heavy / optional deps (anthropic SDK) are imported *inside*
  the subcommand branch so `self-check` + `--help` stay cheap.
- Every subcommand returns int 0/1; argparse's own SystemExit on --help/
  unknown args bubbles to the CLI caller.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from typing import Optional

log = logging.getLogger("efloud.overseer.main")


# ─────────────────────────────────────────────────────────────────────
# argparse setup — single dispatcher, one parser, sub-parsers per command.
# ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ops.overseer",
        description="Efloud overseer agent — observes bot behaviour, summarises, reports.",
    )
    subs = p.add_subparsers(dest="subcommand", required=True)

    subs.add_parser(
        "watch",
        help="Long-running asyncio loop — sidecar default.",
    )
    subs.add_parser(
        "summarize",
        help="One-shot hourly summary; prints to stdout. (Week 3+ wires LLM)",
    )
    subs.add_parser(
        "report",
        help="One-shot daily report; email + telegram. (Week 3+ wires LLM)",
    )
    subs.add_parser(
        "extract-phase0",
        help="One-shot Phase 0 evidence extraction; JSON status to stdout.",
    )
    subs.add_parser(
        "self-check",
        help="Diagnostic: imports + state DB bootstrap. Exit 0 on success.",
    )
    return p


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _state_db_path() -> str:
    return os.environ.get(
        "EFLOUD_OVERSEER_STATE_DB", "/app/state/overseer_state.sqlite"
    )


# ─────────────────────────────────────────────────────────────────────
# Subcommand bodies — each returns int (0 success, non-zero failure).
# ─────────────────────────────────────────────────────────────────────


def _cmd_self_check() -> int:
    """Smoke-test imports + open the state DB. Returns 0 on success."""
    try:
        # Touch every overseer module so a broken import surfaces here.
        from ops.overseer import dedup, rules, state, summarizer, watch  # noqa: F401
        from ops.overseer.ingestors import (  # noqa: F401
            healthz_poller, journal_tail, log_tail,
        )
        from ops.overseer.sinks import telegram as _t  # noqa: F401
        from ops.overseer.phase0_runner import Phase0Runner  # noqa: F401

        # Open state DB — verifies SQLite path is writable.
        st = state.OverseerState(_state_db_path())
        # Round-trip a heartbeat write to confirm schema bootstrap worked.
        st.write_heartbeat()
        age = st.get_heartbeat_age_seconds()
        log.info("self-check OK — state DB heartbeat age=%s", age)
        sys.stdout.write("self-check OK\n")
        return 0
    except Exception as e:  # pragma: no cover — defensive net
        log.exception("self-check failed: %s", e)
        sys.stderr.write(f"self-check FAILED: {e}\n")
        return 1


def _cmd_extract_phase0() -> int:
    """Run Phase 0 evidence extraction once. Emits a JSON status dict to stdout."""
    from ops.overseer.phase0_runner import Phase0Runner

    runner = Phase0Runner()
    dry = _truthy_env("EFLOUD_OVERSEER_DRY_RUN")
    result = runner.run(dry_run=dry)
    # Emit JSON so cron logs can be machine-parsed.
    sys.stdout.write(json.dumps(result, default=str) + "\n")
    # Status semantics: 'ok' and 'dry_run' → 0; 'failed' → 1.
    return 0 if result.get("status") in ("ok", "dry_run") else 1


def _cmd_summarize() -> int:
    """Placeholder — Week 3+ will wire the Summarizer + emit hourly summary.

    Today: prints a stub so the cron schedule doesn't page on no-op runs.
    """
    sys.stdout.write("summarize subcommand placeholder\n")
    return 0


def _cmd_report() -> int:
    """Placeholder — Week 3+ will wire Summarizer + email + telegram sinks."""
    sys.stdout.write("report subcommand placeholder\n")
    return 0


def _cmd_watch() -> int:
    """Build OverseerWatch from env + run_forever until SIGTERM/SIGINT."""
    # Required env — fail loud, don't silently no-op on misconfig.
    log_file = os.environ.get("EFLOUD_LOG_FILE")
    healthz_url = os.environ.get("EFLOUD_HEALTHZ_URL")
    journal_path = os.environ.get("EFLOUD_OVERSEER_JOURNAL_PATH")
    missing = [
        name
        for name, val in (
            ("EFLOUD_LOG_FILE", log_file),
            ("EFLOUD_HEALTHZ_URL", healthz_url),
            ("EFLOUD_OVERSEER_JOURNAL_PATH", journal_path),
        )
        if not val
    ]
    if missing:
        sys.stderr.write(
            "overseer watch: missing required env: " + ", ".join(missing) + "\n"
        )
        return 1

    from ops.overseer.dedup import OverseerDedup
    from ops.overseer.rules import OVERSEER_RULES
    from ops.overseer.sinks.telegram import send_overseer_message
    from ops.overseer.state import OverseerState
    from ops.overseer.watch import OverseerWatch

    state = OverseerState(_state_db_path())
    dedup = OverseerDedup()
    dry_run = _truthy_env("EFLOUD_OVERSEER_DRY_RUN")

    # Telegram sink wraps the helper so the OverseerWatch sink signature
    # (text, severity) maps onto send_overseer_message(text, *, severity).
    def _sink(text: str, severity: str) -> bool:
        return bool(send_overseer_message(text, severity=severity))

    watch = OverseerWatch(
        log_path=log_file,
        healthz_url=healthz_url,
        journal_path=journal_path,
        state=state,
        dedup=dedup,
        rules=OVERSEER_RULES,
        sink_telegram=_sink,
        dry_run=dry_run,
    )

    return asyncio.run(_run_watch(watch))


async def _run_watch(watch) -> int:
    """Drive watch.run_forever with a clean SIGTERM/SIGINT handler.

    Separated from _cmd_watch so the asyncio.run() boundary is testable.
    """
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    # add_signal_handler isn't supported on Windows event loops; the prod
    # container is Linux, so wrap in try/except to avoid breaking dev runs.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown.set)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await watch.run_forever(shutdown)
        return 0
    except Exception as e:  # pragma: no cover — defensive
        log.exception("overseer watch raised: %s", e)
        return 1


# ─────────────────────────────────────────────────────────────────────
# Public entry point — exposed for tests + `python -m ops.overseer`.
# ─────────────────────────────────────────────────────────────────────


_DISPATCH = {
    "watch": _cmd_watch,
    "summarize": _cmd_summarize,
    "report": _cmd_report,
    "extract-phase0": _cmd_extract_phase0,
    "self-check": _cmd_self_check,
}


def main(argv: Optional[list[str]] = None) -> int:
    """Returns exit code 0/1. Used by tests + __name__=='__main__'.

    `--help` and unknown subcommands raise SystemExit (argparse default);
    valid subcommands return int directly so tests can assert without
    catching SystemExit.
    """
    # Configure logging once per invocation — alerter-parity simple text format.
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(name)-25s | %(levelname)-5s | %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = _DISPATCH.get(args.subcommand)
    if handler is None:  # pragma: no cover — argparse rejects unknowns first
        sys.stderr.write(f"unknown subcommand: {args.subcommand}\n")
        return 2
    return handler()


if __name__ == "__main__":
    sys.exit(main())
