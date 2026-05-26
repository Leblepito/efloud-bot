import pytest
from unittest.mock import patch, MagicMock
from ops.alerter.formatter import format_alert_with_ai

def test_format_alert_with_ai_fallback():
    """Verify that format_alert_with_ai returns raw text immediately if no GEMINI_API_KEY is configured (graceful degradation)."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        res = format_alert_with_ai("raw alert message", "WARNING", "breaker.tripped.consecutive")
        assert res == "raw alert message"

@patch("httpx.post")
def test_format_alert_with_ai_success(mock_post):
    """Verify that format_alert_with_ai correctly parses Gemini API JSON response and renders it to structured HTML."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"emoji": "⚠️", "title": "Breaker Tripped", "severity": "WARNING", "event_type": "breaker", "summary": "Consecutive losses exceeded", "details": "3 consecutive losses", "action_required": "Check strategies"}'
                        }
                    ]
                }
            }
        ]
    }
    mock_post.return_value = mock_response
    
    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_gemini_key"}):
        res = format_alert_with_ai("raw msg", "WARNING", "breaker.tripped.consecutive")
        
        # Verify rendered HTML sections
        assert "⚠️ <b>Breaker Tripped</b>" in res
        assert "(WARNING)" in res
        assert "<b>Event:</b> <code>breaker</code>" in res
        assert "<b>Summary:</b> Consecutive losses exceeded" in res
        assert "<b>Details:</b> 3 consecutive losses" in res
        assert "⚠️ <b>Action Required:</b> <i>Check strategies</i>" in res
        mock_post.assert_called_once()
