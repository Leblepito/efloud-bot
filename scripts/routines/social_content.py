"""social_content rutini — her 4 saatte X/Instagram içerik üretimi.

Akış (P-Kronos-Social):
  1. Gate: ``SOCIAL_CONTENT_ENABLED`` truthy değilse no-op (fail-closed).
  2. Slot-dedup: aynı UTC gün+slot için ikinci üretim yapılmaz
     (watcher restart'ında duplicate post zinciri engellenir).
  3. Girdi topla: 3-bot healthz durumu, açık pozisyon sayısı,
     Kronos cascade JSON (``scripts.kronos_service`` çıktısı, bayatsa yok say).
  4. ``backend.social.generators`` ile EN+RU draft'lar üret.
  5. Compliance gate (``scripts.content_compliance.find_violations``) →
     ihlalli draft DÜŞÜRÜLÜR (asla kuyruğa girmez).
  6. Persist: DATABASE_URL varsa content_drafts tablosuna
     PENDING_REVIEW (``SOCIAL_AUTOPILOT=1`` ise APPROVED) olarak yazılır;
     DB yoksa ``data/social_outbox.jsonl``'a düşer (dry ortam).
  7. Operatöre Telegram bildirimi (runner'ın AlertRouter'ı üzerinden).

Yayın bu rutinde YAPILMAZ — APPROVED draft'ları mevcut
``backend.social.publishing_worker`` (60s poll) X/Instagram'a basar.
Trade path'e sıfır dokunuş.

Env:
    SOCIAL_CONTENT_ENABLED  default off  — ana şalter
    SOCIAL_AUTOPILOT        default off  — 1: onaysız yayın (APPROVED yazılır)
    SOCIAL_LANGS            default "en,ru"
    SOCIAL_PLATFORMS        default "x"  — IG hazır olunca "x,instagram"
    EFLOUD_PEER_BOTS        default "mid=http://efloud-bot:8080,long=http://efloud-bot-long:8080,scalp=http://efloud-bot-scalp:8080"
    KRONOS_OUTPUT_PATH      default data/market/kronos_cascade.json
    KRONOS_MAX_AGE_SEC      default 28800 (8h — 2 döngü)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.routines.runner import register
from scripts.routines._base import (
    RoutineResult,
    now_utc,
    read_state_json,
    resolve_state_dir,
    unwrap_state,
    write_snapshot,
)

# Bot TF etiketleri (data/timeframes.py PROFILES ile uyumlu, sadece kozmetik).
_PROFILE_TFS = {"scalp": "5m/1h/12h", "mid": "15m/1h/4h", "long": "1h/8h/1w"}

_DEFAULT_PEERS = (
    "mid=http://efloud-bot:8080,"
    "long=http://efloud-bot-long:8080,"
    "scalp=http://efloud-bot-scalp:8080"
)

OUTBOX_PATH = "data/social_outbox.jsonl"
STATE_PATH_NAME = "social_content_state.json"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


# ────────────────────────── Girdi toplayıcılar ──────────────────────────


def collect_fleet() -> dict:
    """3 botun healthz durumu + (best-effort) açık pozisyon sayısı."""
    peers_raw = os.environ.get("EFLOUD_PEER_BOTS", _DEFAULT_PEERS)
    bots: dict[str, dict] = {}
    for pair in peers_raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, base = pair.split("=", 1)
        name = name.strip()
        up = False
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{base.strip().rstrip('/')}/healthz")
                up = r.status_code == 200
        except Exception:
            up = False
        bots[name] = {"up": up, "tf": _PROFILE_TFS.get(name, "")}

    fleet: dict = {"bots": bots, "open_positions": None, "signals_24h": None}

    # V1 canlı state'inden açık pozisyon sayısı (routines container'ı
    # state_1k'yı mount ediyor — R-1/R-3 pattern'i).
    try:
        state_dir = resolve_state_dir()
        positions = unwrap_state(read_state_json(f"{state_dir}/positions.json"))
        if isinstance(positions, dict):
            open_pos = positions.get("positions", positions)
            if isinstance(open_pos, dict):
                fleet["open_positions"] = len(open_pos)
            elif isinstance(open_pos, list):
                fleet["open_positions"] = len(open_pos)
    except Exception:
        pass

    # signal_ledger.jsonl → son 24h sinyal sayısı (best-effort).
    try:
        ledger = Path(resolve_state_dir()) / "signal_ledger.jsonl"
        if ledger.exists():
            cutoff = now_utc().timestamp() - 86400
            count = 0
            with ledger.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    ts = rec.get("ts") or rec.get("timestamp") or rec.get("created_at")
                    if isinstance(ts, (int, float)) and ts >= cutoff:
                        count += 1
                    elif isinstance(ts, str):
                        try:
                            if datetime.fromisoformat(
                                ts.replace("Z", "+00:00")
                            ).timestamp() >= cutoff:
                                count += 1
                        except ValueError:
                            continue
            fleet["signals_24h"] = count
    except Exception:
        pass

    return fleet


def load_kronos() -> dict | None:
    """Kronos cascade JSON'u oku; yoksa/bayatsa None."""
    path = Path(os.environ.get("KRONOS_OUTPUT_PATH", "data/market/kronos_cascade.json"))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    max_age = int(os.environ.get("KRONOS_MAX_AGE_SEC", "28800"))
    try:
        gen = datetime.fromisoformat(str(data.get("generated_at", "")))
        age = (now_utc() - gen).total_seconds()
        if age > max_age:
            return None
    except ValueError:
        return None
    return data


# ────────────────────────── Persist ──────────────────────────


def _persist_db(drafts: list, autopilot: bool) -> int:
    """content_drafts tablosuna yaz. Dönen: yazılan draft sayısı.

    Kısa ömürlü tek bağlantılık pool — Supabase pooler (pgbouncer) için
    statement_cache_size=0 zorunlu.
    """
    import asyncio

    import asyncpg

    from backend.social.content_queue import (
        approve_draft,
        create_draft,
        submit_for_review,
    )
    from backend.social.queue_storage import ensure_schema, save_draft

    dsn = os.environ.get("DATABASE_URL", "")

    async def _run() -> int:
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=1, statement_cache_size=0
        )
        written = 0
        try:
            await ensure_schema(pool)
            for spec in drafts:
                draft = create_draft(spec.body, spec.lang, spec.post_type, spec.meta)
                submit_for_review(draft, {"violation_count": 0, "violations": []})
                if autopilot:
                    approve_draft(draft, "autopilot")
                await save_draft(pool, draft)
                written += 1
        finally:
            await pool.close()
        return written

    return asyncio.run(_run())


def _persist_outbox(drafts: list, autopilot: bool) -> int:
    """DB yok — JSONL outbox'a düş (dry ortam / smoke test)."""
    path = Path(OUTBOX_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for spec in drafts:
            f.write(
                json.dumps(
                    {
                        "ts": now_utc().isoformat(),
                        "body": spec.body,
                        "lang": spec.lang,
                        "post_type": spec.post_type,
                        "meta": spec.meta,
                        "status": "approved" if autopilot else "pending_review",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return len(drafts)


# ────────────────────────── Rutin ──────────────────────────


@register("social_content")
def main(client=None, alert=None, cfg=None) -> RoutineResult:
    name = "social_content"

    if not _truthy("SOCIAL_CONTENT_ENABLED"):
        return RoutineResult(name, ok=True)

    from backend.social.generators import build_cycle_drafts, slot_index_for_hour
    from scripts.content_compliance import find_violations

    now = now_utc()
    slot = slot_index_for_hour(now.hour)
    slot_key = f"{now.date().isoformat()}:{slot}"

    # Slot-dedup — watcher restart'ında aynı slot ikinci kez üretilmesin.
    state_path = f"{resolve_state_dir(cfg)}/{STATE_PATH_NAME}"
    prev = read_state_json(state_path)
    if prev.get("last_slot_key") == slot_key:
        return RoutineResult(name, ok=True)

    autopilot = _truthy("SOCIAL_AUTOPILOT")
    langs = tuple(
        s.strip() for s in os.environ.get("SOCIAL_LANGS", "en,ru").split(",") if s.strip()
    )
    platforms = tuple(
        s.strip()
        for s in os.environ.get("SOCIAL_PLATFORMS", "x").split(",")
        if s.strip()
    )

    fleet = collect_fleet()
    kronos = load_kronos()

    specs = build_cycle_drafts(
        slot=slot,
        day_ordinal=now.toordinal(),
        kronos=kronos,
        fleet=fleet,
        langs=langs,
        platforms=platforms,
    )

    # Compliance gate — ihlalli draft kuyruğa GİRMEZ.
    clean, dropped = [], []
    for spec in specs:
        violations = find_violations(spec.body, lang="all")
        if violations:
            dropped.append((spec, violations))
        else:
            clean.append(spec)

    written = 0
    persist_error = None
    if clean:
        try:
            if os.environ.get("DATABASE_URL", "").strip():
                written = _persist_db(clean, autopilot)
            else:
                written = _persist_outbox(clean, autopilot)
        except Exception as exc:
            persist_error = str(exc)
            # DB düştüyse outbox'a düşmeyi dene — içerik kaybolmasın.
            try:
                written = _persist_outbox(clean, autopilot)
                persist_error += " (outbox fallback OK)"
            except Exception as exc2:
                persist_error += f" (outbox fallback da düştü: {exc2})"

    # Slot'u ancak bir şey yazabildiysek işaretle — tamamen boş geçen
    # koşu sonraki watcher turunda yeniden denesin.
    if written:
        write_snapshot(state_path, {"last_slot_key": slot_key, "written": written})

    breaches = []
    if written:
        mode = "AUTOPILOT — yayına gidecek" if autopilot else "onay bekliyor (dashboard → Social)"
        breaches.append(
            {
                "severity": "info",
                "key": f"social_content:{slot_key}",
                "title": f"Social: {written} draft hazır ({mode})",
                "body": "; ".join(
                    f"[{s.lang}/{s.post_type}] {s.body[:80]}…" for s in clean[:4]
                ),
            }
        )
    if dropped:
        breaches.append(
            {
                "severity": "warning",
                "key": f"social_content_dropped:{slot_key}",
                "title": f"Social: {len(dropped)} draft compliance'a takıldı",
                "body": "; ".join(
                    f"[{s.lang}] {', '.join(v)}" for s, v in dropped[:4]
                ),
            }
        )
    if persist_error:
        breaches.append(
            {
                "severity": "warning",
                "key": f"social_content_persist:{now.date().isoformat()}",
                "title": "Social: persist hatası",
                "body": persist_error[:400],
            }
        )

    return RoutineResult(name, ok=persist_error is None, breaches=breaches)
