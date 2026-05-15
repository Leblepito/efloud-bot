"""Phase 0 SL evidence script subprocess wrapper.

Çağrı yeri: overseer her gün 03:00 UTC bunu tetikler (cron-driven; Task E'de
docker-compose'a schedule eklenecek). Watch loop'undan ayrı, tek-shot job.

Subprocess strategy: bot container'ı zaten scripts/extract_sl_evidence.py
ile aynı image'da → sidecar overseer container'ında python3 ile direct
call. (Docker exec ihtiyacı doğarsa script_path + python_executable
override edilir.)

Failure contract: bu sınıf **hiç raise etmez**. Tüm hata yolları result
dict üzerinden ('status'='failed' + exit_code/stderr_tail) raporlanır.
Caller (overseer cron tetikleyici) sadece dict bakar."""
from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("efloud.overseer.phase0")


# ─────────────────────────────────────────────────────────────────────
# Defaults — Phase 0 evidence universe + lookback window.
# ─────────────────────────────────────────────────────────────────────

DEFAULT_SYMBOLS: list[str] = [
    "OP/USDT",
    "FIL/USDT",
    "BTC/USDT",
    "ETH/USDT",
    "ADA/USDT",
    "SUI/USDT",
    "LTC/USDT",
]
DEFAULT_LOOKBACK_DAYS = 7
_TAIL_BYTES = 1024  # ≤1KB of stdout/stderr surfaced in result dict


class Phase0Runner:
    """Wrap scripts/extract_sl_evidence.py as a one-shot subprocess.

    Public surface is one method (`run`) returning a typed dict — no
    raised exceptions, even on timeout / OSError / non-zero exit code."""

    def __init__(
        self,
        script_path: str = "scripts/extract_sl_evidence.py",
        python_executable: str = "python3",
        timeout_sec: float = 300.0,
    ):
        self._script_path = script_path
        self._python = python_executable
        self._timeout_sec = float(timeout_sec)

    # ---- public API --------------------------------------------------------

    def run(
        self,
        *,
        since: Optional[str] = None,
        symbols: Optional[list[str]] = None,
        out_dir: str = "/app/reports/phase0",
        dry_run: bool = False,
    ) -> dict:
        """Execute the script. Returns a status dict (never raises).

        Keys:
            status        — 'ok' | 'failed' | 'dry_run'
            exit_code     — int (0 on success, non-zero on failure)
            stdout_tail   — str (last ≤1KB)
            stderr_tail   — str (last ≤1KB)
            csv_path      — str (planned output path, may not exist yet)
            summary_path  — str
            duration_sec  — float (wall-clock; 0 in dry_run)
            command       — list[str] (the assembled subprocess args)
        """
        effective_since = since or self._default_since_iso_z()
        effective_symbols = symbols if symbols is not None else list(DEFAULT_SYMBOLS)

        # Dated subdir keeps historical runs separable (one folder per UTC date).
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dated_dir = Path(out_dir) / today_str
        csv_path = str(dated_dir / "evidence.csv")
        summary_path = str(dated_dir / "summary.md")

        command = self._build_command(
            since=effective_since,
            symbols=effective_symbols,
            csv_path=csv_path,
            summary_path=summary_path,
        )

        if dry_run:
            log.info("phase0_runner DRY_RUN: %s", " ".join(command))
            return {
                "status": "dry_run",
                "exit_code": 0,
                "stdout_tail": "",
                "stderr_tail": "",
                "csv_path": csv_path,
                "summary_path": summary_path,
                "duration_sec": 0.0,
                "command": command,
            }

        # Mkdir the dated output dir before launching so the script never
        # crashes on a missing parent — the script itself does not mkdir.
        try:
            dated_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.warning("phase0_runner mkdir failed for %s: %s", dated_dir, e)
            return {
                "status": "failed",
                "exit_code": -1,
                "stdout_tail": "",
                "stderr_tail": f"mkdir failed: {e}",
                "csv_path": csv_path,
                "summary_path": summary_path,
                "duration_sec": 0.0,
                "command": command,
            }

        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            log.warning("phase0_runner timeout after %.1fs", duration)
            tail_err = self._tail(_stringify(e.stderr) or f"timeout after {self._timeout_sec}s")
            tail_out = self._tail(_stringify(e.stdout))
            return {
                "status": "failed",
                "exit_code": -1,  # timeout sentinel — caller compares != 0
                "stdout_tail": tail_out,
                "stderr_tail": tail_err,
                "csv_path": csv_path,
                "summary_path": summary_path,
                "duration_sec": duration,
                "command": command,
            }
        except subprocess.CalledProcessError as e:
            # check=False above means CalledProcessError shouldn't fire from
            # the real subprocess module — but tests may inject it, and a
            # future refactor could enable check=True. Handle defensively.
            duration = time.monotonic() - start
            log.warning("phase0_runner CalledProcessError: %s", e)
            return {
                "status": "failed",
                "exit_code": int(getattr(e, "returncode", 1) or 1),
                "stdout_tail": self._tail(_stringify(getattr(e, "stdout", ""))),
                "stderr_tail": self._tail(_stringify(getattr(e, "stderr", str(e)))),
                "csv_path": csv_path,
                "summary_path": summary_path,
                "duration_sec": duration,
                "command": command,
            }
        except Exception as e:  # OSError, FileNotFoundError, anything else
            duration = time.monotonic() - start
            log.warning("phase0_runner subprocess raised %s: %s", type(e).__name__, e)
            return {
                "status": "failed",
                "exit_code": -1,
                "stdout_tail": "",
                "stderr_tail": self._tail(f"{type(e).__name__}: {e}"),
                "csv_path": csv_path,
                "summary_path": summary_path,
                "duration_sec": duration,
                "command": command,
            }

        duration = time.monotonic() - start
        stdout_tail = self._tail(proc.stdout or "")
        stderr_tail = self._tail(proc.stderr or "")
        status = "ok" if proc.returncode == 0 else "failed"
        return {
            "status": status,
            "exit_code": int(proc.returncode),
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "csv_path": csv_path,
            "summary_path": summary_path,
            "duration_sec": duration,
            "command": command,
        }

    # ---- internals ---------------------------------------------------------

    def _build_command(
        self,
        *,
        since: str,
        symbols: list[str],
        csv_path: str,
        summary_path: str,
    ) -> list[str]:
        """Assemble the argv list — keeps run() readable."""
        symbols_arg = ",".join(symbols)
        return [
            self._python,
            self._script_path,
            "--since", since,
            "--symbols", symbols_arg,
            "--out", csv_path,
            "--summary", summary_path,
        ]

    @staticmethod
    def _default_since_iso_z() -> str:
        """Now - 7d, ISO 8601 with trailing Z (UTC). Matches the script's
        --since contract (UTC lower bound for closed_at)."""
        ts = datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        # %Y-%m-%dT%H:%M:%SZ — seconds precision is enough for the script.
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _tail(text: str) -> str:
        """Return at most _TAIL_BYTES chars from the *end* of `text`.

        We slice on str length (not bytes) — extract_sl_evidence.py is
        ASCII/UTF-8 friendly and the 1KB ceiling is a soft cap for log volume."""
        if not text:
            return ""
        if len(text) <= _TAIL_BYTES:
            return text
        return text[-_TAIL_BYTES:]


def _stringify(value: object) -> str:
    """Coerce TimeoutExpired's stdout/stderr (may be bytes) to str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    return str(value)
