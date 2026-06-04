"""
Lane A Content Job Emitter
━━━━━━━━━━━━━━━━━━━━━━━━━━
Bot sinyal/pozisyon event'ini JSONL dosyaya yazar. Consumer (Lane B/C/D/E/F)
okur. Default OFF. Trade execution'a sifir dokunus.

Spec: docs/superpowers/specs/2026-06-04-content-jobs-consumer-design.md
Schema: docs/schemas/content_job-1.0.0.json
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import jsonschema
except ImportError:
    jsonschema = None

log = logging.getLogger("efloud.content_jobs")

SCHEMA_VERSION = "1.0.0"
COMPLIANCE_TR = "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir."
COMPLIANCE_EN = "Not investment advice. Trade at your own risk."
_DEFAULT_PATH = "/app/data/content_jobs"


def _enabled() -> bool:
    return os.environ.get("EFLOUD_CONTENT_EMITTER_ENABLED", "").lower() in ("1", "true", "yes")


def _base_path() -> Path:
    return Path(os.environ.get("EFLOUD_CONTENT_JOBS_PATH", _DEFAULT_PATH))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_commit() -> Optional[str]:
    """Container'da /app/.git/HEAD -> commit."""
    try:
        head = Path("/app/.git/HEAD")
        if not head.exists():
            return None
        ref = head.read_text().strip().split(" ", 1)[-1]
        cp = Path(f"/app/.git/{ref}")
        return cp.read_text().strip()[:12] if cp.exists() else None
    except Exception:
        return None


class ContentJobEmitter:
    """Tek dosyaya atomik JSONL append. Per-day rotation. Hata -> log + drop."""

    def __init__(self, base_path: Optional[Path] = None, env: str = "mainnet",
                 loop_id: Optional[str] = None):
        self.base_path = base_path or _base_path()
        self.env = env
        self.loop_id = loop_id or str(uuid.uuid4())
        self.commit = _git_commit()
        # Single-process lock: efloud-bot tek container ama thread-safe yap.
        # Dosya O_APPEND POSIX atomic ama Python write + flush + fsync 3 syscall,
        # aralarinda race olabilir. Lock ile sequentialize.
        self._lock = threading.Lock()

    def _schema(self) -> Optional[dict]:
        sp = Path(__file__).parent.parent / "docs" / "schemas" / f"content_job-{SCHEMA_VERSION}.json"
        if not sp.exists():
            sp = Path("docs/schemas") / f"content_job-{SCHEMA_VERSION}.json"
        if not sp.exists():
            return None
        try:
            return json.loads(sp.read_text())
        except Exception as e:
            log.warning("content_jobs_schema_load_failed err=%s", e)
            return None

    def _file(self) -> Path:
        return self.base_path / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"

    def _append(self, line: str) -> bool:
        """O_APPEND + fsync + lock. Concurrent thread'ler sequentialize."""
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error("content_jobs_mkdir_failed path=%s err=%s", self.base_path, e)
            return False
        target = self._file()
        with self._lock:
            try:
                with open(target, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                return True
            except OSError as e:
                log.error("content_jobs_write_failed err=%s", e)
                return False

    def emit(self, event_type: str, signal: dict, execution: Optional[dict] = None) -> bool:
        if not _enabled():
            return False
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "schema_version": SCHEMA_VERSION,
            "occurred_at": _now_iso(),
            "source": {"service": "efloud-bot", "env": self.env,
                       "commit": self.commit, "loop_id": self.loop_id},
            "signal": signal,
            "compliance": {"disclaimer_tr": COMPLIANCE_TR,
                           "disclaimer_en": COMPLIANCE_EN, "no_guarantee": True},
        }
        if execution is not None:
            event["execution"] = execution
        schema = self._schema()
        if schema and jsonschema:
            try:
                jsonschema.validate(event, schema)
            except jsonschema.ValidationError as e:
                log.error("content_jobs_schema_violation err=%s", e.message)
                return False
        return self._append(json.dumps(event, separators=(",", ":"), ensure_ascii=False))


__all__ = ["ContentJobEmitter", "SCHEMA_VERSION"]
