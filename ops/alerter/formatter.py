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
