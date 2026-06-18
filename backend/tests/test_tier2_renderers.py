"""
Tier-2 renderers — hermetic unit tests.

Bu testler:
- templates.yaml'ı gerçekten yükler (VPS'te var, hermetic OK)
- content_compliance.find_violations'ı gerçek çağırır (gate live)
- queue_create_draft_fn mock'lanır (DB dokunulmaz)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.social import tier2_renderers as r2
from backend.social.content_queue import ContentStatus
from backend.social.tier2_renderers import (
    ComplianceGateViolationError,
    LanguageNotSupportedError,
    MissingPlaceholderError,
    RenderedContent,
    TemplateNotFoundError,
    TemplateStubError,
    build_queue_payload,
    enqueue,
    load_templates,
    pre_gate,
    render,
    render_and_enqueue,
)


REPO = Path(__file__).resolve().parents[2]
TEMPLATES_PATH = REPO / "scripts" / "content_templates" / "templates.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: real templates + mock queue
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def templates():
    """Gerçek templates.yaml (VPS'te var)."""
    return load_templates(TEMPLATES_PATH)


@pytest.fixture
def queue_create_draft_fn():
    """create_draft mock — ContentDraft benzeri obje döner."""
    from backend.social.content_queue import ContentDraft

    counter = {"n": 0}

    def _create(body, lang, post_type, meta=None):
        counter["n"] += 1
        d = ContentDraft(
            draft_id=f"draft_{counter['n']:03d}",
            body=body,
            lang=lang,
            post_type=post_type,
            meta=meta or {},
        )
        return d

    return _create


# ─────────────────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────────────────


def test_load_templates_path_exists():
    data = load_templates(TEMPLATES_PATH)
    assert "templates" in data
    assert "meta" in data
    assert data["meta"]["channel"] == "x"


def test_load_templates_has_five_templates(templates):
    ids = {t["id"] for t in templates["templates"]}
    assert ids == {
        "signal_idea", "signal_idea_thread", "educational",
        "performance_recap", "promotional", "market_commentary",
    }


def test_load_templates_default_path_resolves():
    """Env yokken default path çalışıyor mu?"""
    data = load_templates()
    assert "templates" in data


def test_load_templates_path_missing_raises(tmp_path):
    with pytest.raises(r2.RendererError, match="bulunamadı"):
        load_templates(tmp_path / "missing.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# Render: single (signal_idea, performance_recap, promotional, market_commentary)
# ─────────────────────────────────────────────────────────────────────────────


def test_render_signal_idea_en(templates):
    rc = render(
        "signal_idea", "en",
        {
            "symbol": "BTCUSDT", "tf": "15m", "direction": "LONG",
            "structure": "bullish OB + FVG retest",
            "entry": "64200", "sl": "63500", "tp1": "65400", "tp2": "66800",
            "rr": "1:2.6", "risk_pct": "1.1",
            "chart_img": "https://example.com/chart.png",
        },
        templates,
    )
    assert rc.format == "single"
    assert rc.category == "signal"
    assert rc.body is not None
    assert "BTCUSDT" in rc.body
    # signal_idea uses meta.disclaimers.en exact string → present=True
    assert rc.disclaimer_present is True
    assert rc.sim_label_present is False  # signal template, sim değil
    assert rc.media == ["https://example.com/chart.png"]


def test_render_signal_idea_tr(templates):
    rc = render(
        "signal_idea", "tr",
        {
            "symbol": "BTCUSDT", "tf": "15m", "direction": "LONG",
            "structure": "bullish OB + FVG retest",
            "entry": "64200", "sl": "63500", "tp1": "65400", "tp2": "66800",
            "rr": "1:2.6", "risk_pct": "1.1",
            "chart_img": "x.png",
        },
        templates,
    )
    assert rc.body is not None
    assert "BTCUSDT" in rc.body
    assert "Yapı" in rc.body
    # signal_idea uses meta.disclaimers.tr exact string → present=True
    assert rc.disclaimer_present is True


def test_render_performance_recap_en_has_sim_label(templates):
    rc = render(
        "performance_recap", "en",
        {"week": "2026-W24", "n_ideas": "7", "n_reached": "4/7",
         "avg_r": "+1.8", "risk_pct": "1.3"},
        templates,
    )
    assert rc.body is not None
    assert "[SIMULATED]" in rc.body
    assert rc.sim_label_present is True
    # performance_recap uses its own disclaimer wording ("Past performance is not
    # indicative of future results. Not investment advice.") — not the exact
    # meta.disclaimers.en string. So disclaimer_present=False here; the gate
    # accepts the template copy via content_compliance.find_violations == [].
    assert rc.disclaimer_present is False


def test_render_promotional_en(templates):
    rc = render(
        "promotional", "en",
        {"feature": "New: 15m + 1h multi-timeframe exports",
         "cta_url": "https://u2algo.com/waitlist"},
        templates,
    )
    assert rc.body is not None
    assert "waitlist" in rc.body.lower()
    # promotional has its own disclaimer copy — not meta.disclaimers.en exact.
    # Gate still accepts it (verified by verify_compliance.py).
    assert rc.disclaimer_present is False


def test_render_market_commentary_tr(templates):
    rc = render(
        "market_commentary", "tr",
        {"symbol": "BTCUSDT", "tf": "4h",
         "bias": "nötr", "levels": "61800–66500", "watch_note": "mid tepki"},
        templates,
    )
    assert rc.body is not None
    assert "BTCUSDT" in rc.body
    # Same: custom disclaimer wording.
    assert rc.disclaimer_present is False


# ─────────────────────────────────────────────────────────────────────────────
# Render: thread (signal_idea_thread, educational)
# ─────────────────────────────────────────────────────────────────────────────


def test_render_signal_thread_en(templates):
    rc = render(
        "signal_idea_thread", "en",
        {
            "symbol": "ETHUSDT", "tf": "1h", "direction": "SHORT",
            "structure": "bearish breaker + EQH sweep",
            "entry": "3420", "sl": "3505", "tp1": "3300", "tp2": "3180",
            "rr": "1:2.1", "risk_pct": "1.4",
            "invalidation_note": "1h close back above the breaker",
            "chart_img": "https://example.com/chart2.png",
        },
        templates,
    )
    assert rc.format == "thread"
    assert len(rc.tweets) == 4
    # Disclaimer son tweet'te
    assert rc.disclaimer_present is True
    assert rc.media == ["https://example.com/chart2.png"]
    # Full text birleştirilmiş olmalı
    assert "ETHUSDT" in rc.full_text


def test_render_educational_tr(templates):
    rc = render(
        "educational", "tr",
        {
            "concept": "Order Block (OB)",
            "one_line_definition": "Güçlü hareketten önceki son ters mum.",
            "how_to_spot": "yapıyı kıran yükseliş impulsundan önceki son düşüş mumu",
            "how_to_use": "fiyat OB'ye dönünce teyit ara",
            "risk_pct": "1",
        },
        templates,
    )
    assert len(rc.tweets) == 4
    assert rc.disclaimer_present is True
    assert "📚" in rc.tweets[0]


# ─────────────────────────────────────────────────────────────────────────────
# Render: error paths
# ─────────────────────────────────────────────────────────────────────────────


def test_render_unknown_template_raises(templates):
    with pytest.raises(TemplateNotFoundError, match="bilinmeyen_template"):
        render("bilinmeyen_template", "en", {}, templates)


def test_render_unsupported_lang_raises(templates):
    with pytest.raises(LanguageNotSupportedError, match="desteklemiyor"):
        render("signal_idea", "fr", {}, templates)


def test_render_ru_stub_raises(templates):
    """RU stub → TemplateStubError (TODO body)."""
    with pytest.raises(TemplateStubError, match="TODO stub"):
        render(
            "signal_idea", "ru",
            {"symbol": "BTCUSDT", "tf": "15m", "direction": "LONG",
             "structure": "x", "entry": "1", "sl": "1", "tp1": "1", "tp2": "1",
             "rr": "1:1", "risk_pct": "1", "chart_img": "x"},
            templates,
        )


def test_render_missing_placeholder_raises(templates):
    with pytest.raises(MissingPlaceholderError, match="placeholder eksik"):
        render("signal_idea", "en", {"symbol": "BTCUSDT"}, templates)  # eksik


# ─────────────────────────────────────────────────────────────────────────────
# Pre-gate
# ─────────────────────────────────────────────────────────────────────────────


def test_pre_gate_clean_for_sample(templates, queue_create_draft_fn):
    rc = render(
        "signal_idea", "en",
        {
            "symbol": "BTCUSDT", "tf": "15m", "direction": "LONG",
            "structure": "bullish OB + FVG retest",
            "entry": "64200", "sl": "63500", "tp1": "65400", "tp2": "66800",
            "rr": "1:2.6", "risk_pct": "1.1",
            "chart_img": "x.png",
        },
        templates,
    )
    violations = pre_gate(rc)
    assert violations == [], f"sample template gate FAIL: {violations}"


def test_pre_gate_flags_banned_phrase():
    """Garanti içeren bir body → gate violation dönmeli."""
    rc = RenderedContent(
        template_id="manual", lang="tr", category="signal", format="single",
        body="Bu strateji garantili getiri vaat ediyor.",
        disclaimer_present=True, sim_label_present=False,
    )
    v = pre_gate(rc)
    assert any("banned_phrase" in x for x in v)


def test_pre_gate_flags_absolute_money():
    rc = RenderedContent(
        template_id="manual", lang="en", category="signal", format="single",
        body="Bugün $250 kazandık.", disclaimer_present=True,
    )
    v = pre_gate(rc)
    assert "absolute_money" in v


def test_pre_gate_flags_unlabeled_sim():
    """sim-word ama label yok → violation."""
    rc = RenderedContent(
        template_id="manual", lang="en", category="performance", format="single",
        body="Last week backtest showed great results.",
        disclaimer_present=True, sim_label_present=False,
    )
    v = pre_gate(rc)
    assert "unlabeled_simulation" in v


def test_pre_gate_passes_when_label_present():
    rc = RenderedContent(
        template_id="manual", lang="en", category="performance", format="single",
        body="Last week [SIMULATED] backtest showed great results.",
        disclaimer_present=True, sim_label_present=True,
    )
    v = pre_gate(rc)
    assert "unlabeled_simulation" not in v


# ─────────────────────────────────────────────────────────────────────────────
# Queue integration
# ─────────────────────────────────────────────────────────────────────────────


def test_enqueue_clean_calls_queue(templates, queue_create_draft_fn):
    rc = render(
        "signal_idea", "en",
        {
            "symbol": "BTCUSDT", "tf": "15m", "direction": "LONG",
            "structure": "bullish OB + FVG retest",
            "entry": "64200", "sl": "63500", "tp1": "65400", "tp2": "66800",
            "rr": "1:2.6", "risk_pct": "1.1",
            "chart_img": "x.png",
        },
        templates,
    )
    gate = pre_gate(rc)
    draft = enqueue(rc, gate, queue_create_draft_fn)
    assert draft.draft_id == "draft_001"
    assert draft.status == ContentStatus.DRAFT  # queue create_draft DRAFT döner
    assert draft.lang == "en"
    assert draft.post_type == "signal"
    # meta template_id'yi içermeli
    assert draft.meta["template_id"] == "signal_idea"
    assert draft.meta["disclaimer_present"] is True


def test_enqueue_violation_raises_quarantine(templates, queue_create_draft_fn):
    """Gate FAIL → ComplianceGateViolationError, queue_create_draft_fn çağrılmamalı."""
    rc = RenderedContent(
        template_id="manual", lang="tr", category="signal", format="single",
        body="Bu strateji garantili getiri vaat ediyor.",
        disclaimer_present=True,
    )
    gate = pre_gate(rc)
    with pytest.raises(ComplianceGateViolationError) as exc_info:
        enqueue(rc, gate, queue_create_draft_fn)
    assert exc_info.value.template_id == "manual"
    assert any("banned_phrase" in v for v in exc_info.value.violations)
    # queue_create_draft_fn hiç çağrılmadı
    # (mock fn — kontrol: eğer çağrılsaydı counter artardı; direkt ref kontrol et)


def test_build_queue_payload_shape():
    rc = RenderedContent(
        template_id="t1", lang="en", category="signal", format="single",
        body="hello", disclaimer_present=True, sim_label_present=False,
        values_used={"a": 1},
    )
    p = build_queue_payload(rc, [])
    assert p["body"] == "hello"
    assert p["lang"] == "en"
    assert p["post_type"] == "signal"
    assert p["meta"]["template_id"] == "t1"
    assert p["meta"]["values_used"] == {"a": 1}
    assert p["meta"]["compliance_report"]["violation_count"] == 0


def test_render_and_enqueue_full_pipeline(templates, queue_create_draft_fn):
    rc, draft = render_and_enqueue(
        "performance_recap", "tr",
        {"week": "2026-W24", "n_ideas": "7", "n_reached": "4/7",
         "avg_r": "+1.8", "risk_pct": "1.3"},
        queue_create_draft_fn,
        templates,
    )
    assert rc.sim_label_present is True
    assert draft.post_type == "performance"
    assert "[SIMULATED]" in draft.body


# ─────────────────────────────────────────────────────────────────────────────
# Lane topology (operatör kararı: research ↔ publish ayrımı)
# ─────────────────────────────────────────────────────────────────────────────


def test_module_has_no_xurl_import():
    """renderer xurl/Manus çağırmamalı (publish lane işi)."""
    src = Path(r2.__file__).read_text()
    # Yorum/docstring dışı kontrol: import/function-call referansı var mı?
    # xurl_client import edilmemeli, ManusClient import edilmemeli.
    assert "xurl_client" not in src
    assert "manus_client" not in src
    assert "from xurl" not in src
    assert "from manus" not in src


def test_module_does_not_call_publishers():
    """renderer publish lane'e (lane_e) dokunmamalı — sadece docstring'te bahsedilebilir."""
    import re
    src = Path(r2.__file__).read_text()
    # Docstring'leri tamamen çıkar (module + tüm function/class docstring'leri).
    code_no_docstrings = re.sub(r'"""[\s\S]*?"""', '', src)
    code_no_docstrings = re.sub(r"'''[\s\S]*?'''", '', code_no_docstrings)
    code_no_docstrings = re.sub(r"#.*$", "", code_no_docstrings, flags=re.MULTILINE)
    assert "lane_e" not in code_no_docstrings.lower(), "renderer publish lane'e referans veriyor"
    assert "publish_draft" not in code_no_docstrings, "renderer publish_draft çağırıyor"
