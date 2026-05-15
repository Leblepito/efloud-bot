"""LLM özet üretici — claude-haiku-4-5 ile bot davranışı NL summary.

İki kullanım yeri:
1. Watch loop saatlik özet (Task E'de wired olacak): son 1 saatlik
   log_lines + journal_recent → "Bot durumu" kısa rapor.
2. Daily report (ops/daily_report'la birlikte): 24h closed trades +
   key metrikler → "Günlük rapor" markdown.

Cost cap: state.get_llm_calls_today() < daily_cap (default 500). Cap
aşılırsa graceful skip + placeholder, no API call. Çağrılar başarılı
olduğunda state.record_llm_call(token_in, token_out) ile sayaç +
token harcaması güncellenir.

Offline mode: EFLOUD_OVERSEER_LLM_OFFLINE=1 → API çağrısı yapılmaz,
"<LLM offline>" placeholder döner. Test ve Week 2 rollout için.

API hata yakalamaları:
    success    → text content
    offline    → "<LLM offline>"
    cap aşıldı → "<LLM cap exceeded>"
    exception  → "<LLM error>" (state.record_llm_call ÇAĞRILMAZ)

Anthropic SDK lazy import edilir — top-level import yok ki:
  - test ortamında SDK olmadan import OK,
  - offline mode'da hiç gerekmesin.
"""
from __future__ import annotations

import json
import logging

# Input size caps — prevent unbounded token usage on large log buffers.
MAX_LOG_LINES_HOURLY = 100
MAX_JOURNAL_ENTRIES_HOURLY = 20
MAX_TRADES_DAILY = 50
import os
from typing import Any, Optional, Protocol

log = logging.getLogger("efloud.overseer.summarizer")


# ─────────────────────────────────────────────────────────────────────
# Protocol shim — lets tests inject a fake client without depending on
# the anthropic SDK type surface. The single method mirrors
# anthropic.Anthropic.messages.create's keyword args we actually use.
# ─────────────────────────────────────────────────────────────────────


class AnthropicClient(Protocol):
    """Subset of anthropic.Anthropic.messages.create — kwargs-only."""

    def messages_create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
    ) -> Any: ...


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 600
DEFAULT_DAILY_CAP = 500

# System prompts kept here (not module-level constants we import elsewhere)
# so a future tweak doesn't accidentally drift between the two flows.
_SYSTEM_HOURLY = (
    "You are an observer for a crypto trading bot (efloud, SMC strategy on "
    "Binance USDT-M futures). You only describe what happened — you do NOT "
    "suggest trades, parameter changes, or strategy edits. Your tone is "
    "factual, concise. Output Turkish.\n\n"
    "Format hourly summary as:\n"
    "- 1-line headline (her satır <80 char)\n"
    "- 3-5 bullet observations\n"
    "- 1-line risk flag (or \"Risk: yok\" if hiçbir uyarı yok)"
)

_SYSTEM_DAILY = (
    "You are an observer for a crypto trading bot (efloud, SMC strategy on "
    "Binance USDT-M futures). You only describe what happened — you do NOT "
    "suggest trades, parameter changes, or strategy edits. Your tone is "
    "factual, concise. Output Turkish.\n\n"
    "Format daily report as Markdown:\n"
    "- '# Günlük Rapor' heading\n"
    "- '## Özet' (1-2 paragraph summary)\n"
    "- '## Önemli Olaylar' bullet list of notable trades or events\n"
    "- '## Risk Notu' (single line)"
)


# ─────────────────────────────────────────────────────────────────────
# Placeholders (string constants the tests assert on verbatim).
# ─────────────────────────────────────────────────────────────────────

_PLACEHOLDER_OFFLINE = "<LLM offline>"
_PLACEHOLDER_CAP = "<LLM cap exceeded>"
_PLACEHOLDER_ERROR = "<LLM error>"


class Summarizer:
    """LLM summary üretici.

    Caller bir state nesnesi (OverseerState benzeri — `get_llm_calls_today`
    ve `record_llm_call(token_in, token_out)` metodları yeterli) +
    opsiyonel AnthropicClient mock geçer. Production'da client None →
    modül lazy `anthropic.Anthropic()` oluşturur (env'den ANTHROPIC_API_KEY).
    """

    def __init__(
        self,
        state: Any,
        *,
        client: Optional[AnthropicClient] = None,
        daily_cap: int = DEFAULT_DAILY_CAP,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        self._state = state
        self._injected_client = client
        self._daily_cap = int(daily_cap)
        self._model = model
        self._max_tokens = int(max_tokens)

    # ---- public API --------------------------------------------------------

    def is_offline(self) -> bool:
        """True iff EFLOUD_OVERSEER_LLM_OFFLINE=1 in environment.

        Checked on every call (not cached) so an operator flipping the env
        live without restarting the container takes effect immediately."""
        return os.environ.get("EFLOUD_OVERSEER_LLM_OFFLINE", "").strip() == "1"

    def hourly_summary(
        self,
        *,
        recent_log_lines: list[dict],
        journal_recent: list[dict],
    ) -> str:
        """Üret saatlik özet. Cap/offline/error koruması placeholder döner."""
        if self.is_offline():
            return _PLACEHOLDER_OFFLINE
        if self._cap_exceeded():
            log.warning(
                "overseer summarizer: daily LLM cap %d reached — skipping call",
                self._daily_cap,
            )
            return _PLACEHOLDER_CAP

        user_msg = self._build_hourly_user_message(recent_log_lines, journal_recent)
        return self._dispatch(system=_SYSTEM_HOURLY, user_message=user_msg)

    def daily_report(
        self,
        *,
        closed_trades_24h: list[dict],
        key_metrics: dict,
    ) -> str:
        """Üret 24h trade markdown rapor. Aynı cap/offline/error koruması."""
        if self.is_offline():
            return _PLACEHOLDER_OFFLINE
        if self._cap_exceeded():
            log.warning(
                "overseer summarizer: daily LLM cap %d reached — skipping call",
                self._daily_cap,
            )
            return _PLACEHOLDER_CAP

        user_msg = self._build_daily_user_message(closed_trades_24h, key_metrics)
        return self._dispatch(system=_SYSTEM_DAILY, user_message=user_msg)

    # ---- internals ---------------------------------------------------------

    def _cap_exceeded(self) -> bool:
        """True if today's UTC LLM-call counter is >= the configured cap."""
        try:
            calls_today = int(self._state.get_llm_calls_today())
        except Exception:
            # State read failure → treat as cap-exceeded so we fail-safe by
            # not making the API call. Logged but no raise.
            log.warning("overseer summarizer: state.get_llm_calls_today() failed", exc_info=True)
            return True
        return calls_today >= self._daily_cap

    def _dispatch(self, *, system: str, user_message: str) -> str:
        """Common API-call body for hourly + daily. Captures errors into
        the "<LLM error>" placeholder (never re-raises)."""
        try:
            client = self._get_client()
        except Exception as e:
            log.warning("overseer summarizer: client init failed: %s", e)
            return _PLACEHOLDER_ERROR

        messages = [{"role": "user", "content": user_message}]
        try:
            resp = client.messages_create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            )
        except Exception as e:
            log.warning("overseer summarizer: messages_create failed: %s", e)
            return _PLACEHOLDER_ERROR

        try:
            text = self._extract_text(resp)
            tok_in, tok_out = self._extract_usage(resp)
        except Exception as e:
            log.warning("overseer summarizer: response parse failed: %s", e)
            return _PLACEHOLDER_ERROR

        # Only record on a successful end-to-end call — exception paths above
        # all return before reaching here, so token spend stays truthful.
        try:
            self._state.record_llm_call(tok_in, tok_out)
        except Exception as e:
            # State write failure is non-fatal (we still return the summary);
            # tomorrow's cap-guard may be slightly off but operations continue.
            log.warning("overseer summarizer: state.record_llm_call failed: %s", e)

        return text

    def _get_client(self) -> AnthropicClient:
        """Return the injected client or lazy-construct anthropic.Anthropic().

        The lazy import keeps `import ops.overseer.summarizer` cheap and
        avoids forcing the SDK as a hard dependency for offline deploys.
        """
        if self._injected_client is not None:
            return self._injected_client
        try:
            import anthropic  # noqa: WPS433 — intentional lazy import
        except ImportError as e:
            raise RuntimeError(
                "anthropic SDK is required for online summarizer use "
                "(pip install anthropic) — or set EFLOUD_OVERSEER_LLM_OFFLINE=1"
            ) from e
        sdk_client = anthropic.Anthropic()
        return _SdkAdapter(sdk_client)

    @staticmethod
    def _extract_text(resp: Any) -> str:
        """Pluck the first text block out of resp.content.

        Anthropic returns content as a list of typed blocks ({type: text|...}).
        We pick the first text block; later non-text blocks (tool_use, etc.)
        are ignored — the summarizer never asks for tools."""
        content = getattr(resp, "content", None)
        if not content:
            raise ValueError("empty response content")
        for block in content:
            btype = getattr(block, "type", None)
            if btype == "text":
                return getattr(block, "text", "")
        raise ValueError("no text block in response content")

    @staticmethod
    def _extract_usage(resp: Any) -> tuple[int, int]:
        """Return (input_tokens, output_tokens) from resp.usage."""
        usage = getattr(resp, "usage", None)
        if usage is None:
            return (0, 0)
        return (
            int(getattr(usage, "input_tokens", 0)),
            int(getattr(usage, "output_tokens", 0)),
        )

    @staticmethod
    def _build_hourly_user_message(
        recent_log_lines: list[dict],
        journal_recent: list[dict],
    ) -> str:
        """Serialize recent context into a single user message.

        We use JSON (with default=str) so any timestamp/Decimal sneaks
        through without throwing — the model reads it fine."""
        capped_lines = recent_log_lines[-MAX_LOG_LINES_HOURLY:]
        capped_journal = journal_recent[-MAX_JOURNAL_ENTRIES_HOURLY:]
        try:
            lines_json = json.dumps(capped_lines, ensure_ascii=False, default=str)
        except Exception:
            lines_json = str(capped_lines)
        try:
            journal_json = json.dumps(capped_journal, ensure_ascii=False, default=str)
        except Exception:
            journal_json = str(capped_journal)
        return (
            "Son 1 saatlik bot davranışını özetle.\n\n"
            "## Recent log lines (JSON):\n"
            f"{lines_json}\n\n"
            "## Recent journal entries (JSON):\n"
            f"{journal_json}\n"
        )

    @staticmethod
    def _build_daily_user_message(
        closed_trades_24h: list[dict],
        key_metrics: dict,
    ) -> str:
        """Serialize closed-trades + metrics into the daily user message."""
        capped_trades = closed_trades_24h[-MAX_TRADES_DAILY:]
        try:
            trades_json = json.dumps(capped_trades, ensure_ascii=False, default=str)
        except Exception:
            trades_json = str(capped_trades)
        try:
            metrics_json = json.dumps(key_metrics, ensure_ascii=False, default=str)
        except Exception:
            metrics_json = str(key_metrics)
        return (
            "Son 24 saatin trade davranışını rapor halinde sun.\n\n"
            "## Closed trades (JSON):\n"
            f"{trades_json}\n\n"
            "## Key metrics (JSON):\n"
            f"{metrics_json}\n"
        )


class _SdkAdapter:
    """Adapts anthropic.Anthropic to our Protocol (kwargs-only signature).

    The real SDK exposes `client.messages.create(...)`. Our Protocol uses a
    single flat method `messages_create` so test fakes don't have to nest a
    sub-object — this adapter bridges the two without leaking SDK types
    into call sites.
    """

    def __init__(self, sdk_client: Any):
        self._sdk = sdk_client

    def messages_create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
    ) -> Any:
        return self._sdk.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
