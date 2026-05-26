# Firebase Genkit / Pydantic Structured Output Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alerter modülü tarafından gönderilen tüm Telegram bildirimlerini, Pydantic ve Gemini API (Genkit standardı) ile yapılandırılmış (structured JSON output) ve görsel olarak zengin, tutarlı HTML formatına dönüştüren asenkron ve yedekli (fallback-safe) bir biçimlendirme katmanı eklemek.

**Architecture:**
1. `ops/alerter/formatter.py` modülü `StructuredAlert` Pydantic şemasını barındırır.
2. `format_alert_with_ai` fonksiyonu, raw log girdisini veya kural tabanlı alert metnini alır, Gemini 1.5 Flash API'sine `response_schema` (Pydantic model) vererek asenkron çağrıda bulunur ve mükemmel yapıda JSON alır.
3. Alınan JSON verisini, Telegram'da zengin HTML formatında (emoji, kalın çizgiler, kalın başlıklar, detay bloku, action-required alanı) render eden bir şablon motoru çalışır.
4. **Graceful Degradation**: Eğer API key yoksa veya timeout/hata alınırsa, kural tabanlı orijinal alert metni doğrudan ve kayıpsız bir şekilde Telegram'a gönderilir.

**Tech Stack:** Python 3.10+, Pydantic, HTTPX, Gemini API, pytest.

---

### Task 1: Structured Output Schema & Template definition

**Files:**
- Create: `ops/alerter/formatter.py`
- Test: `tests/alerter/test_alerter_formatter.py`

- [ ] **Step 1: Write the failing test**
  `tests/alerter/test_alerter_formatter.py` dosyasını oluşturarak alert biçimlendiricinin Pydantic şema validasyonunu ve HTML şablon render çıktısını test eden TDD testini yazın.
  ```python
  import pytest
  from ops.alerter.formatter import StructuredAlert, render_alert_html

  def test_structured_alert_validation():
      alert = StructuredAlert(
          emoji="🚨",
          title="Daily Loss Limit Breached",
          severity="CRITICAL",
          event_type="breaker",
          summary="Daily loss exceeds 3.0% limit",
          details="Starting balance: 10000, current: 9650",
          action_required="Check open positions and logs immediately."
      )
      assert alert.severity == "CRITICAL"
      assert alert.event_type == "breaker"

  def test_render_alert_html():
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
      assert "<b>Event:</b> breaker" in html
      assert "<b>Action Required:</b>" in html
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `$env:PYTHONPATH="."; .venv\Scripts\pytest tests/alerter/test_alerter_formatter.py -v`
  Expected: FAIL (ModuleNotFoundError: No module named 'ops.alerter.formatter')

- [ ] **Step 3: Write minimal implementation**
  `ops/alerter/formatter.py` dosyasını oluşturarak Pydantic şemasını ve HTML render motorunu yazın.
  ```python
  import pydantic
  from typing import Optional

  class StructuredAlert(pydantic.BaseModel):
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
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `$env:PYTHONPATH="."; .venv\Scripts\pytest tests/alerter/test_alerter_formatter.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add ops/alerter/formatter.py tests/alerter/test_alerter_formatter.py
  git commit -m "feat(alerter): define pydantic schema and rendering template for structured alerts"
  ```

---

### Task 2: Gemini AI Formatter Integration with Pydantic Schema

**Files:**
- Modify: `ops/alerter/formatter.py`
- Test: `tests/alerter/test_alerter_formatter_ai.py`

- [ ] **Step 1: Write the failing test**
  `tests/alerter/test_alerter_formatter_ai.py` dosyasını oluşturup, mock Gemini API çağrıları üzerinden raw log girdilerinin Pydantic StructuredAlert modellerine başarıyla parse edildiğini test edin.
  ```python
  import pytest
  from unittest.mock import patch, MagicMock
  from ops.alerter.formatter import format_alert_with_ai

  def test_format_alert_with_ai_fallback():
      # No API key configured -> should return raw text immediately (graceful degradation)
      with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
          res = format_alert_with_ai("raw alert message", "WARNING", "breaker.tripped.consecutive")
          assert res == "raw alert message"

  @patch("httpx.post")
  def test_format_alert_with_ai_success(mock_post):
      # Mock successful Gemini API response returning JSON structure
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
      
      with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
          res = format_alert_with_ai("raw msg", "WARNING", "breaker.tripped.consecutive")
          assert "⚠️ <b>Breaker Tripped</b>" in res
          assert "<b>Event:</b> <code>breaker</code>" in res
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `$env:PYTHONPATH="."; .venv\Scripts\pytest tests/alerter/test_alerter_formatter_ai.py -v`
  Expected: FAIL (AttributeError: 'module' object has no attribute 'format_alert_with_ai')

- [ ] **Step 3: Write minimal implementation**
  `ops/alerter/formatter.py` içine Gemini API structured JSON asenkron/senkron HTTP çağrısını kodlayın:
  ```python
  import os
  import json
  import httpx
  import logging
  from typing import Dict, Any

  log = logging.getLogger("efloud.alerter.formatter")

  def format_alert_with_ai(raw_text: str, severity: str, alert_key: str) -> str:
      """Uses Gemini API with response_schema to structure alerts. Fallback to raw_text on failure."""
      api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
      if not api_key:
          return raw_text

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

      url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
      headers = {"Content-Type": "application/json"}
      payload = {
          "contents": [{"parts": [{"text": prompt}]}],
          "generationConfig": {
              "responseMimeType": "application/json",
          }
      }

      try:
          resp = httpx.post(url, headers=headers, json=payload, timeout=8.0)
          if resp.status_code == 200:
              data = resp.json()
              raw_json = data["candidates"][0]["content"]["parts"][0]["text"].strip()
              
              if raw_json.startswith("```"):
                  lines = raw_json.split("\n")
                  raw_json = "\n".join([line for line in lines if not line.startswith("```")])
                  
              parsed = json.loads(raw_json)
              alert = StructuredAlert(**parsed)
              return render_alert_html(alert)
          else:
              log.warning(f"Gemini API formatting error {resp.status_code}: {resp.text}")
      except Exception as e:
          log.warning(f"Failed to format alert with AI, falling back to raw: {e}")

      return raw_text
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `$env:PYTHONPATH="."; .venv\Scripts\pytest tests/alerter/test_alerter_formatter_ai.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add ops/alerter/formatter.py tests/alerter/test_alerter_formatter_ai.py
  git commit -m "feat(alerter): implement AI structured output formatter with robust fallback"
  ```

---

### Task 3: Wiring Structured Output Formatter into Alerter Loop

**Files:**
- Modify: `ops/alerter/alerter.py`
- Modify: `ops/alerter/rules.py`
- Test: `tests/test_alerter_e2e.py`

- [ ] **Step 1: Write/Review the test**
  Alerter E2E test suite (`tests/test_alerter_e2e.py`)'yi koşturarak mevcut testler ile uyumluluğunu doğrulayın.

- [ ] **Step 2: Modify `ops/alerter/alerter.py`**
  `Alerter._maybe_fire` metodunu AI formatlama katmanı üzerinden geçecek şekilde düzenleyin.
  ```python
  # ops/alerter/alerter.py'ye import ekle:
  from ops.alerter.formatter import format_alert_with_ai

  # _maybe_fire metodunun sonunu güncelle:
  # ... ok = send_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, text) satırı yerine:
  formatted_text = format_alert_with_ai(text, rule.severity, rule.alert_key)
  ok = send_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, formatted_text)
  ```

- [ ] **Step 3: Run the test suite to verify it passes**
  Run: `$env:PYTHONPATH="."; .venv\Scripts\pytest tests/test_alerter_e2e.py -v`
  Expected: PASS

- [ ] **Step 4: Commit**
  ```bash
  git add ops/alerter/alerter.py
  git commit -m "feat(alerter): wire structured AI alert formatter into Alerter main loop"
  ```

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-firebase-genkit-structured-output.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
