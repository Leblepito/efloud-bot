import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Any

class SentimentCache:
    """SHA-256 JSON-based semantic caching layer for LLM requests."""
    
    def __init__(self, cache_dir: str = "state/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[Dict[str, Any]]:
        h = self._get_hash(text)
        cache_file = self.cache_dir / f"{h}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def set(self, text: str, data: Dict[str, Any]) -> None:
        h = self._get_hash(text)
        cache_file = self.cache_dir / f"{h}.json"
        cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
