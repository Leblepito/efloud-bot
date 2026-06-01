## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## autoresearch

This project has an autonomous trading strategy backtest optimizer at `scripts/autoresearch/` built on self-modifying parameters and backtest evaluation loop patterns.

When the user types `/optimize` or requests strategy optimization:
- Propose a branch `strategy-opt/<tag>` and run: `git checkout -b strategy-opt/<tag>`.
- Read and follow all instructions under `scripts/autoresearch/program.md`.
- Run the infinite self-optimizing training and backtest evaluation loop autonomously.
- Log results in `scripts/autoresearch/results.tsv`.

## Runtime Agent Team (canonical Part A)

There is a runtime multi-agent LLM layer under `engine/agents/`:
- `GeminiClient` — single source of truth for all Gemini REST calls.
- `BaseAgent` / `AgentVerdict` — uniform per-role verdict schema.
- `SignalValidatorAgent` / `RiskReviewerAgent` / `RegimeAgent` /
  `OverseerAgent` — per-trade advisory roles. Per-role
  `filter_context` is a *passive whitelist* (prompt-level field
  selection), not an enforced isolation; the Overseer is the only
  agent with a real isolation guarantee (sees only the sub-agent
  verdicts).
- `PostMortemAgent` — cycle-external; reads the trade journal and
  writes a markdown report under `reports/`. The bot has no
  built-in scheduler — post-mortem is triggered manually via
  `POST /api/ai/post-mortem?schedule=daily|weekly`.
- `AgentTeam` — wires the sub-agents and persists the disagreement
  log (`state/agent_disagreements.jsonl`). The orchestrator applies
  the `gating: true` hard-veto check; the team itself does not
  implement a sub-agent-override rule.

By default `agent_team.gating` is `false` — the team runs in **shadow
mode**: verdicts are logged and persisted, but the deterministic
guard/breaker pipeline is **not** modified. Do not flip `gating` to
`true` without a documented shadow-mode observation period.

When the user types `/agents` or asks for the latest verdicts, hit
`GET /api/ai/agents` (FastAPI). To trigger a post-mortem manually,
`POST /api/ai/post-mortem?schedule=daily|weekly`.

## Dev-time Claude Code team (canonical Part B)

The `.claude/` directory contains:
- `agents/*.md` — subagent definitions (existing `efloud-*` agents +
  the five from Part B: `smc-strategy-reviewer`, `risk-safety-auditor`,
  `backtest-runner`, `api-integration`, `agent-team-engineer`).
- `skills/writing-plans/` — `obra/superpowers`-style implementation
  plan writer.
- `skills/claude-automation-recommender/` — read-only repo analyser
  for Claude Code automations.
- `settings.json` — hooks (graphify nudge) + experimental agent
  teams flag.

When the user asks to plan a multi-step change, use the
`writing-plans` skill. When the user asks "what Claude Code
automations should I add?", use `claude-automation-recommender`.


