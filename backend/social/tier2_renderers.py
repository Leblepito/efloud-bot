"""
Tier-2 content renderers (P-002 M6 second half) — Hermes consume contract.

Contract (from scripts/content_templates/README.md §"How Hermes wires this in"):
    1. Render   — load scripts/content_templates/templates.yaml,
                  pick template.langs[lang], str.format(**values).
                  For format=thread, render each tweets[] entry; tweet 1 carries
                  {chart_img} media.
    2. Pre-gate — run scripts.content_compliance.find_violations(text) on the
                  rendered text BEFORE enqueueing. Non-empty → quarantine,
                  don't enqueue (same pattern as LaneCCopywriter.run).
    3. Enqueue  — build a draft into the approval queue (T-027 / pending_review).

Lane topology (operatör kararı, 2026-06-19):
    scripts/content_templates/  → publish omurgası (gate + lane_*)
    backend/social/             → research subsystem (Manus, xurl client, renderer)

    Renderer ("this module") bridges research → publish:
      research produces raw values (signal: {symbol, tf, structure, ...})
      renderer formats + pre-gates + enqueues
      publish (lane_e) consumes approved drafts and dispatches via xurl/Manus

NO outbound publish from this module. NO xurl/Manus calls. Pure rendering +
pre-gate + enqueue. The publish dispatch lives in lane_e (separate module,
operatörün mimari kararı).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# Default templates.yaml location (resolved from this file's path).
# scripts/content_templates/templates.yaml lives at REPO_ROOT/scripts/...
# This module lives at REPO_ROOT/backend/social/tier2_renderers.py
# → parents[2] == REPO_ROOT.
_DEFAULT_TEMPLATES_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "content_templates" / "templates.yaml"
)
TEMPLATES_PATH_ENV = "EFLOUD_TEMPLATES_PATH"  # override


class RendererError(Exception):
    """Base error for tier2_renderers."""


class TemplateNotFoundError(RendererError):
    """template_id not in loaded templates.yaml."""


class LanguageNotSupportedError(RendererError):
    """Lang not present in template.langs (e.g. RU/KZ TODO stub)."""


class TemplateStubError(RendererError):
    """Lang exists but is a stub ('TODO' body/tweets)."""


class ComplianceGateViolationError(RendererError):
    """Pre-gate ihlali — draft quarantine edilir, enqueue edilmez."""

    def __init__(self, template_id: str, lang: str, violations: list[str]):
        self.template_id = template_id
        self.lang = lang
        self.violations = violations
        super().__init__(
            f"compliance gate violation in {template_id}/{lang}: {violations}"
        )


class MissingPlaceholderError(RendererError):
    """str.format KeyError — value'lar template'in placeholders'ını karşılamıyor."""


# ─────────────────────────────────────────────────────────────────────────────
# Rendered content model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RenderedContent:
    """Template'in formatlanmış çıktısı — pre-gate sonrası enqueue'ya hazır."""

    template_id: str
    lang: str
    category: str
    format: str                       # "single" | "thread"
    body: str | None = None           # format=single
    tweets: list[str] = field(default_factory=list)  # format=thread
    media: list[str] = field(default_factory=list)   # chart_img paths/URLs
    disclaimer_present: bool = False  # exact engine.content_jobs string var mı
    sim_label_present: bool = False   # [SIMULATED] / [BACKTEST] etc. var mı
    values_used: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Pre-gate'e gönderilecek tam metin (thread: tweets joined)."""
        if self.format == "thread":
            return "\n".join(self.tweets)
        return self.body or ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "lang": self.lang,
            "category": self.category,
            "format": self.format,
            "body": self.body,
            "tweets": self.tweets,
            "media": self.media,
            "disclaimer_present": self.disclaimer_present,
            "sim_label_present": self.sim_label_present,
            "values_used": self.values_used,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_templates_path(explicit: str | Path | None = None) -> Path:
    """Path resolution: explicit arg > env > default."""
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get(TEMPLATES_PATH_ENV)
    if env:
        return Path(env)
    return _DEFAULT_TEMPLATES_PATH


def load_templates(path: str | Path | None = None) -> dict[str, Any]:
    """templates.yaml → parsed dict. Convenience wrapper around yaml.safe_load.

    Returns:
        {"meta": {...}, "templates": [{"id": ..., "langs": {...}}, ...]}
    """
    p = _resolve_templates_path(path)
    if not p.exists():
        raise RendererError(f"templates.yaml bulunamadı: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "templates" not in data:
        raise RendererError(f"templates.yaml şeması hatalı: 'templates' anahtarı yok")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Render
# ─────────────────────────────────────────────────────────────────────────────


def _disclaimer_text(disclaimers: dict[str, str], lang: str) -> str:
    """meta.disclaimers[lang] — bulamazsa boş string döner (test zorunlu değil)."""
    return disclaimers.get(lang, "")


def _check_disclaimer(text: str, disclaimer: str) -> bool:
    if not disclaimer:
        return False
    return disclaimer in text


_SIM_LABEL_PATTERN = __import__("re").compile(
    r"\[(BACKTEST|TESTNET|SIMULATED|SIM|REPLAY)\]",
    __import__("re").IGNORECASE,
)


def _check_sim_label(text: str) -> bool:
    return bool(_SIM_LABEL_PATTERN.search(text))


def _format_str(template_str: str, values: dict[str, Any]) -> str:
    """str.format with explicit KeyError → MissingPlaceholderError."""
    try:
        return template_str.format(**values)
    except KeyError as e:
        raise MissingPlaceholderError(
            f"placeholder eksik: {e.args[0]} (verilen keys: {sorted(values.keys())})"
        )


def render(
    template_id: str,
    lang: str,
    values: dict[str, Any],
    templates: dict[str, Any] | None = None,
    templates_path: str | Path | None = None,
) -> RenderedContent:
    """Bir template'i formatla + label/disclaimer kontrolü yap.

    Args:
        template_id: "signal_idea" | "educational" | "performance_recap" | "promotional" | "market_commentary" (5 tip)
        lang: "en" | "tr" (RU/KZ stub → TemplateStubError)
        values: template placeholders'ı karşılayan dict (sample.yaml'dan)
        templates: önceden load_templates() edilmiş dict (None ise load eder)
        templates_path: explicit path (None ise env/default)

    Returns:
        RenderedContent (pre-gate henüz çalışmamış — caller pre_gate çağıracak)
    """
    if templates is None:
        templates = load_templates(templates_path)

    # Template bul
    tpl = next(
        (t for t in templates["templates"] if t["id"] == template_id),
        None,
    )
    if tpl is None:
        raise TemplateNotFoundError(
            f"template_id bulunamadı: {template_id} "
            f"(mevcut: {[t['id'] for t in templates['templates']]})"
        )

    # Lang desteği
    if lang not in tpl["langs"]:
        raise LanguageNotSupportedError(
            f"template {template_id} lang={lang} desteklemiyor "
            f"(mevcut: {list(tpl['langs'].keys())})"
        )

    spec = tpl["langs"][lang]

    # Stub kontrol (RU/KZ TODO)
    is_stub = (spec.get("body") == "TODO") or (spec.get("tweets") == ["TODO"])
    if is_stub:
        raise TemplateStubError(
            f"template {template_id} lang={lang} henüz TODO stub — "
            f"templates.yaml README §'RU/KZ addition' adımlarını tamamla"
        )

    # Format dispatch
    fmt = spec.get("format")
    media_list = [
        _format_str(m, values) for m in tpl.get("media", [])
    ]

    body: str = ""
    full_text: str = ""
    tweets: list[str] = []

    if fmt == "thread":
        tweets_raw = spec.get("tweets", [])
        if not tweets_raw:
            raise RendererError(f"thread template ama tweets boş: {template_id}/{lang}")
        tweets = [_format_str(t, values) for t in tweets_raw]
        full_text = "\n".join(tweets)
    elif fmt == "single":
        raw_body = spec.get("body", "")
        if not raw_body:
            raise RendererError(f"single template ama body boş: {template_id}/{lang}")
        body = _format_str(raw_body, values)
        full_text = body
    else:
        raise RendererError(f"bilinmeyen format: {fmt!r} (template {template_id})")

    # Disclaimer + sim-label kontrol
    disclaimers = (templates.get("meta") or {}).get("disclaimers") or {}
    disclaimer_text = _disclaimer_text(disclaimers, lang)

    return RenderedContent(
        template_id=template_id,
        lang=lang,
        category=tpl.get("category", "unknown"),
        format=fmt,
        body=body if fmt == "single" else None,
        tweets=tweets if fmt == "thread" else [],
        media=media_list,
        disclaimer_present=_check_disclaimer(full_text, disclaimer_text),
        sim_label_present=_check_sim_label(full_text),
        values_used=dict(values),  # copy for audit
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pre-gate (compliance)
# ─────────────────────────────────────────────────────────────────────────────


def pre_gate(rendered: RenderedContent, lang: str | None = None) -> list[str]:
    """RenderedContent → scripts.content_compliance.find_violations.

    Returns:
        list[str]: boş ise CLEAN, dolu ise violation tag'leri (raise YAPMA).

    Raises:
        ImportError: scripts.content_compliance bulunamazsa (VPS layout broken).
    """
    # Lazy import — content_compliance repo root'a bağımlı; testlerde mock'lanır.
    from scripts.content_compliance import find_violations  # type: ignore

    scan_lang = lang or rendered.lang
    return find_violations(rendered.full_text, lang=scan_lang)


# ─────────────────────────────────────────────────────────────────────────────
# Enqueue (T-027 queue integration)
# ─────────────────────────────────────────────────────────────────────────────


def build_queue_payload(rendered: RenderedContent, gate_report: list[str]) -> dict[str, Any]:
    """ContentDraft'a map edilecek payload — T-027 create_draft ile uyumlu.

    T-027 schema: { draft_id, body, lang, post_type, meta, status, ... }
    Burada: body = full_text, lang = rendered.lang, post_type = category.
    """
    return {
        "body": rendered.full_text,
        "lang": rendered.lang,
        "post_type": rendered.category,
        "meta": {
            "template_id": rendered.template_id,
            "format": rendered.format,
            "media": rendered.media,
            "tweets": rendered.tweets,
            "disclaimer_present": rendered.disclaimer_present,
            "sim_label_present": rendered.sim_label_present,
            "values_used": rendered.values_used,
            "compliance_report": {
                "violation_count": len(gate_report),
                "violations": gate_report,
            },
        },
    }


def enqueue(
    rendered: RenderedContent,
    gate_report: list[str],
    queue_create_draft_fn: Any,
) -> Any:
    """Pre-gate PASS ise T-027 queue'ya ekle, FAIL ise quarantine.

    Args:
        rendered: render() çıktısı
        gate_report: pre_gate() çıktısı (boş ise CLEAN)
        queue_create_draft_fn: backend.social.content_queue.create_draft
                               (DI için parametre; testlerde mock'lanır)

    Returns:
        ContentDraft (queue_create_draft_fn return value)

    Raises:
        ComplianceGateViolationError: gate ihlali → quarantine (enqueue YOK)
    """
    if gate_report:
        logger.warning(
            "quarantine: %s/%s gate violations: %s",
            rendered.template_id, rendered.lang, gate_report,
        )
        raise ComplianceGateViolationError(
            template_id=rendered.template_id,
            lang=rendered.lang,
            violations=gate_report,
        )

    payload = build_queue_payload(rendered, gate_report)
    draft = queue_create_draft_fn(
        body=payload["body"],
        lang=payload["lang"],
        post_type=payload["post_type"],
        meta=payload["meta"],
    )
    logger.info(
        "enqueued: %s/%s draft_id=%s",
        rendered.template_id, rendered.lang, draft.draft_id,
    )
    return draft


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: render + pre_gate + enqueue (full pipeline)
# ─────────────────────────────────────────────────────────────────────────────


def render_and_enqueue(
    template_id: str,
    lang: str,
    values: dict[str, Any],
    queue_create_draft_fn: Any,
    templates: dict[str, Any] | None = None,
    templates_path: str | Path | None = None,
) -> tuple[RenderedContent, Any]:
    """render() → pre_gate() → enqueue() tam pipeline.

    Returns:
        (RenderedContent, ContentDraft) — gate PASS durumunda

    Raises:
        ComplianceGateViolationError: gate FAIL → quarantine, enqueue YOK
        TemplateNotFoundError, LanguageNotSupportedError, TemplateStubError, ...
    """
    rendered = render(template_id, lang, values, templates, templates_path)
    gate_report = pre_gate(rendered)
    draft = enqueue(rendered, gate_report, queue_create_draft_fn)
    return rendered, draft
