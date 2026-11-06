"""Telegram community-channel collector — channel posts → Lane A-shaped JSONL.

The community channel carries **two** message shapes on one feed:

- bot trade posts (``engine/notifications/telegram_notifier.py``,
  ``EFLOUD_CUSTOMER_TG_TRADES``) — see ``docs/telegram/community-channel.md``;
- ``u2algo Price Action`` indicator alerts (TradingView webhook) — see
  ``docs/telegram/tradingview-to-telegram.md``.

The Bot API cannot read channel history: ``getUpdates`` only returns **new**
``channel_post`` updates while the bot is a channel admin, and returns nothing at
all once a webhook is set. So this module is a small accumulator: every poll
parses the new posts and appends one JSON object per line to
``{out_dir}/{YYYY-MM-DD}.jsonl``, the exact directory layout Lane B reads.

Event shape is Lane A *compatible* (``docs/schemas/content_job-1.0.0.json``) with
one deliberate deviation: ``source.service`` is ``telegram-channel-collector``,
not ``efloud-bot``, because the bot did not produce these events. The schema
pins that field to a const, so these rows are validated against the schema
*minus* that const (see ``validate_event``). Do not "fix" it to ``efloud-bot``:
that would attribute collector output to the trading bot.

Idempotent on ``(chat_id, message_id)``: ``event_id`` is a UUIDv5 of that pair,
so re-polling the same post never produces a second event.

Read-only with respect to trading: no orders, no config, no state outside
``state_path`` and ``out_dir``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.content_jobs import COMPLIANCE_EN, COMPLIANCE_TR, SCHEMA_VERSION

log = logging.getLogger("efloud.tg_collector")

COLLECTOR_SERVICE = "telegram-channel-collector"
DEFAULT_TIMEFRAME = "15m"
DEFAULT_CONFLUENCE = 60
API_BASE = "https://api.telegram.org"

# Fixed namespace so event_id is stable across machines and runs.
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://u2algo.com/telegram-channel-collector")

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]"
)
_FIELD = re.compile(
    r"^(Entry|SL|TP1|TP2|Setup|Exit|Neden\s*/\s*Reason|Sonu\u00e7\s*/\s*Result)"
    r"\s*:\s*(.+)$",
    re.IGNORECASE,
)
_CONFLUENCE = re.compile(r"confluence\s*:\s*(\d{1,3})", re.IGNORECASE)
_QUOTES = ("USDT", "USDC", "USD", "BTC", "ETH")
_NULLISH = {"", "-", "--", "\u2014", "\u2013", "n/a", "none", "null"}


class CollectorError(Exception):
    """The channel feed could not be read (API error, bad config, webhook set)."""


# ── parsing ─────────────────────────────────────────────────────────────────

def _clean(line: str) -> str:
    """Strip emoji + the Markdown the bot posts with, keep the text."""
    return _EMOJI.sub("", line or "").replace("*", "").replace("`", "").strip()


def _num(raw: Optional[str]) -> Optional[float]:
    """Parse a posted price. ``_fmt_price`` writes thousands separators."""
    if raw is None:
        return None
    v = str(raw).strip().replace(",", "").replace("\u00a0", "")
    if v.lower() in _NULLISH:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def normalize_symbol(raw: str) -> Optional[str]:
    """``BTCUSDT.P`` / ``BTCUSDT`` / ``BTC/USDT`` → ``BTC/USDT``."""
    s = (raw or "").strip().upper().replace("/", "").replace("-", "")
    if s.endswith(".P"):
        s = s[:-2]
    for q in _QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[: -len(q)]}/{q}"
    return None


def normalize_timeframe(raw: Optional[str]) -> Optional[str]:
    """``15`` → ``15m``; ``1h``/``4h``/``1d`` pass through."""
    if not raw:
        return None
    v = raw.strip().lower()
    if v.isdigit():
        return f"{int(v)}m"
    if re.fullmatch(r"\d+[mhdw]", v):
        return v
    return None


def _parse_fields(lines: Iterable[str]) -> dict:
    """Collect ``Key: value`` pairs; handles ``Entry: x → TP1: y`` arrows."""
    out: dict[str, str] = {}
    for line in lines:
        # Split on the raw arrow first: _clean() strips the arrows block, so
        # cleaning before the split would glue "Entry: x" and "Exit: y" together.
        for segment in (line or "").split("\u2192"):
            m = _FIELD.match(_clean(segment))
            if not m:
                continue
            key = re.sub(r"\s*/\s*.*$", "", m.group(1)).strip().lower()
            out.setdefault(key, m.group(2).strip())
    return out


def _parse_header(line: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return ``(symbol, direction, timeframe)`` from the post's first line."""
    head = _clean(line)
    head = head.split("\u2014")[0]  # bot: "BTCUSDT LONG — yeni işlem / new trade"
    tf_raw = None
    if "\u00b7" in head:  # indicator: "LONG BTCUSDT.P · 15"
        head, _, tf_raw = head.partition("\u00b7")
    tokens = head.split()
    direction = symbol = None
    if len(tokens) >= 2:
        if tokens[0].upper() in ("LONG", "SHORT"):
            direction, symbol = tokens[0].upper(), tokens[1]
        elif tokens[1].upper() in ("LONG", "SHORT"):
            symbol, direction = tokens[0], tokens[1].upper()
    return (normalize_symbol(symbol) if symbol else None), direction, normalize_timeframe(tf_raw)


def parse_channel_post(text: str) -> Optional[dict]:
    """Parse one channel post into a normalized dict, or ``None`` if unknown.

    ``kind`` is ``opened`` / ``tp1_hit`` / ``closed``. Only ``opened`` carries
    the entry/SL/TP1 triple a chart needs; the other two are recorded so the
    feed stays complete but are not turned into social drafts.
    """
    if not text or not text.strip():
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    symbol, direction, timeframe = _parse_header(lines[0])
    if not symbol or not direction:
        return None

    low = _clean(text).lower()
    if "tp1 hit" in low:
        kind = "tp1_hit"
    elif "trade closed" in low or "i\u015flem kapand\u0131" in low:
        kind = "closed"
    else:
        kind = "opened"

    fields = _parse_fields(lines[1:])
    conf = _CONFLUENCE.search(_clean(text))
    return {
        "kind": kind,
        "symbol": symbol,
        "direction": direction,
        "timeframe": timeframe,
        "entry": _num(fields.get("entry")),
        "sl": _num(fields.get("sl")),
        "tp1": _num(fields.get("tp1")),
        "tp2": _num(fields.get("tp2")),
        "exit": _num(fields.get("exit")),
        "setup": fields.get("setup") or None,
        "reason": fields.get("neden") or None,
        "confluence": int(conf.group(1)) if conf else None,
        "origin": "indicator" if timeframe else "bot",
    }


def to_content_job(
    parsed: dict,
    *,
    chat_id: str | int,
    message_id: int,
    occurred_at: str,
    env: str = "mainnet",
    default_timeframe: str = DEFAULT_TIMEFRAME,
    default_confluence: int = DEFAULT_CONFLUENCE,
) -> Optional[dict]:
    """Turn a parsed post into a Lane A-shaped ``content_job`` event.

    Returns ``None`` for anything that is not a fresh entry (``tp1_hit`` /
    ``closed``) or that lacks the entry/SL/TP1 triple.

    ``confluence`` is required by the schema as an integer, but channel posts do
    not carry a score. When the post has none, ``default_confluence`` is written
    and ``signal.reasons_detail.confluence_source`` records that it is a
    placeholder, never a measured score.
    """
    if parsed.get("kind") != "opened":
        return None
    entry, sl, tp1 = parsed.get("entry"), parsed.get("sl"), parsed.get("tp1")
    if not entry or not sl or not tp1:
        return None

    tf = parsed.get("timeframe") or default_timeframe
    conf = parsed.get("confluence")
    conf_source = "channel_post" if conf is not None else "channel_default"
    if conf is None:
        conf = int(default_confluence)

    setup = parsed.get("setup")
    return {
        "event_id": str(uuid.uuid5(_NS, f"{chat_id}:{message_id}")),
        "event_type": "content_job.position_opened",
        "schema_version": SCHEMA_VERSION,
        "occurred_at": occurred_at,
        "source": {
            "service": COLLECTOR_SERVICE,
            "env": env,
            "channel_id": str(chat_id),
            "message_id": int(message_id),
            "origin": parsed.get("origin"),
        },
        "signal": {
            "symbol": parsed["symbol"],
            "direction": parsed["direction"],
            "entry": float(entry),
            "sl": float(sl),
            "tp1": float(tp1),
            "tp2": float(parsed["tp2"]) if parsed.get("tp2") else None,
            "confluence": conf,
            "timeframe": tf,
            "reasons": [setup] if setup else [],
            "reasons_detail": {
                "confluence_source": conf_source,
                "timeframe_source": "channel_post" if parsed.get("timeframe") else "default",
                "setup": setup,
            },
        },
        "compliance": {
            "disclaimer_tr": COMPLIANCE_TR,
            "disclaimer_en": COMPLIANCE_EN,
            "no_guarantee": True,
        },
    }


def validate_event(event: dict) -> list[str]:
    """Validate against the Lane A schema, allowing the collector's service name.

    Returns a list of error strings (empty == valid). ``source.service`` is
    relaxed on purpose — see the module docstring.
    """
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - optional dependency
        return []
    schema_path = _ROOT / "docs" / "schemas" / f"content_job-{SCHEMA_VERSION}.json"
    if not schema_path.exists():  # pragma: no cover - packaging guard
        return []
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema = json.loads(json.dumps(schema))
    schema["properties"]["source"]["properties"]["service"] = {"type": "string"}
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.path)}: {e.message}"
            for e in sorted(validator.iter_errors(event), key=lambda e: list(e.path))]


# ── transport ───────────────────────────────────────────────────────────────

def http_get_updates(token: str, params: dict, *, timeout: float = 10.0) -> dict:
    """Default transport: one ``getUpdates`` call. Token never leaves the URL."""
    url = f"{API_BASE}/bot{token}/getUpdates?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # network / HTTP error body
        raise CollectorError(f"getUpdates failed: {type(e).__name__}: {e}") from e


Transport = Callable[[dict], dict]


# ── collector ───────────────────────────────────────────────────────────────

class TelegramChannelCollector:
    """Poll new channel posts and append them to a per-day Lane A JSONL feed."""

    def __init__(
        self,
        *,
        out_dir,
        state_path,
        channel_id: str | int,
        token: Optional[str] = None,
        transport: Optional[Transport] = None,
        env: str = "mainnet",
        default_timeframe: str = DEFAULT_TIMEFRAME,
        default_confluence: int = DEFAULT_CONFLUENCE,
        limit: int = 100,
    ):
        self.out_dir = Path(out_dir)
        self.state_path = Path(state_path)
        self.channel_id = str(channel_id)
        self.token = token
        self.transport = transport
        self.env = env
        self.default_timeframe = default_timeframe
        self.default_confluence = int(default_confluence)
        self.limit = int(limit)

    # ── state ───────────────────────────────────────────────────────────────
    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {"last_update_id": 0, "seen": []}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("tg_collector_state_load_failed err=%s", e)
            return {"last_update_id": 0, "seen": []}
        if not isinstance(data, dict):
            return {"last_update_id": 0, "seen": []}
        data.setdefault("last_update_id", 0)
        data.setdefault("seen", [])
        return data

    def _save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.state_path) + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    def _seen_from_feed(self) -> set[str]:
        """Event ids already on disk — dedupe survives a lost state file."""
        seen: set[str] = set()
        if not self.out_dir.exists():
            return seen
        for f in sorted(self.out_dir.glob("*.jsonl")):
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        eid = json.loads(line).get("event_id")
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    if eid:
                        seen.add(eid)
            except OSError as e:
                log.warning("tg_collector_feed_read_failed file=%s err=%s", f.name, e)
        return seen

    # ── append ──────────────────────────────────────────────────────────────
    def _append(self, event: dict) -> Path:
        date = str(event["occurred_at"])[:10]
        self.out_dir.mkdir(parents=True, exist_ok=True)
        target = self.out_dir / f"{date}.jsonl"
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n")
        return target

    # ── one poll ────────────────────────────────────────────────────────────
    def collect(self) -> dict:
        state = self._load_state()
        seen = set(state.get("seen") or []) | self._seen_from_feed()
        offset = int(state.get("last_update_id") or 0) + 1

        if self.transport is None:
            if not self.token:
                raise CollectorError(
                    "no token: set EFLOUD_CUSTOMER_TG_TOKEN or inject a transport")
            transport = lambda params: http_get_updates(self.token, params)  # noqa: E731
        else:
            transport = self.transport

        data = transport({
            "offset": offset,
            "timeout": 0,
            "limit": self.limit,
            "allowed_updates": json.dumps(["channel_post"]),
        })
        if not isinstance(data, dict) or not data.get("ok"):
            desc = (data or {}).get("description") if isinstance(data, dict) else None
            raise CollectorError(f"getUpdates not ok: {desc or data!r}")

        updates = data.get("result") or []
        written = skipped_other_chat = skipped_unparsed = skipped_kind = duplicates = 0
        last_update_id = int(state.get("last_update_id") or 0)

        for u in updates:
            if not isinstance(u, dict):
                continue
            last_update_id = max(last_update_id, int(u.get("update_id") or 0))
            post = u.get("channel_post") or u.get("edited_channel_post") or {}
            chat_id = str((post.get("chat") or {}).get("id", ""))
            if chat_id != self.channel_id:
                skipped_other_chat += 1
                continue
            text = post.get("text") or post.get("caption") or ""
            parsed = parse_channel_post(text)
            if parsed is None:
                skipped_unparsed += 1
                log.info("tg_collector_unparsed message_id=%s", post.get("message_id"))
                continue
            occurred = datetime.fromtimestamp(
                int(post.get("date") or 0), tz=timezone.utc
            ).isoformat().replace("+00:00", "Z")
            event = to_content_job(
                parsed,
                chat_id=self.channel_id,
                message_id=int(post.get("message_id") or 0),
                occurred_at=occurred,
                env=self.env,
                default_timeframe=self.default_timeframe,
                default_confluence=self.default_confluence,
            )
            if event is None:
                skipped_kind += 1
                continue
            if event["event_id"] in seen:
                duplicates += 1
                continue
            self._append(event)
            seen.add(event["event_id"])
            written += 1

        state["last_update_id"] = last_update_id
        state["seen"] = sorted(seen)[-5000:]
        self._save_state(state)

        return {
            "updates": len(updates),
            "written": written,
            "duplicates": duplicates,
            "skipped_other_chat": skipped_other_chat,
            "skipped_unparsed": skipped_unparsed,
            "skipped_kind": skipped_kind,
            "last_update_id": last_update_id,
            "out_dir": str(self.out_dir),
        }

    # ── offline ingest (fixtures / replay) ──────────────────────────────────
    def ingest_posts(self, posts: Iterable[dict]) -> dict:
        """Append already-fetched posts (``message_id``/``date``/``text``).

        Used by the dry-run and the tests so the whole feed path can be
        exercised without a bot token or a network call.
        """
        state = self._load_state()
        seen = set(state.get("seen") or []) | self._seen_from_feed()
        written = skipped_unparsed = skipped_kind = duplicates = 0
        for p in posts:
            parsed = parse_channel_post(p.get("text") or "")
            if parsed is None:
                skipped_unparsed += 1
                continue
            occurred = p.get("occurred_at") or datetime.fromtimestamp(
                int(p.get("date") or 0), tz=timezone.utc
            ).isoformat().replace("+00:00", "Z")
            event = to_content_job(
                parsed,
                chat_id=p.get("chat_id", self.channel_id),
                message_id=int(p.get("message_id") or 0),
                occurred_at=occurred,
                env=self.env,
                default_timeframe=self.default_timeframe,
                default_confluence=self.default_confluence,
            )
            if event is None:
                skipped_kind += 1
                continue
            if event["event_id"] in seen:
                duplicates += 1
                continue
            self._append(event)
            seen.add(event["event_id"])
            written += 1
        state["seen"] = sorted(seen)[-5000:]
        self._save_state(state)
        return {
            "written": written,
            "duplicates": duplicates,
            "skipped_unparsed": skipped_unparsed,
            "skipped_kind": skipped_kind,
            "out_dir": str(self.out_dir),
        }


def main(argv: Optional[list[str]] = None) -> dict:
    """CLI: poll the channel once (or replay a fixture) into the JSONL feed."""
    import argparse

    ap = argparse.ArgumentParser(
        description="Telegram community channel → Lane A-shaped JSONL feed")
    ap.add_argument("--out", default=os.environ.get(
        "EFLOUD_TG_FEED_DIR", "/app/data/content_jobs"))
    ap.add_argument("--state", default=os.environ.get(
        "EFLOUD_TG_COLLECTOR_STATE", "state/tg_collector/state.json"))
    ap.add_argument("--channel-id", default=os.environ.get("EFLOUD_CUSTOMER_TG_CHANNEL_ID"))
    ap.add_argument("--from-file", default=None,
                    help="replay posts from a JSON fixture instead of calling the API")
    ap.add_argument("--default-timeframe", default=DEFAULT_TIMEFRAME)
    ap.add_argument("--default-confluence", type=int, default=DEFAULT_CONFLUENCE)
    args = ap.parse_args(argv)

    if not args.channel_id:
        raise SystemExit("--channel-id (or EFLOUD_CUSTOMER_TG_CHANNEL_ID) is required")

    collector = TelegramChannelCollector(
        out_dir=args.out, state_path=args.state, channel_id=args.channel_id,
        token=os.environ.get("EFLOUD_CUSTOMER_TG_TOKEN"),
        default_timeframe=args.default_timeframe,
        default_confluence=args.default_confluence,
    )
    if args.from_file:
        posts = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        summary = collector.ingest_posts(posts)
    else:
        summary = collector.collect()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


__all__ = [
    "CollectorError", "COLLECTOR_SERVICE", "DEFAULT_TIMEFRAME", "DEFAULT_CONFLUENCE",
    "normalize_symbol", "normalize_timeframe", "parse_channel_post",
    "to_content_job", "validate_event", "http_get_updates",
    "TelegramChannelCollector", "main",
]


if __name__ == "__main__":  # pragma: no cover
    main()
