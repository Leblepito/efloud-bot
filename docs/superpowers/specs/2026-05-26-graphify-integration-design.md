# Design Spec: Graphify Cognitive & Architectural Integration

**Date:** 2026-05-26  
**Author:** Antigravity (Orchestrator)  
**Topic:** Exposing Graphify codebase representation, integrating cognitive MCP tools, and absorbing advanced patterns (parallel processing, caching, and auto-reporting) into the Efloud trading ecosystem.

---

## 1. Overview & Context

`graphify` is an advanced cognitive tool that builds a navigable knowledge graph of codebases, research corpora, or raw document directories. By integrating it into `efloud-bot`, we achieve a three-fold leverage:
1. **Goal C (Visualization):** Extract and generate a complete codebase graph of the trading bot for documentation and visual overview.
2. **Goal A (Agent Empowerment):** Expose this graph to workspace agents (Antigravity, Hermes) via native rules, workflows, and a stdio MCP server for live BFS/DFS code navigation.
3. **Goal B (Concept Absorption):** Refactor the trading bot's AI Sentiment and reporting layers to adopt graphify's elite architectural patterns: parallel LLM chunking, SHA-256 state/semantic caching, and otonom markdown trade excursion reports.

---

## 2. Proposed Roadmap

### Phase 1: Codebase Graph Generation (Goal C)
- Run `graphify` extraction on the `efloud-bot` codebase.
- Use the local `python` interpreter with editable `graphify` installation.
- Generate `graphify-out/graph.json` (Ham Graph), `graphify-out/graph.html` (Interactive Web UI), and `graphify-out/GRAPH_REPORT.md` (Audit Report).

### Phase 2: Cognitive Agent & MCP Integration (Goal A)
- Run `python -m graphify antigravity install` to generate `.agents/rules` and `.agents/workflows` for Google Antigravity.
- Run `python -m graphify hermes install` to register the skill inside the Hermes co-pilot workspace.
- Start and test the graphify stdio MCP server exposing `query_graph`, `shortest_path`, and `god_nodes` to the workspace.

### Phase 3: Architectural Refactoring of Efloud-Bot (Goal B)
- **Pattern A (Parallel LLM Chunking):** Refactor `engine/ai/sentiment.py` to chunk incoming stream data and process via parallel subagents.
- **Pattern B (State/Sentiment Caching):** Implement a robust SHA-256 caching layer under `state/cache/` to cache news/market sentiment requests and prevent redundant LLM billing.
- **Pattern C (Otonom Trade Excursion Reporting):** Create an automated DAILY_TRADE_REPORT generator in `reports/` summarizing daily performance, MAE/MFE excursions, slippage, and AI sentiment reasoning in premium markdown formats.

---

## 3. Detailed Component Designs

### 3.1. Phase 1: Codebase Visualizer
- **Command:** `python -m graphify extract . --backend gemini --token-budget 60000 --max-concurrency 4`
- **Verification:** Ensure `graphify-out/graph.html` and `GRAPH_REPORT.md` compile successfully.

### 3.2. Phase 2: Agent Skill Registration
- **Rules generation:** Creates `.agents/rules/graphify.md` directing the agent to search `graphify-out/graph.json` when answering questions.
- **MCP server integration:** Exposes standard query commands so the agent can trace imports and call paths otonomously.

### 3.3. Phase 3: Architectural Absorptions
#### Caching Layer Spec (`utils/cache.py`)
```python
import hashlib
import json
from pathlib import Path
from typing import Optional, Any

class SentimentCache:
    def __init__(self, cache_dir: str = "state/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[Dict[str, Any]]:
        h = self._get_hash(text)
        cache_file = self.cache_dir / f"{h}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        return None

    def set(self, text: str, data: Dict[str, Any]) -> None:
        h = self._get_hash(text)
        cache_file = self.cache_dir / f"{h}.json"
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

#### Parallel Processing Spec (`engine/ai/parallel_sentiment.py`)
- Split long texts/news feeds into a list of chunks.
- Spawn parallel async calls to the Gemini/Claude API to evaluate sentiment concurrently, then aggregate results.

---

## 4. Verification Plan

### Automated Verification
- Verify that `python -m graphify extract` runs cleanly without syntax or API errors.
- Confirm `python -m pytest` passes completely after refactoring `engine/ai/sentiment.py` to verify caching and parallel processing.

### Manual Verification
- Deploy to staging/Hetzner and check if the daily auto-report generator outputs `reports/DAILY_TRADE_REPORT.md` cleanly.
- Verify `graph.html` renders beautifully in local browser.
