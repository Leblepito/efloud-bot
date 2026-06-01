"""Role agents — each one a thin subclass with its own prompt (and optional
context filter).

The five roles mirror the canonical plan A2:

* :class:`SignalValidatorAgent` — LTF/MTF structure, symbol-aware.
* :class:`RiskReviewerAgent`    — R:R / notional / SL distance, symbol-agnostic.
* :class:`RegimeAgent`          — Macro / HTF bias / ADX, symbol-aware.
* :class:`OverseerAgent`        — Synthesises the sub-agent verdicts.
* :class:`PostMortemAgent`      — Cycle-external; reads the trade journal
  and emits a markdown report under ``reports/``.

Context filters on the three per-trade roles are intentionally
restrictive: each ``filter_context`` is a passive whitelist that
selects only the fields the role is allowed to see, before the
prompt is built. That is *prompt-level field selection*, not an
enforced isolation — a sub-agent's prompt is built from a smaller
dict, but the underlying ctx object is the same shared instance
passed by ``team.py``. The Overseer is the only agent with a real
isolation guarantee: it sees only the sub-agent verdict list, not
the trade context.

The PostMortemAgent is independent of the per-cycle path and is
triggered manually via the API (the bot has no built-in scheduler).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseAgent

log = logging.getLogger("efloud.agents.roles")


# ── LTF/MTF signal validator ──────────────────────────────────────────────

class SignalValidatorAgent(BaseAgent):
    """Validates LTF/MTF structure of a candidate signal.

    Sees: ``symbol, direction, entry, sl, tp1, confluence``.
    Does NOT see: macro/regime (RegimeAgent's job) or risk math
    (RiskReviewerAgent's job). This separation is the
    :meth:`filter_context` contract — keep it restrictive.
    """

    name = "signal_validator"

    def filter_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {k: ctx[k] for k in ("symbol", "direction", "entry", "sl",
                                     "tp1", "confluence") if k in ctx}

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        return (
            "You are SignalValidator, a focused LTF/MTF structure reviewer.\n"
            "Determine if this is institutional order flow (smart money\n"
            "entering) or a retail trap / liquidity sweep.\n\n"
            f"CONTEXT:\n{json.dumps(ctx, ensure_ascii=False, default=str)}\n\n"
            "Return JSON with EXACTLY these keys:\n"
            '  "verdict":    "ACCEPT" | "REJECT" | "NEUTRAL"\n'
            '  "confidence": float in [0.0, 1.0]\n'
            '  "reasoning":  one short sentence\n'
        )


# ── Risk reviewer ─────────────────────────────────────────────────────────

class RiskReviewerAgent(BaseAgent):
    """Reviews position-size, R:R, and SL distance.

    Sees: ``rr, size_notional_pct, sl_atr_distance``.
    Does NOT see: symbol, entry, sl. The risk agent is intentionally
    symbol-agnostic — it should reject on numbers alone.
    """

    name = "risk_reviewer"

    def filter_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {k: ctx[k] for k in ("rr", "size_notional_pct",
                                     "sl_atr_distance") if k in ctx}

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        return (
            "You are RiskReviewer, a hard-nosed position-sizer.\n"
            "You do not know the symbol — judge the NUMBERS only.\n\n"
            f"CONTEXT:\n{json.dumps(ctx, ensure_ascii=False, default=str)}\n\n"
            "Rules of thumb (you may override with reasoning):\n"
            "  - R:R < 1.5 → bias REJECT\n"
            "  - notional > 8% of balance → bias REJECT\n"
            "  - SL distance < 0.5 ATR or > 5 ATR → bias REJECT\n\n"
            "Return JSON with EXACTLY these keys:\n"
            '  "verdict":    "ACCEPT" | "REJECT" | "NEUTRAL"\n'
            '  "confidence": float in [0.0, 1.0]\n'
            '  "reasoning":  one short sentence\n'
        )


# ── Regime agent ──────────────────────────────────────────────────────────

class RegimeAgent(BaseAgent):
    """Reads macro / HTF regime context.

    Sees: ``htf_bias, adx, htf_slope_pct``.
    Does NOT see: per-trade entry/SL/TP (SignalValidator's job) or
    position-size (RiskReviewer's job).
    """

    name = "regime"

    def filter_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {k: ctx[k] for k in ("htf_bias", "adx",
                                     "htf_slope_pct") if k in ctx}

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        return (
            "You are Regime, a macro/HTF context reader.\n"
            "Decide if the regime is trading-friendly for the proposed\n"
            "direction. You do not see per-trade details.\n\n"
            f"CONTEXT:\n{json.dumps(ctx, ensure_ascii=False, default=str)}\n\n"
            "Return JSON with EXACTLY these keys:\n"
            '  "verdict":    "ACCEPT" | "REJECT" | "NEUTRAL"\n'
            '  "confidence": float in [0.0, 1.0]\n'
            '  "reasoning":  one short sentence\n'
        )


# ── Overseer ──────────────────────────────────────────────────────────────

class OverseerAgent(BaseAgent):
    """Synthesises sub-agent verdicts into a final team call.

    The Overseer is the ONLY agent that sees the full set of sub-agent
    outputs. It is intentionally NOT given the original trade context
    — that would re-introduce echoing. It reasons ONLY on what the
    other agents decided.
    """

    name = "overseer"

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        verdicts = ctx.get("agent_verdicts", [])
        return (
            "You are Overseer, the strict judge of the agent team.\n"
            "Each sub-agent below has already decided on its own slice\n"
            "of the trade. Synthesise them into a final call. Do NOT\n"
            "re-derive the trade from raw context — that is not your job.\n\n"
            f"SUB-AGENT VERDICTS:\n"
            f"{json.dumps(verdicts, ensure_ascii=False, default=str)}\n\n"
            "Return JSON with EXACTLY these keys:\n"
            '  "verdict":    "ACCEPT" | "REJECT" | "NEUTRAL"\n'
            '  "confidence": float in [0.0, 1.0]\n'
            '  "reasoning":  one short sentence\n'
        )


# ── Post-Mortem (cycle-external) ──────────────────────────────────────────

class PostMortemAgent(BaseAgent):
    """Reads the closed-trade journal and writes a markdown report.

    Cycle-external: invoked from a daily/weekly job, not the hot
    trading path. Returns the absolute path of the written file. The
    LLM is asked for a structured verdict schema (win-rate forecast,
    common loss reasons, top-3 improvement suggestions); the agent
    writes the markdown scaffold around whatever the model returns so
    a missing API key still produces a deterministic report shell.
    """

    name = "post_mortem"

    def review(self, ctx: Dict[str, Any]) -> "AgentVerdict":  # type: ignore[override]
        """The PostMortem agent does not follow the standard per-cycle
        review contract. It is invoked via :meth:`write_report`.
        """
        return _verdict_from_payload(self.name, {})

    def write_report(self, journal_path: str, reports_dir: str = "./reports",
                     *, schedule: str = "daily") -> str:
        """Analyse ``journal_path`` and write a markdown report.

        Args:
            journal_path: Path to ``state/trade_journal.jsonl`` (or any
                similar JSONL with the ``TradeSnapshot`` schema).
            reports_dir:  Directory to write the markdown into.
            schedule:     ``"daily"`` or ``"weekly"`` — adjusts the
                prompt's framing but not the schema.

        Returns:
            Absolute path of the generated ``.md`` file.

        Side effects:
            Creates ``reports/`` if missing. Reads up to 500 lines from
            the tail of the journal to bound the LLM input.
        """
        # 1. Load the last N closed trades.
        trades = _read_journal_tail(journal_path, max_lines=500)

        # 2. Compute the deterministic baselines (no LLM needed for these).
        stats = _summarize_trades(trades)

        # 3. Ask the LLM for qualitative interpretation.
        prompt = self._build_prompt(stats, schedule=schedule)
        llm_payload = self.client.complete_json(prompt) or {}

        # 4. Compose the markdown — LLM-flavoured but always complete.
        ts_label = time.strftime("%Y%m%d")
        out_dir = Path(reports_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"post_mortem_{ts_label}.md"

        md = _render_markdown(stats=stats, llm_payload=llm_payload, schedule=schedule)
        out_path.write_text(md, encoding="utf-8")
        log.info(f"PostMortemAgent wrote {out_path}")
        return str(out_path.resolve())

    @staticmethod
    def _build_prompt(stats: Dict[str, Any], *, schedule: str) -> str:
        return (
            f"You are a {schedule} post-mortem reviewer for a Binance USDT-M\n"
            "futures trading bot. The deterministic stats below are the truth;\n"
            "your job is qualitative interpretation.\n\n"
            f"STATS:\n{json.dumps(stats, ensure_ascii=False, default=str)}\n\n"
            "Return JSON with EXACTLY these keys:\n"
            '  "win_rate_forecast": float 0.0-1.0 (next-N-trade expected win rate)\n'
            '  "common_loss_reasons": list[str] (3-5 short phrases)\n'
            '  "improvement_suggestions": list[str] (exactly 3 short items)\n'
        )


# ── Helpers (module-private) ──────────────────────────────────────────────


def _verdict_from_payload(name: str, data: Dict[str, Any]) -> Any:  # type: ignore[name-defined]
    """Re-exported from base to avoid a circular import for the
    PostMortemAgent.review shim above.
    """
    from .base import _verdict_from_payload as _impl
    return _impl(name, data)


def _read_journal_tail(path: str, max_lines: int = 500) -> List[Dict[str, Any]]:
    """Best-effort read of the last N JSONL records.

    Empty / missing / unparseable files are returned as ``[]`` — the
    caller will still emit a report shell so the operator sees the gap.
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            tail = f.readlines()[-max_lines:]
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def _summarize_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute deterministic baseline stats from the journal.

    The LLM cannot hallucinate these — they're the ground truth. The
    LLM is only asked for qualitative interpretation on top.
    """
    n = len(trades)
    closed = [t for t in trades if t.get("exit_price") is not None]
    pnl_values = [float(t.get("realized_pnl", 0.0) or 0.0) for t in closed]
    winners = [p for p in pnl_values if p > 0]
    losers = [p for p in pnl_values if p < 0]
    win_rate = (len(winners) / len(pnl_values)) if pnl_values else 0.0
    avg_win = (sum(winners) / len(winners)) if winners else 0.0
    avg_loss = (sum(losers) / len(losers)) if losers else 0.0
    profit_factor = (
        abs(sum(winners) / sum(losers)) if losers and sum(losers) != 0
        else float("inf") if winners else 0.0
    )
    return {
        "n_records": n,
        "n_closed": len(closed),
        "n_winners": len(winners),
        "n_losers": len(losers),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "total_pnl": round(sum(pnl_values), 2),
        "profit_factor": (round(profit_factor, 2)
                          if profit_factor != float("inf") else None),
    }


def _render_markdown(*, stats: Dict[str, Any], llm_payload: Dict[str, Any],
                     schedule: str) -> str:
    """Compose a markdown report. Always complete; LLM just fills colour."""
    common = llm_payload.get("common_loss_reasons") or []
    improvements = llm_payload.get("improvement_suggestions") or []
    forecast = llm_payload.get("win_rate_forecast")

    lines: List[str] = [
        f"# Post-Mortem ({schedule})",
        "",
        f"_Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}_",
        "",
        "## Deterministic Stats",
        "",
        f"- Records: **{stats['n_records']}**",
        f"- Closed trades: **{stats['n_closed']}**",
        f"- Win rate: **{stats['win_rate']*100:.1f}%** "
        f"({stats['n_winners']}W / {stats['n_losers']}L)",
        f"- Average win: **${stats['avg_win']:.2f}**",
        f"- Average loss: **${stats['avg_loss']:.2f}**",
        f"- Total realised PnL: **${stats['total_pnl']:.2f}**",
        f"- Profit factor: **{stats['profit_factor']}**",
        "",
        "## Win-Rate Forecast",
        "",
    ]
    if forecast is not None:
        lines.append(f"- Next-period expected win rate: **{float(forecast)*100:.1f}%**")
    else:
        lines.append("- Next-period expected win rate: _LLM did not return a forecast_")
    lines.append("")

    lines.append("## Common Loss Reasons")
    lines.append("")
    if common:
        for r in common[:5]:
            lines.append(f"- {r}")
    else:
        lines.append("- _LLM did not surface any specific loss reasons_")
    lines.append("")

    lines.append("## Top-3 Improvement Suggestions")
    lines.append("")
    if improvements:
        for i, s in enumerate(improvements[:3], start=1):
            lines.append(f"{i}. {s}")
    else:
        lines.append("_LLM did not surface any specific suggestions_")
    lines.append("")
    return "\n".join(lines)
