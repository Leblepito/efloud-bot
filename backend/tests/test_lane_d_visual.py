"""Lane D visual harness tests — PR #14 (Phase 4a).

Consumes Lane C copy drafts and builds a branded visual spec (chart + overlay)
in two formats: a square-ish *still* and a 1080×1920 *vertical* (story/reels).
The actual pixels are produced by an injected ``renderer`` (Pillow like
``u2algo-site/scripts/generate-launch-pngs.py``, or the higgsfield image MCP, in
prod); the default renderer writes a dependency-free render manifest. Overlay
text is re-checked for compliance (defense in depth). Draft-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.content_jobs import COMPLIANCE_TR
from scripts.lane_d_visual import (
    VISUAL_FORMATS,
    LaneDVisual,
    build_visual_spec,
    manifest_renderer,
)

DATE = "2026-06-09"


def _copy(event_id: str = "a", **over) -> dict:
    caption = (
        "BTC/USDT · 15m · LONG\n"
        "15m FVG retest, bullish OB confluence.\n"
        "Risk ~2.0% · R:R 1:2.0 (TP1) · Geçersizleşme: 48800 altı\n\n"
        f"{COMPLIANCE_TR}"
    )
    c = {
        "event_id": event_id, "symbol": "BTC/USDT", "timeframe": "15m",
        "lang": "tr", "caption": caption,
        "thread": ["BTC/USDT 15m LONG — yapı: TRENDING.", COMPLIANCE_TR],
        "alt_text": "BTC/USDT 15m grafiği — LONG TRENDING setup",
        "source_confidence": "high",
    }
    c.update(over)
    return c


def _write_copy(copy_dir: Path, date: str, items: list[dict]) -> None:
    d = copy_dir / date
    d.mkdir(parents=True, exist_ok=True)
    for c in items:
        (d / f"{c['event_id']}.json").write_text(
            json.dumps(c, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / "copy", tmp_path / "visual"


def _lane_d(dirs, **kw) -> LaneDVisual:
    copy_dir, out_dir = dirs
    return LaneDVisual(copy_dir=copy_dir, out_dir=out_dir, **kw)


def test_vertical_format_is_1080x1920():
    assert VISUAL_FORMATS["vertical"] == (1080, 1920)
    assert "still" in VISUAL_FORMATS


def test_visual_spec_has_overlay_and_disclaimer_footer():
    spec = build_visual_spec(_copy(), chart_path="/tmp/lane-b/a.png")
    assert spec["overlay"]["headline"].startswith("BTC/USDT")
    assert spec["overlay"]["footer"] == COMPLIANCE_TR
    assert spec["chart_path"] == "/tmp/lane-b/a.png"
    assert set(spec["formats"]) == set(VISUAL_FORMATS)


def test_default_manifest_renderer_writes_one_file_per_format(dirs):
    copy_dir, out_dir = dirs
    _write_copy(copy_dir, DATE, [_copy("a")])
    summary = _lane_d(dirs).run(date=DATE)
    assert summary["generated"] == 1
    assert summary["rendered_files"] == len(VISUAL_FORMATS)
    for fmt in VISUAL_FORMATS:
        assert (out_dir / DATE / f"a.{fmt}.json").exists()


def test_manifest_renderer_records_dimensions(tmp_path):
    spec = build_visual_spec(_copy(), chart_path=None)
    base = tmp_path / "a"
    out = manifest_renderer(spec, "vertical", base)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["format"] == "vertical"
    assert payload["width"] == 1080 and payload["height"] == 1920


def test_compliance_quarantines_bad_copy(dirs):
    copy_dir, out_dir = dirs
    bad = _copy("a", caption=f"Garantili getiri! {COMPLIANCE_TR}")
    _write_copy(copy_dir, DATE, [bad])
    summary = _lane_d(dirs).run(date=DATE)
    assert summary["quarantined"] == 1
    assert summary["generated"] == 0
    assert not (out_dir / DATE / "a.vertical.json").exists()


def test_injected_renderer_called_once_per_format(dirs):
    copy_dir, _ = dirs
    _write_copy(copy_dir, DATE, [_copy("a")])
    calls: list[str] = []

    def fake_renderer(spec, fmt, base):
        calls.append(fmt)
        p = Path(str(base) + f".{fmt}.txt")
        p.write_text("ok", encoding="utf-8")
        return p

    _lane_d(dirs, renderer=fake_renderer).run(date=DATE)
    assert sorted(calls) == sorted(VISUAL_FORMATS)


def test_missing_copy_dir_is_noop(dirs):
    s = _lane_d(dirs).run(date=DATE)
    assert s["total"] == 0
    assert s["generated"] == 0


def test_rerun_is_idempotent_overwrite(dirs):
    copy_dir, out_dir = dirs
    _write_copy(copy_dir, DATE, [_copy("a")])
    d = _lane_d(dirs)
    d.run(date=DATE)
    d.run(date=DATE)
    files = list((out_dir / DATE).glob("a.*.json"))
    assert len(files) == len(VISUAL_FORMATS)
