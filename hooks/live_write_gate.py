#!/usr/bin/env python3
"""Claude Code PreToolUse gate for efloud-bot live-state writes. Stdlib only.

Adapted from HyperGrok Trading Desk's `hooks/exchange_write_gate.py`
(https://github.com/galleonlabs/hypergrok-trading-desk, MIT License,
Copyright (c) 2026 Galleon Labs; see THIRD_PARTY_NOTICES.md). Changes: the
Hyperliquid patterns were replaced with Binance USDT-M (ccxt + signed fapi),
the efloud bot control API, production deploy scripts/compose and the
Supabase apply script.

A Bash command that looks like a live write gets an "ask" decision, so the
operator confirms it even in an auto-accepting session. Anything else gets no
opinion and follows the normal permission flow. The gate never approves.

It reads the command text and any script file the command names (resolved
from the session's working directory). It does not follow imports, so a write
hidden in a helper module is not seen. It is a backstop, not the approval:
the desk's ticket protocol (skills/desk-operating-model) is the control.
"""
import json
import os
import re
import sys

# ccxt unified write methods (order, leverage, margin, funds).
SDK_WRITE_RE = re.compile(
    r"\.\s*(create_order|create_\w*order|create_orders|cancel_order|cancel_orders|"
    r"cancel_all_orders|edit_order|set_leverage|set_margin_mode|set_position_mode|"
    r"add_margin|reduce_margin|set_margin|transfer|withdraw)\s*\(",
)
# ccxt implicit signed endpoints that change state (fapiPrivatePostOrder, ...).
PRIVATE_WRITE_RE = re.compile(r"\b\w*[Pp]rivate(?:V\d)?(Post|Put|Delete)\w*\s*\(")
# Raw HTTP write to Binance.
HTTP_WRITE_METHOD_RE = re.compile(r"(?:-X\s*|--request\s+)(POST|PUT|DELETE)\b", re.IGNORECASE)
BINANCE_HOST_RE = re.compile(r"binance\.(?:com|us)\b", re.IGNORECASE)
# efloud bot control API writes (all POST-only routes in backend/api.py).
# URL prefix: scheme URL, $VAR/${VAR}/}, or a scheme-less host the way curl and
# httpie accept it — dotted host / IPv4 with optional port, a docker service
# name with a port (efloud-bot:8000), localhost, or httpie's bare ":port"
# (T-20261107-01; scheme-less form was a gap).
BOT_API_WRITE_RE = re.compile(
    r"(?:https?://[^\s'\"]*|\$\{?\w+\}?|\}"
    r"|(?<![\w/.-])(?:[\w-]+(?:\.[\w-]+)+(?::\d+)?|[\w-]+:\d+|localhost)|(?<![\w/.-]):\d+)/api/"
    r"(bot/(?:start|stop|restart)|kill-switch|breaker/reset|orders/close)\b"
)
# Production deploy / state scripts, only when executed (not cat/grep/less).
DEPLOY_SCRIPT_RE = re.compile(
    r"(?:\b(?:bash|sh|zsh)\s+|(?:^|[;&|(]\s*)\.?/?)(?:\S*/)?"
    r"deploy/(?:deploy|setup-server|rotate-credentials|backup/restore_state)\.sh\b"
)
PROD_COMPOSE_RE = re.compile(
    r"docker[\s-]compose\b[^;&|]*docker-compose\.(?:prod|panel)\.yml[^;&|]*"
    r"\b(up|down|restart|stop|start|rm|kill|pull|create)\b"
)
# Compose state change sent to a remote host over ssh. On the prod VPS the
# default docker-compose.yml also defines `container_name: efloud-bot`, so a
# `docker compose up` there without -f can replace the prod container
# (T-20261107-01). Local `docker compose up` stays silent (dev).
# Two separate searches (an `ssh` word anywhere + a compose verb on one line)
# keep this linear-ish: a single ssh…compose…verb pattern backtracked cubically
# and a hook timeout means "no opinion" (fails open). Heredoc / multi-line
# remote commands are covered because the verb only has to share a line with
# `docker compose`. `.ssh`, `ssh-keygen` and `status=up` do not count.
SSH_WORD_RE = re.compile(r"(?<![\w.~/-])ssh\s")
COMPOSE_VERB_RE = re.compile(
    r"\bdocker[\s-]compose\b[^;&|\n]{0,200}?\s(up|down|restart|stop|start|rm|kill|pull|create)(?=\s|$|['\"])",
    re.MULTILINE,
)
DOCKER_CONTAINER_RE = re.compile(r"\bdocker\s+(stop|restart|kill|rm)\s+(?:-\S+\s+)*\S*efloud")
SUPABASE_APPLY_RE = re.compile(r"\bsupabase_apply\.py\b(?![^;&|]*--dry-run)")

# Only scripts that are *executed* by an interpreter (or ./script) are inspected;
# reading (cat/grep/sed), linting or pytest-ing a file that mentions a write
# method is not a write. (Deviation from upstream, which scanned any named file.)
EXEC_SCRIPT_RE = re.compile(
    r"(?:\b(?:python(?:3(?:\.\d+)?)?|py|node|bun|deno(?:\s+run)?|tsx|ts-node)\b(?:\s+-[A-Za-z]+)*\s+"
    r"|(?:^|[;&|(]\s*|\s)\./)"
    r"([\w./~-]+\.(?:py|ts|mts|cts|js|mjs|cjs))\b"
)
MAX_SCRIPT_BYTES = 2_000_000


def find_write_in_code(text):
    """Patterns that apply both to the command line and to named script files."""
    match = SDK_WRITE_RE.search(text) or PRIVATE_WRITE_RE.search(text)
    if match:
        return match.group(0).rstrip("( ").lstrip(". ")
    if HTTP_WRITE_METHOD_RE.search(text) and BINANCE_HOST_RE.search(text):
        return "an HTTP write to Binance"
    match = BOT_API_WRITE_RE.search(text)
    if match:
        return f"bot API /api/{match.group(1)}"
    return None


def find_write_in_command(command):
    found = find_write_in_code(command)
    if found:
        return found
    for regex, label in (
        (DEPLOY_SCRIPT_RE, "a production deploy script"),
        (PROD_COMPOSE_RE, "a production docker compose change"),
        (DOCKER_CONTAINER_RE, "a bot container stop/restart"),
        (SUPABASE_APPLY_RE, "a Supabase schema apply (no --dry-run)"),
    ):
        if regex.search(command):
            return label
    if SSH_WORD_RE.search(command) and COMPOSE_VERB_RE.search(command):
        return "a docker compose change on a remote host"
    return None


def named_scripts(command, cwd):
    for token in EXEC_SCRIPT_RE.findall(command):
        path = os.path.expanduser(token)
        if not os.path.isabs(path):
            path = os.path.join(cwd, path)
        try:
            if os.path.isfile(path) and os.path.getsize(path) <= MAX_SCRIPT_BYTES:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    yield token, handle.read()
        except OSError:
            continue


def decide(event):
    if event.get("tool_name") != "Bash":
        return None
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command:
        return None
    found = find_write_in_command(command)
    where = "in the command"
    if not found:
        cwd = event.get("cwd") or os.getcwd()
        for token, text in named_scripts(command, cwd):
            found = find_write_in_code(text)
            if found:
                where = f"in {token}"
                break
    if not found:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"efloud live-write gate: this looks like a live-state write ({found} {where}). "
                "Approve only if it is the single action for a ticket with a Risk PASS "
                "and the operator's approval by that ticket id (skills/desk-operating-model)."
            ),
        }
    }


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    if not isinstance(event, dict):
        return 0
    decision = decide(event)
    if decision:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
