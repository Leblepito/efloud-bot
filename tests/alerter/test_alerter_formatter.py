import pytest
from ops.alerter.formatter import StructuredAlert, render_alert_html

def test_structured_alert_validation():
    """Verify that StructuredAlert Pydantic model correctly validates input fields."""
    alert = StructuredAlert(
        emoji="🚨",
        title="Daily Loss Limit Breached",
        severity="CRITICAL",
        event_type="breaker",
        summary="Daily loss exceeds 3.0% limit",
        details="Starting balance: 10000, current: 9650",
        action_required="Check open positions and logs immediately."
    )
    assert alert.emoji == "🚨"
    assert alert.title == "Daily Loss Limit Breached"
    assert alert.severity == "CRITICAL"
    assert alert.event_type == "breaker"
    assert alert.summary == "Daily loss exceeds 3.0% limit"
    assert alert.details == "Starting balance: 10000, current: 9650"
    assert alert.action_required == "Check open positions and logs immediately."

def test_structured_alert_optional_fields():
    """Verify that StructuredAlert allows action_required to be optional/None."""
    alert = StructuredAlert(
        emoji="📈",
        title="Position Opened",
        severity="INFO",
        event_type="trade_opened",
        summary="LONG BTC/USDT opened at 62500",
        details="Size: 0.1 BTC, SL: 61000, TP: 65000"
    )
    assert alert.action_required is None

def test_render_alert_html():
    """Verify that render_alert_html generates beautiful HTML containing key alert components."""
    alert = StructuredAlert(
        emoji="🚨",
        title="Daily Loss Limit Breached",
        severity="CRITICAL",
        event_type="breaker",
        summary="Daily loss exceeds 3.0% limit",
        details="Starting balance: 10000, current: 9650",
        action_required="Check open positions and logs immediately."
    )
    html = render_alert_html(alert)
    
    assert "🚨 <b>Daily Loss Limit Breached</b>" in html
    assert "(CRITICAL)" in html
    assert "━━━━━━━━━━━━━━━━━━━━━━━━━━" in html
    assert "<b>Event:</b> <code>breaker</code>" in html
    assert "<b>Summary:</b> Daily loss exceeds 3.0% limit" in html
    assert "<b>Details:</b> Starting balance: 10000, current: 9650" in html
    assert "⚠️ <b>Action Required:</b> <i>Check open positions and logs immediately.</i>" in html
