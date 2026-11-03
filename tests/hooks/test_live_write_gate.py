"""Tests for hooks/live_write_gate.py — the Claude Code PreToolUse backstop.

The gate must return an "ask" decision for Bash commands that look like a
live-state write (Binance order/leverage/margin via ccxt, signed fapi
POST/DELETE, bot control API writes, production deploy) and stay silent for
everything else. It must never return "allow".
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "hooks" / "live_write_gate.py"


def run_gate(command: str, cwd: Path | None = None, tool: str = "Bash") -> dict | None:
    event = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd or ROOT)}
    out = subprocess.run(
        [sys.executable, "-I", str(GATE)],
        input=json.dumps(event), capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout) if out.stdout.strip() else None


def decision(result: dict | None) -> str | None:
    if result is None:
        return None
    return result["hookSpecificOutput"]["permissionDecision"]


@pytest.mark.parametrize("command", [
    # ccxt writes (inline python)
    "python -c 'ex.create_order(\"BTC/USDT\", \"limit\", \"buy\", 0.01, 60000)'",
    "python -c 'exchange.cancel_order(\"123\", \"BTC/USDT\")'",
    "python -c 'client.set_leverage(10, \"ETH/USDT\")'",
    "python -c 'ex.set_margin_mode(\"isolated\", \"SOL/USDT\")'",
    "python -c 'ex.cancel_all_orders(\"BTC/USDT\")'",
    "python -c 'ex.create_market_order(\"BTC/USDT\", \"sell\", 1)'",
    # signed Binance futures private writes
    "python -c 'ex.fapiPrivatePostOrder(params)'",
    "python -c 'ex.fapiPrivateDeleteAlgoOrder(p)'",
    "curl -X POST https://fapi.binance.com/fapi/v1/order -H 'X-MBX-APIKEY: k'",
    "curl -X DELETE 'https://fapi.binance.com/fapi/v1/allOpenOrders?symbol=BTCUSDT'",
    # bot control API writes
    "curl -s -X POST https://bot.u2algo.com/api/bot/start -H 'Authorization: Bearer x'",
    "curl -X POST http://localhost:8000/api/kill-switch",
    "curl -X POST $API/api/breaker/reset",
    "curl -XPOST https://2-28-139-82.nip.io/api/orders/close -d '{}'",
    "curl -X POST https://bot.u2algo.com/api/bot/restart",
    # production deploy
    "bash deploy/deploy.sh",
    "./deploy/deploy.sh mid",
    "docker compose -f docker-compose.prod.yml up -d --force-recreate efloud-bot",
    "docker-compose -f docker-compose.prod.yml restart",
    "python scripts/supabase_apply.py --apply",
])
def test_live_writes_get_ask(command):
    assert decision(run_gate(command)) == "ask"


@pytest.mark.parametrize("command", [
    "pytest -q",
    "git status",
    "python -c 'ex.fetch_ohlcv(\"BTC/USDT\", \"15m\")'",
    "python -c 'ex.fetch_positions()'",
    "python -c 'ex.fapiPrivateV2GetPositionRisk()'",
    "curl -s https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m",
    "curl -s https://bot.u2algo.com/api/health",
    "curl -s -X POST https://bot.u2algo.com/api/login -d '{}'",
    "docker compose -f docker-compose.prod.yml logs --tail 100",
    "docker compose -f docker-compose.prod.yml ps",
    "docker compose up -d",  # local dev compose, not prod
    "grep -n create_order engine/safe_orchestrator.py",
    "cat deploy/deploy.sh",
])
def test_reads_and_dev_commands_pass_silently(command):
    assert run_gate(command) is None


def test_write_inside_named_script_is_detected(tmp_path):
    script = tmp_path / "close_all.py"
    script.write_text("import ccxt\nex = ccxt.binanceusdm()\nex.create_order('BTC/USDT','market','sell',1)\n")
    result = run_gate("python close_all.py", cwd=tmp_path)
    assert decision(result) == "ask"
    assert "close_all.py" in result["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("prefix", ["python3 -u", "./", "docker exec -i efloud-bot python", "uv run python"])
def test_executed_script_variants_are_inspected(tmp_path, prefix):
    script = tmp_path / "flat.py"
    script.write_text("ex.cancel_all_orders('BTC/USDT')\n")
    sep = "" if prefix.endswith("/") else " "
    assert decision(run_gate(f"{prefix}{sep}flat.py", cwd=tmp_path)) == "ask"


@pytest.mark.parametrize("command", [
    "grep -n foo writer.py",
    "cat writer.py",
    "sed -n 1,40p writer.py",
    "pytest -q writer.py",
    "python -m pytest writer.py",
    "ruff check writer.py",
])
def test_reading_or_testing_a_writer_file_is_not_a_write(tmp_path, command):
    (tmp_path / "writer.py").write_text("ex.create_order('BTC/USDT','market','buy',1)\n")
    assert run_gate(command, cwd=tmp_path) is None


def test_read_only_named_script_passes(tmp_path):
    script = tmp_path / "report.py"
    script.write_text("import ccxt\nex = ccxt.binanceusdm()\nprint(ex.fetch_ticker('BTC/USDT'))\n")
    assert run_gate("python report.py", cwd=tmp_path) is None


def test_non_bash_tools_ignored():
    assert run_gate("ex.create_order(1)", tool="Read") is None


@pytest.mark.parametrize("payload", ["", "not json", "[]", '{"tool_name": "Bash"}'])
def test_malformed_input_never_crashes(payload):
    out = subprocess.run([sys.executable, "-I", str(GATE)], input=payload,
                         capture_output=True, text=True, timeout=10)
    assert out.returncode == 0
    assert out.stdout.strip() == ""


def test_never_allows():
    src = GATE.read_text(encoding="utf-8")
    assert '"allow"' not in src and "'allow'" not in src
