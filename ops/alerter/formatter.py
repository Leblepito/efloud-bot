import pydantic
from typing import Optional

class StructuredAlert(pydantic.BaseModel):
    """Pydantic schema for structured alert notifications (Genkit compliant)."""
    emoji: str
    title: str
    severity: str  # "INFO" | "WARNING" | "CRITICAL"
    event_type: str  # "breaker" | "health" | "trade_opened" | "trade_closed" | "tp1_hit" | "overseer"
    summary: str
    details: str
    action_required: Optional[str] = None

def render_alert_html(alert: StructuredAlert) -> str:
    """Render a structured alert into consistent, beautiful Telegram HTML format."""
    lines = [
        f"{alert.emoji} <b>{alert.title}</b> ({alert.severity})",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Event:</b> <code>{alert.event_type}</code>",
        f"<b>Summary:</b> {alert.summary}",
        f"<b>Details:</b> {alert.details}"
    ]
    if alert.action_required:
        lines.append(f"\n⚠️ <b>Action Required:</b> <i>{alert.action_required}</i>")
    return "\n".join(lines)

import os
import json
import httpx
import logging

log = logging.getLogger("efloud.alerter.formatter")

def format_alert_with_ai(raw_text: str, severity: str, alert_key: str) -> str:
    """Structure alerts via the advisory LLM (default Claude, gemini fallback via
    ``LLM_PROVIDER``). Falls back to ``raw_text`` on any failure (no key, HTTP,
    parse) — the shared client returns ``{}`` and parsing/fence-stripping is
    handled there, so a broken LLM never drops an operator alert."""
    # Determine event type from alert_key
    event_type = "overseer"
    for prefix in ["breaker", "health", "trade"]:
        if alert_key.startswith(prefix):
            event_type = prefix
            break
    if "tp1" in alert_key:
        event_type = "tp1_hit"
    elif "closed" in alert_key:
        event_type = "trade_closed"
    elif "opened" in alert_key:
        event_type = "trade_opened"

    prompt = f"""
    You are an expert crypto system administrator formatting notifications for a Binance SMC trade bot.
    Structure the following raw alert:
    Raw Alert: "{raw_text}"
    Severity: "{severity}"
    Event Type: "{event_type}"

    Output exactly a JSON object conforming to this schema:
    {{
      "emoji": "Single emoji describing the event",
      "title": "Short title in English",
      "severity": "{severity}",
      "event_type": "{event_type}",
      "summary": "Brief 1-sentence Turkish summary",
      "details": "Factual details of the event in Turkish",
      "action_required": "Action operator must take in Turkish (if any, otherwise null)"
    }}
    Do not include any backticks or markdown, just raw JSON.
    """

    try:
        # Lazy import: the alerter shares the bot image, so engine is importable.
        from engine.agents.llm import make_llm_client
        parsed = make_llm_client().complete_json(prompt, timeout=8.0)
        if parsed:
            alert = StructuredAlert(**parsed)
            return render_alert_html(alert)
    except Exception as e:
        log.warning(f"Failed to format alert with AI, falling back to raw: {e}")

    return raw_text

