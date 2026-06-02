#!/usr/bin/env python3
"""Kronos Claude skill runner.

Outer launcher: handles first-run install (Kronos repo + venv + deps), then
delegates to the inner predict script inside the venv.

Usage:
    python3 run_kronos.py <TICKER> [period] [interval] [pred_len]

Examples:
    python3 run_kronos.py AAPL
    python3 run_kronos.py BTC-USD 3mo 4h 48
    python3 run_kronos.py NVDA 1y 1d 30
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
KRONOS_DIR = SKILL_DIR / "_kronos"
VENV_DIR = SKILL_DIR / ".venv"
REQUIREMENTS = SKILL_DIR / "requirements.txt"
INNER = SKILL_DIR / "scripts" / "_predict.py"

KRONOS_GIT_URL = "https://github.com/shiyu-coder/Kronos"


def info(msg: str) -> None:
    print(f"[kronos] {msg}", file=sys.stderr, flush=True)


def ensure_kronos_repo() -> None:
    if KRONOS_DIR.exists():
        return
    info("First run: cloning Kronos repo from GitHub...")
    subprocess.run(
        ["git", "clone", "--depth", "1", KRONOS_GIT_URL, str(KRONOS_DIR)],
        check=True,
    )


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python3"


def venv_pip() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def ensure_venv() -> None:
    if VENV_DIR.exists() and venv_python().exists():
        return
    info("First run: creating Python venv at .claude/skills/kronos/.venv...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    info("First run: installing dependencies (torch, transformers, yfinance, pandas)...")
    info("This takes 3-7 minutes. Subsequent runs are fast.")
    subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [str(venv_pip()), "install", "-r", str(REQUIREMENTS)],
        check=True,
    )


def run_prediction(ticker: str, period: str, interval: str, pred_len: str) -> int:
    env = os.environ.copy()
    env["KRONOS_REPO"] = str(KRONOS_DIR)
    proc = subprocess.run(
        [str(venv_python()), str(INNER), ticker, period, interval, pred_len],
        env=env,
    )
    return proc.returncode


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_kronos.py <TICKER> [period] [interval] [pred_len]")
        print("Example: run_kronos.py AAPL")
        print("Example: run_kronos.py BTC-USD 3mo 4h 48")
        return 1

    ticker = sys.argv[1].upper()
    period = sys.argv[2] if len(sys.argv) > 2 else "6mo"
    interval = sys.argv[3] if len(sys.argv) > 3 else "1d"
    pred_len = sys.argv[4] if len(sys.argv) > 4 else "24"

    ensure_kronos_repo()
    ensure_venv()
    return run_prediction(ticker, period, interval, pred_len)


if __name__ == "__main__":
    sys.exit(main())
