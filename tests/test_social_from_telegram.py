"""Tests — Telegram community channel → Instagram/X social drafts.

Covers the two new modules only; the Lane B→G chain they drive is already
covered by ``tests/test_social_publishing.py`` and ``tests/test_lane_g_publish.py``.

  telegram_channel_collector  post parsing (both message shapes), symbol/TF
                              normalisation, Lane A-shaped event build, schema
                              validation, getUpdates polling + idempotency
  social_from_telegram        draft → approve → publish verbs, bundle export,
                              compliance of every caption, default-closed gates

Every test is offline and deterministic: the Telegram API is replaced by an
injected transport, candles are synthesised into a local parquet cache, and no
publisher is ever constructed with credentials.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine.content_jobs import COMPLIANCE_TR
from scripts.content_compliance import find_violations, has_disclaimer
from scripts.social_from_telegram import (
    approve,
    draft,
    export_bundles,
    publish,
)
from scripts.telegram_channel_collector import (
    COLLECTOR_SERVICE,
    CollectorError,
    TelegramChannelCollector,
    normalize_symbol,
    normalize_timeframe,
    parse_channel_post,
    to_content_job,
    validate_event,
)

FIXTURE = Path(__file__).parent / "fixtures" / "telegram_channel_posts_2026-11-06.json"
CHAT = "-1002000000001"
DATE = "2026-11-06"

BOT_POST = (
    "🟢 *BTCUSDT LONG* — yeni işlem / new trade\n"
    "Entry: `76,186.0`\nSL: `75,700.0`\nTP1: `77,150.0`\nTP2: `78,100.0`\n"
    "Setup: OB BREAKER+OTE\nu2algo Price Action"
)
INDICATOR_POST = (
    "🔴 SHORT ETHUSDT.P · 15\nEntry: 2245.46\nSL: 2271.2\nTP1: 2201.5\n"
    "TP2: —\nSetup: FVG RETEST\nu2algo Price Action"
)


def _fixture_posts() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _seed_cache(cache_dir: Path, symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT")) -> Path:
    """Write a deterministic 15m parquet cache so charts render offline."""
    from data.cache import OHLCVCache

    cache = OHLCVCache(cache_dir)
    idx = pd.date_range("2026-11-05T12:00:00Z", periods=120, freq="15min")
    for i, sym in enumerate(symbols):
        base = 100.0 * (i + 1)
        close = pd.Series(
            [base + ((n % 7) - 3) * 0.15 for n in range(len(idx))], index=idx
        )
        df = pd.DataFrame({
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 10.0,
        })
        cache.put(sym, "15m", df)
    return cache_dir


# ── parsing ─────────────────────────────────────────────────────────────────

def test_parse_bot_opened_post():
    p = parse_channel_post(BOT_POST)
    assert p["kind"] == "opened"
    assert p["symbol"] == "BTC/USDT"
    assert p["direction"] == "LONG"
    assert p["entry"] == 76186.0
    assert p["sl"] == 75700.0
    assert p["tp1"] == 77150.0
    assert p["tp2"] == 78100.0
    assert p["setup"] == "OB BREAKER+OTE"
    assert p["timeframe"] is None
    assert p["origin"] == "bot"


def test_parse_indicator_post_carries_timeframe():
    p = parse_channel_post(INDICATOR_POST)
    assert p["kind"] == "opened"
    assert p["symbol"] == "ETH/USDT"
    assert p["direction"] == "SHORT"
    assert p["timeframe"] == "15m"
    assert p["tp2"] is None  # "—" is a null, not a price
    assert p["origin"] == "indicator"


@pytest.mark.parametrize("text,kind", [
    ("🎯 *BTCUSDT LONG* — TP1 hit\nEntry: `76,186.0` → TP1: `77,150.0`", "tp1_hit"),
    ("🏁 *ETHUSDT SHORT* — işlem kapandı / trade closed\n"
     "Entry: `2,245.46` → Exit: `2,201.5`", "closed"),
])
def test_parse_lifecycle_posts(text, kind):
    p = parse_channel_post(text)
    assert p["kind"] == kind
    assert p["symbol"] in ("BTC/USDT", "ETH/USDT")


def test_parse_arrow_line_splits_both_fields():
    text = ("🏁 *ETHUSDT SHORT* — trade closed" + chr(10)
            + "Entry: `2,245.46` → Exit: `2,201.5`")
    p = parse_channel_post(text)
    assert p["entry"] == 2245.46
    assert p["exit"] == 2201.5


@pytest.mark.parametrize("text", ["", "   ", "hello world", "📊 *u2algo — Günlük Özet (2026-11-06)*"])
def test_parse_rejects_non_signal_posts(text):
    assert parse_channel_post(text) is None


@pytest.mark.parametrize("raw,expected", [
    ("BTCUSDT.P", "BTC/USDT"),
    ("BTCUSDT", "BTC/USDT"),
    ("BTC/USDT", "BTC/USDT"),
    ("ETHUSDC", "ETH/USDC"),
    ("SOLUSDT.P", "SOL/USDT"),
    ("WEIRD", None),
])
def test_normalize_symbol(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("15", "15m"), ("1h", "1h"), ("4H", "4h"), ("1d", "1d"), (None, None), ("abc", None),
])
def test_normalize_timeframe(raw, expected):
    assert normalize_timeframe(raw) == expected


# ── event build ─────────────────────────────────────────────────────────────

def test_to_content_job_is_schema_valid():
    p = parse_channel_post(BOT_POST)
    ev = to_content_job(p, chat_id=CHAT, message_id=1, occurred_at="2026-11-06T09:15:00Z")
    assert validate_event(ev) == []
    assert ev["signal"]["symbol"] == "BTC/USDT"
    assert ev["signal"]["confluence"] == 60
    assert ev["signal"]["reasons_detail"]["confluence_source"] == "channel_default"
    assert ev["signal"]["timeframe"] == "15m"
    assert ev["signal"]["reasons_detail"]["timeframe_source"] == "default"
    assert ev["compliance"]["disclaimer_tr"] == COMPLIANCE_TR


def test_to_content_job_keeps_explicit_confluence():
    p = parse_channel_post(INDICATOR_POST + "\nConfluence: 82/100")
    ev = to_content_job(p, chat_id=CHAT, message_id=2, occurred_at="2026-11-06T09:45:00Z")
    assert ev["signal"]["confluence"] == 82
    assert ev["signal"]["reasons_detail"]["confluence_source"] == "channel_post"


def test_to_content_job_attributes_collector_not_bot():
    p = parse_channel_post(BOT_POST)
    ev = to_content_job(p, chat_id=CHAT, message_id=3, occurred_at="2026-11-06T09:15:00Z")
    assert ev["source"]["service"] == COLLECTOR_SERVICE
    assert ev["source"]["service"] != "efloud-bot"
    assert ev["source"]["message_id"] == 3


@pytest.mark.parametrize("text", [
    "🎯 *BTCUSDT LONG* — TP1 hit\nEntry: `76,186.0` → TP1: `77,150.0`",
    "🏁 *ETHUSDT SHORT* — trade closed\nEntry: `2,245.46` → Exit: `2,201.5`",
])
def test_to_content_job_skips_lifecycle_events(text):
    p = parse_channel_post(text)
    assert to_content_job(p, chat_id=CHAT, message_id=4,
                          occurred_at="2026-11-06T10:00:00Z") is None


def test_to_content_job_requires_entry_sl_tp1():
    p = parse_channel_post("🟢 LONG BTCUSDT.P · 15\nEntry: 100\nTP1: 110")
    assert to_content_job(p, chat_id=CHAT, message_id=5,
                          occurred_at="2026-11-06T10:00:00Z") is None


def test_event_id_is_stable_per_message():
    p = parse_channel_post(BOT_POST)
    a = to_content_job(p, chat_id=CHAT, message_id=77, occurred_at="2026-11-06T09:15:00Z")
    b = to_content_job(p, chat_id=CHAT, message_id=77, occurred_at="2026-11-06T09:15:00Z")
    c = to_content_job(p, chat_id=CHAT, message_id=78, occurred_at="2026-11-06T09:15:00Z")
    assert a["event_id"] == b["event_id"]
    assert a["event_id"] != c["event_id"]


# ── collector ───────────────────────────────────────────────────────────────

def _collector(tmp_path: Path, transport=None) -> TelegramChannelCollector:
    return TelegramChannelCollector(
        out_dir=tmp_path / "jobs", state_path=tmp_path / "state" / "tg.json",
        channel_id=CHAT, transport=transport,
    )


def _update(update_id: int, message_id: int, text: str, chat_id: str = CHAT) -> dict:
    return {"update_id": update_id, "channel_post": {
        "message_id": message_id, "date": 1793966100,
        "chat": {"id": int(chat_id)}, "text": text,
    }}


def test_collect_writes_jsonl_and_advances_offset(tmp_path):
    calls = []

    def transport(params):
        calls.append(params)
        return {"ok": True, "result": [_update(10, 501, BOT_POST)]}

    c = _collector(tmp_path, transport)
    s = c.collect()
    assert s["written"] == 1 and s["updates"] == 1
    assert calls[0]["offset"] == 1
    assert json.loads(calls[0]["allowed_updates"]) == ["channel_post"]

    feed = tmp_path / "jobs" / "2026-11-06.jsonl"
    rows = [json.loads(x) for x in feed.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["signal"]["symbol"] == "BTC/USDT"
    assert json.loads((tmp_path / "state" / "tg.json").read_text())["last_update_id"] == 10

    # second poll resumes after the last update and does not re-write the post
    def transport2(params):
        calls.append(params)
        return {"ok": True, "result": []}

    c.transport = transport2
    s2 = c.collect()
    assert calls[-1]["offset"] == 11
    assert s2["written"] == 0
    assert len(feed.read_text(encoding="utf-8").splitlines()) == 1


def test_collect_skips_other_chats_and_lifecycle_posts(tmp_path):
    def transport(params):
        return {"ok": True, "result": [
            _update(1, 1, BOT_POST, chat_id="-1009999999999"),
            _update(2, 2, "🎯 *BTCUSDT LONG* — TP1 hit\nEntry: `1` → TP1: `2`"),
            _update(3, 3, "📊 *u2algo — Günlük Özet (2026-11-06)*"),
            _update(4, 4, INDICATOR_POST),
        ]}

    s = _collector(tmp_path, transport).collect()
    assert s["skipped_other_chat"] == 1
    assert s["skipped_kind"] == 1
    assert s["skipped_unparsed"] == 1
    assert s["written"] == 1


def test_collect_dedupes_replayed_updates(tmp_path):
    payload = {"ok": True, "result": [_update(1, 900, BOT_POST)]}
    c = _collector(tmp_path, lambda params: payload)
    assert c.collect()["written"] == 1
    c.state_path.unlink()  # state lost → the same update is replayed
    s = c.collect()
    assert s["written"] == 0 and s["duplicates"] == 1


def test_collect_raises_on_api_error(tmp_path):
    c = _collector(tmp_path, lambda params: {"ok": False, "description": "Conflict: webhook is active"})
    with pytest.raises(CollectorError, match="webhook is active"):
        c.collect()


def test_collect_requires_token_or_transport(tmp_path):
    with pytest.raises(CollectorError, match="no token"):
        _collector(tmp_path).collect()


def test_ingest_posts_is_idempotent(tmp_path):
    c = _collector(tmp_path)
    first = c.ingest_posts(_fixture_posts())
    second = c.ingest_posts(_fixture_posts())
    assert first["written"] == 3 and first["skipped_kind"] == 2
    assert second["written"] == 0 and second["duplicates"] == 3


# ── adapter: draft → approve → publish ──────────────────────────────────────

@pytest.fixture()
def drafted(tmp_path):
    """Run the real Lane B→G chain over the fixture feed, offline."""
    # Chart render needs matplotlib (optional dep, not in requirements.txt —
    # same guard as tests/test_social_publishing.py::TestRenderTradeChart).
    pytest.importorskip("matplotlib")
    cache = _seed_cache(tmp_path / "cache")
    jobs = tmp_path / "jobs"
    TelegramChannelCollector(
        out_dir=jobs, state_path=tmp_path / "state" / "tg.json", channel_id=CHAT,
    ).ingest_posts(_fixture_posts())
    work = tmp_path / "work"
    summary = draft(date=DATE, jobs_dir=jobs, work_dir=work, cache_dir=cache,
                    platforms=["x", "instagram"])
    return {"summary": summary, "work": work, "tmp": tmp_path}


def test_draft_packages_both_platforms_pending_review(drafted):
    g = drafted["summary"]["lane_g"]
    assert g["packaged"] == 6  # 3 events × (x, instagram)
    assert g["blocked_compliance"] == 0
    assert g["missing_media"] == 0
    assert g["auto_approve"] is False

    bundles = sorted((drafted["work"] / "bundles" / DATE / "bundles").glob("*.json"))
    assert len(bundles) == 6
    for f in bundles:
        b = json.loads(f.read_text(encoding="utf-8"))
        assert b["state"] == "pending_review"
        assert b["platform"] in ("x", "instagram")
        assert b["payload"]["media"], "every bundle must carry a chart"


def test_draft_never_publishes(drafted):
    p = drafted["summary"]["publish"]
    assert p["dry_run"] is True
    assert p["published"] == 0 and p["approved"] == 0


def test_captions_are_compliance_clean(drafted):
    bundles = sorted((drafted["work"] / "bundles" / DATE / "bundles").glob("*.json"))
    for f in bundles:
        b = json.loads(f.read_text(encoding="utf-8"))
        cap = b["payload"]["caption"]
        assert find_violations(cap) == [], f"{b['draft_id']}: {find_violations(cap)}"
        assert has_disclaimer(cap)
        assert "yatırım tavsiyesi değildir" in cap
        assert "$" not in cap and "₺" not in cap
        assert "bakiye" not in cap.lower()
        assert "pozisyon" not in cap.lower()
        assert len(cap) <= (280 if b["platform"] == "x" else 2200)


def test_captions_make_no_parity_claim(drafted):
    """'same setup/entry' is allowed; 'identical TPs' is not."""
    for f in (drafted["work"] / "bundles" / DATE / "bundles").glob("*.json"):
        cap = json.loads(f.read_text(encoding="utf-8"))["payload"]["caption"].lower()
        assert "birebir" not in cap
        assert "aynı tp" not in cap


def test_approve_then_publish_dry_run(drafted):
    work = drafted["work"]
    res = approve(bundle_dir=work / "bundles", date=DATE)
    assert len(res["approved"]) == 6 and res["missing"] == []

    out = publish(bundle_dir=work / "bundles", date=DATE,
                  state_path=drafted["tmp"] / "state" / "lane_e.json", live=False)
    assert out["approved"] == 6
    assert out["published"] == 6  # DryRunPublisher records, no network
    assert out["dry_run"] is True
    assert all(r["status"] == "published" for r in out["results"])


def test_approve_can_target_one_bundle(drafted):
    work = drafted["work"]
    bundles = sorted((work / "bundles" / DATE / "bundles").glob("*.json"))
    target = json.loads(bundles[0].read_text(encoding="utf-8"))
    res = approve(bundle_dir=work / "bundles", date=DATE,
                  event_id=target["event_id"], platform=target["platform"])
    assert res["approved"] == [target["draft_id"]]


def test_publish_live_without_flags_is_noop(drafted, monkeypatch):
    for var in ("X_API_ENABLED", "INSTAGRAM_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    work = drafted["work"]
    approve(bundle_dir=work / "bundles", date=DATE)
    out = publish(bundle_dir=work / "bundles", date=DATE,
                  state_path=drafted["tmp"] / "state" / "lane_e.json", live=True)
    assert out["dry_run"] is False
    assert out["published"] == 0
    assert all(r["status"] == "no_publishers" for r in out["results"])


def test_export_bundles_writes_small_files_and_manifest(drafted):
    out_dir = drafted["tmp"] / "export"
    res = export_bundles(bundle_dir=drafted["work"] / "bundles", date=DATE,
                         out_dir=out_dir, max_bytes=150 * 1024)
    assert res["files"] == 6 and res["oversize"] == []

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 6
    for entry in manifest["files"]:
        assert entry["violations"] == []
        assert entry["disclaimer_present"] is True
        for media in entry["media"]:
            assert media["bytes"] < 150 * 1024
            assert (out_dir / media["path"]).exists()
        assert (out_dir / entry["caption_file"]).exists()


def test_export_flags_oversize_media(drafted):
    res = export_bundles(bundle_dir=drafted["work"] / "bundles", date=DATE,
                         out_dir=drafted["tmp"] / "export2", max_bytes=1024)
    assert res["oversize"], "a 1 KB cap must flag the chart PNGs"


def test_http_transport_error_redacts_token(monkeypatch):
    import scripts.telegram_channel_collector as tcc

    def boom(url, timeout):
        raise OSError(f"cannot open {url}")

    monkeypatch.setattr(tcc.urllib.request, "urlopen", boom)
    with pytest.raises(tcc.CollectorError) as ei:
        tcc.http_get_updates("123:SECRET", {"offset": 1})
    assert "SECRET" not in str(ei.value)
    assert ei.value.__cause__ is None
