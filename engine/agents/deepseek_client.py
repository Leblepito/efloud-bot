import os
import logging
import json
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

log = logging.getLogger("efloud.agents.deepseek")

DEFAULT_MODEL = "deepseek-chat"

class DeepSeekClient:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        if OpenAI is None:
            raise ImportError("openai package required for DeepSeekClient")
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            log.warning("DeepSeek API key not set")
        self.model = model
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        ) if self.api_key else None

    def complete_json(self, prompt: str) -> dict:
        if not self.client:
            return {}
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Respond only with valid JSON. No markdown code fences."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            log.warning(f"DeepSeek API error: {e}")
            return {}