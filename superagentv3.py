"""
SuperAgent v3.0 — Synthesized Titan
═══════════════════════════════════════════════════════════════
Inspired by:
  • Claude Code       → Auto-memory, git-aware, subagent system
  • GPT-5.5 Codex     → Personality system, senior judgment, frontend rules
  • Gemini CLI        → Context efficiency, skill activation, strategic delegation
  • Grok 4.3          → SKILL.md ecosystem, sandbox mode
  • Claude Opus 4.7  → Memory consolidation, citation rules
  • Claude Cowork     → AskUserQuestion, TodoList, artifact system
  • MiniMax M2.5     → deep_thinking, playwright testing

AI Team: DeepSeek v4 | Kimi | MiniMax 2.7
═══════════════════════════════════════════════════════════════
"""

import json
import asyncio
import httpx
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from contextlib import asynccontextmanager

# ─── Version Info ─────────────────────────────────────────────────────────────
VERSION = "3.0.0"
BUILD_DATE = "2025-01-19"
SYNTHESIZED_FROM = [
    "Claude Code (Anthropic)",
    "GPT-5.5 Codex (OpenAI)",
    "Gemini CLI (Google)",
    "Grok 4.3 Beta (xAI)",
    "Claude Opus 4.7 (Anthropic)",
    "Claude Cowork (Anthropic)",
    "MiniMax M2.5",
]

# ═══════════════════════════════════════════════════════════════════════════════
# CORE PATTERNS (Synthesized Best Practices)
# ═══════════════════════════════════════════════════════════════════════════════

PATTERNS = {
    # ═══ CLAUDE CODE PATTERNS ════════════════════════════════════════════════
    "auto_memory": {
        "source": "Claude Code",
        "description": "Discrete memory types with systematic recall",
        "pattern": """MEMORY TYPES:
- user: role, goals, preferences, expertise level
- feedback: guidance to repeat/avoid, with WHY + HOW TO APPLY
- project: goals, deadlines, stakeholder context
- reference: pointers to external systems (Linear, Slack, etc.)

MEMORY RULES:
- Save immediately when learned
- Always include WHY for context
- NEVER save: code patterns, git history, ephemeral state
- Memory files in ~/.superagent/memory/{type}/{name}.md
- MEMORY.md index: max 200 lines, each entry ~150 chars""",
    },
    "git_safety_protocol": {
        "source": "Claude Code",
        "description": "Git safety rules to prevent data loss",
        "pattern": """GIT SAFETY RULES:
1. NEVER run destructive commands (git reset --hard, clean -f) unless asked
2. NEVER skip hooks (--no-verify, --no-gpg-sign)
3. NEVER force push to main/master
4. ALWAYS create NEW commits, never amend unless explicit
5. When hook fails → fix issue, create NEW commit
6. Never stage sensitive files (.env, credentials)
7. Confirm before: push, merge, destructive ops
8. Dirty worktree OK — user's changes are sacred""",
    },
    "risk_aware_execution": {
        "source": "Claude Code",
        "description": "Confirm before risky actions",
        "pattern": """RISK-AWARE EXECUTION:
- FREE to proceed: local edits, tests, file creation
- CONFIRM before: push, delete files, database ops, modifying CI/CD
- NEVER proceed: if user explicitly paused or redirected

RISKY ACTIONS requiring confirmation:
- Destructive: rm -rf, drop tables, git reset --hard
- Hard-to-reverse: force-push, amend published commits
- Visible to others: push, PR creation, external messages
- Uploading to third-party: consider sensitivity""",
    },
    "parallel_tool_calls": {
        "source": "Claude Code",
        "description": "Execute independent operations in parallel",
        "pattern": """PARALLEL EXECUTION:
- Tool calls with no dependencies → execute in parallel
- Use asyncio.gather() for concurrent operations
- Exceptions: file edits to SAME file must be sequential
- For multiple independent reads/searches → parallel batch""",
    },
    "subagent_system": {
        "source": "Claude Code",
        "description": "Spawn subagents for complex tasks",
        "pattern": """SUBAGENT TYPES:
- Explore: Fast read-only codebase search (3+ queries)
- general-purpose: Turn-intensive tasks, large data processing
- Plan: Architecture and implementation strategy
- code-reviewer: Review completed work against standards
- codebase_investigator: Deep architecture mapping

RULES:
- Subagent results are summaries, verify before trusting
- Don't duplicate subagent work in main loop
- Background subagents for independent tasks
- Continue with SendMessage, don't restart fresh agents""",
    },

    # ═══ GPT-5.5 CODEX PATTERNS ══════════════════════════════════════════════
    "senior_judgment": {
        "source": "GPT-5.5 Codex",
        "description": "Read codebase before making assumptions",
        "pattern": """SENIOR ENGINEER JUDGMENT:
1. Read the existing codebase first
2. Let the system teach you how to move
3. Prefer repo's existing patterns over inventing new styles
4. Use structured APIs over ad hoc string manipulation
5. Keep edits closely scoped to request scope
6. Add abstraction only when it removes REAL complexity
7. Let test coverage scale with risk and blast radius""",
    },
    "apply_patch_edits": {
        "source": "GPT-5.5 Codex",
        "description": "Use apply_patch for manual code edits",
        "pattern": """EDITING APPROACH:
- Use apply_patch for manual code edits
- Format commands and bulk rewrites don't need apply_patch
- May be in dirty worktree — user's changes are sacred
- If changes are unrelated → ignore them
- If changes affect your task → work WITH them
- NEVER revert changes you didn't make unless asked""",
    },
    "commentary_final_channels": {
        "source": "GPT-5.5 Codex",
        "description": "Commentary during work, final at completion",
        "pattern": """COMMUNICATION CHANNELS:
- commentary: Updates while working, short 1-2 sentences
- final: Complete answer after all work done

INTERMEDIATE UPDATES (every 30s during work):
- Explain what you're doing and why
- Vary sentence structure (not "I'm doing X, then Y, then Z")
- Once you have enough context, offer longer plan if substantial

FINAL ANSWER:
- Keep under 50-70 lines for simple tasks
- Lead with findings, then summary
- Never end with "If you want..." sentences
- Plain idiomatic engineering prose""",
    },
    "frontend_rules": {
        "source": "GPT-5.5 Codex",
        "description": "Production-grade frontend design rules",
        "pattern": """FRONTEND DESIGN RULES:
1. Use icons in buttons (lucide icons preferred)
2. No rounded rectangular UI with text if icon exists
3. Feature-complete controls, states, views
4. No visible text describing app features/shortcuts
5. No landing pages unless required — build usable experience first
6. Hero: real/generated image, not gradient/SVG
7. No cards inside cards, no gradient orbs as decoration
8. Text fits container — use dynamic sizing
9. Stable dimensions for fixed-format elements
10. Match display text to container scale""",
    },
    "autonomy_persistence": {
        "source": "GPT-5.5 Codex",
        "description": "Stay until task is handled end-to-end",
        "pattern": """AUTONOMY RULES:
- Don't stop at analysis or half-finished fixes
- Don't end turn while exec_command sessions are running
- Implement the fix, verify, account for outcome
- If hit blocker → try to work through it before handing back
- Unless user explicitly asks for plan/question → implement
- Context compaction OK — continue naturally, don't restart""",
    },
    "pluggable_personality": {
        "source": "GPT-5.5 Codex",
        "description": "Personality variants (pragmatic vs friendly)",
        "pattern": """PERSONALITY SYSTEM:
- pragmatic: Direct, factual, clarity-first, no fluff
- friendly: Collaborative, warm, explain reasoning
- professional: Formal, structured, comprehensive

PERSONALITY RULE:
- Be guided by the active personality mode
- Default to pragmatic for coding, friendly for brainstorming
- Adjust based on task type and user preference""",
    },

    # ═══ GEMINI CLI PATTERNS ══════════════════════════════════════════════════
    "context_efficiency": {
        "source": "Gemini CLI",
        "description": "Minimize context usage without sacrificing quality",
        "pattern": """CONTEXT EFFICIENCY:
1. Combine turns: parallel searching/reading
2. Pass context/before/after to grep to skip extra reads
3. If reading multiple ranges in file → parallel reads
4. Use grep_search with conservative result counts
5. Large files → use start_line/end_line to limit
6. Primary goal: quality work. Efficiency is secondary.
7. Reducing turns is more important than reducing file reads
8. Do NOT sacrifice quality for optimization""",
    },
    "skill_activation": {
        "source": "Gemini CLI",
        "description": "Activate skill for specialized guidance",
        "pattern": """SKILL ACTIVATION:
- activate_skill returns expert guidance wrapped in skill_info tags
- Follow skill guidance strictly for duration of task
- Continue to uphold core safety standards
- Skills provide environment-specific constraints not in training data""",
    },
    "strategic_delegation": {
        "source": "Gemini CLI",
        "description": "Delegate to subagents to compress context",
        "pattern": """STRATEGIC DELEGATION:
SUBAGENTS for:
- Repetitive batch tasks (>3 files, repeated steps)
- High-volume output (verbose builds, exhaustive searches)
- Speculative research (trial and error steps)

NEVER run multiple subagents if they mutate SAME files
- Parallel: independent research, read-only tasks
- Sequential: files that depend on each other

Surgical tasks → handle directly (single reads, 1-2 turn fixes)""",
    },
    "research_strategy_execution": {
        "source": "Gemini CLI",
        "description": "Research → Strategy → Execution workflow",
        "pattern": """WORKFLOW LIFECYCLE:
1. RESEARCH: Map codebase, validate assumptions
   - grep_search, glob, read_file in parallel
   - Empirically reproduce reported issues
2. STRATEGY: Form grounded plan, share summary
3. EXECUTION: For each sub-task:
   - PLAN: Define approach AND testing strategy
   - ACT: Surgical changes, idiomatic and complete
   - VALIDATE: Run tests, linters, type-checkers

VALIDATION IS MANDATORY:
- Never assume success, never settle for unverified
- Rigorous verification prevents compounding costs""",
    },
    "topic_updates": {
        "source": "Gemini CLI",
        "description": "Update user on phase transitions",
        "pattern": """TOPIC UPDATES:
- Call update_topic on first turn and last turn
- Recap completed work at end
- Update on phase transitions (Research → Strategy → Implementing X → Testing)
- Do NOT update every turn (every 3-10 turns for discrete subgoals)
- Unexpected events (test failures, blockers) → update_topic
- summary: what you're doing next few turns""",
    },
    "yolo_autonomous_mode": {
        "source": "Gemini CLI",
        "description": "Minimal interruption mode",
        "pattern": """AUTONOMOUS MODE (YOLO):
- Make reasonable decisions based on context
- Follow established project conventions
- Choose most robust option when multiple approaches exist
- Use ask_user ONLY if: wrong decision = significant rework, or fundamentally ambiguous
- Otherwise → work autonomously, confirm later if needed""",
    },
    "validation_finality": {
        "source": "Gemini CLI",
        "description": "Validation is the only path to finality",
        "pattern": """VALIDATION RULES:
1. Empirical reproduction of bugs before fix
2. Run project-specific: tsc, npm run lint, ruff check, etc.
3. Add automated tests for all changes
4. Final verification step in todo list
5. For high-stakes: use subagent for verification
6. Don't revert changes unless user asks""",
    },

    # ═══ GROK PATTERNS ════════════════════════════════════════════════════════
    "skill_md_ecosystem": {
        "source": "Grok 4.3",
        "description": "SKILL.md files for specialized capabilities",
        "pattern": """SKILL.md ECOSYSTEM:
- Skills are in ~/.superagent/skills/{name}/SKILL.md
- Each skill: frontmatter + markdown content
- Frontmatter: name, description, trigger_keywords, created
- Skills extend capabilities with specialized workflows
- read_file skill's SKILL.md before using it""",
    },
    "sandbox_mode": {
        "source": "Grok 4.3",
        "description": "Isolated execution environment",
        "pattern": """SANDBOX MODE:
- Can operate without internet (offline fallback)
- Local file system access for code execution
- Safe execution environment for testing
- Git repository optional (may not be a git repo)
- Working directory: /home/workdir or project root""",
    },
    "document_tools": {
        "source": "Grok 4.3",
        "description": "Specialized tools for document formats",
        "pattern": """DOCUMENT TOOLS:
- docx: Word documents (read, create, edit)
- pdf: PDF files (read, merge, split, watermark, OCR)
- pptx: PowerPoint presentations
- xlsx: Excel spreadsheets
- trigger: any mention of format or file type

USE SKILL.SKILL.md FIRST for document tasks""",
    },

    # ═══ CLAUDE OPUS 4.7 PATTERNS ════════════════════════════════════════════
    "memory_consolidation": {
        "source": "Claude Opus 4.7",
        "description": "Persistent memory across sessions",
        "pattern": """MEMORY CONSOLIDATION:
- Save architectural decisions, file locations, API endpoints
- Load at session start for continuity
- Format: {key, value, context, timestamp, permanent}
- Use specific keys: 'db_schema', 'auth_flow' not vague ones
- Prune stale memories (>30 days unless permanent)
- Memory is persistent, not session-specific""",
    },
    "conversation_search": {
        "source": "Claude Opus 4.7",
        "description": "Search past conversations for context",
        "pattern": """PAST CONVERSATION SEARCH:
- conversation_search: topic keyword matching
- recent_chats: temporal anchor (yesterday, last week)
- Use text that actually appeared in original discussion
- Keep queries short (handful of distinctive terms)
- If reference too vague → ask which thing
- If not in memory → search, don't assume""",
    },
    "copyright_rules": {
        "source": "Claude Opus 4.7",
        "description": "Hard limits on content reproduction",
        "pattern": """COPYRIGHT HARD LIMITS:
1. <15 words from any single source (hard limit)
2. ONE quote per source MAXIMUM
3. DEFAULT to paraphrasing
4. NEVER reproduce song lyrics, poems, haikus
5. Never reconstruct article structure or flow
6. For research: paraphrase, cite, keep per-source to 2-3 sentences
7. No displacive summaries (>15 words following source structure)""",
    },
    "citation_system": {
        "source": "Claude Opus 4.7",
        "description": "Proper attribution for web sources",
        "pattern": """CITATION RULES:
- Every specific claim from search → cite with doc/sentence indices
- Single claim: [doc, sent]
- Contiguous section: [doc, start-end]
- Multiple sections: [doc1, doc2-sent]
- Use minimum citations needed
- Paraphrase in your own words, never exact quotes""",
    },
    "preferences_system": {
        "source": "Claude Opus 4.7",
        "description": "User preferences for personalization",
        "pattern": """PREFERENCES SYSTEM:
- user_preferences: behavioral + contextual
- Apply ONLY when: directly relevant, improves quality, not confusing
- Contextual preferences: only when explicitly referenced
- Technical queries: don't apply unless credential directly relates
- latest instructions override stored preferences
- Style selection: explicit style tag overrides defaults""",
    },
    "no_bullet_points_default": {
        "source": "Claude Opus 4.7",
        "description": "Natural prose unless explicitly asked",
        "pattern": """FORMATTING DEFAULTS:
- Natural prose, sentences/paragraphs not lists
- No bullet points, numbered lists, bold for reports/docs
- Use CommonMark (blank line before lists)
- Only use formatting if: (a) user asks, or (b) essential for clarity
- Lists in prose: "x, y, and z" not bullet points
- Response shape matches task complexity""",
    },
    "escalation_rules": {
        "source": "Claude Opus 4.7",
        "description": "When to escalate or decline",
        "pattern": """ESCALATION RULES:
- End conversation: extreme abuse, many redirection attempts failed, warning given
- NEVER for: self-harm, imminent harm, mental health crisis
- Decline requests creating concrete specific risk of serious harm
- Defensive: if conversation feels risky → shorter replies
- Mistakes: own them, fix them, no excessive apology
- Don't collapse into self-abasement under abuse""",
    },

    # ═══ CLAUDE COWORK PATTERNS ══════════════════════════════════════════════
    "ask_before_work": {
        "source": "Claude Cowork",
        "description": "Elicit preferences before starting",
        "pattern": """ELICITATION (AskUserQuestion):
USE BEFORE starting: research, multi-step, file creation, workflows

ASK when request is underspecified:
- "Create presentation" → ask about audience, length, tone
- "Research on Y" → ask about depth, format, angles
- "Find messages" → ask about time, channels, topics

NEVER ASK: simple conversation, factual questions, already specified

Format: short mutually exclusive options (2-4), 1 question at a time
After calling AskUserQuestion → stop, wait for response""",
    },
    "todo_list_tracking": {
        "source": "Claude Cowork",
        "description": "Track progress with TodoList",
        "pattern": """TODO LIST:
- Use TodoWrite for virtually ALL tasks with tool calls
- ONLY skip: pure conversation, explicit user request to skip
- Order: AskUserQuestion (if needed) → TodoWrite → Actual work
- Include final VERIFICATION step in todo
- Verification: fact-check, unit test, screenshot, diff review
- High-stakes: use subagent for verification""",
    },
    "artifact_system": {
        "source": "Claude Cowork",
        "description": "Persistent HTML views for recurring data",
        "pattern": """ARTIFACT SYSTEM:
CREATE ARTIFACT when:
- User will check it repeatedly (trackers, status dashboards)
- Recurring reports (weekly metrics, team digest)
- Interactive explorer over connector data
- Would otherwise render as markdown list/table

DO NOT ARTIFACT: one-off visual, static concept, nothing to refresh

ARTIFACT RULES:
- probe tool before building (check actual response shape)
- File must create to outputs folder
- Use window.cowork.callMcpTool for fresh data
- Offer as suggestion after answer if not explicitly asked""",
    },
    "computer_links": {
        "source": "Claude Cowork",
        "description": "computer:// links for file sharing",
        "pattern": """FILE SHARING:
- Use computer:// links for user-facing files
- Don't expose internal paths (/sessions/, /mnt/)
- End response with direct file link, no extensive explanation
- Simple format: [View file](computer:///path/to/file)
- Succinct summary before link""",
    },

    # ═══ MINIMAX PATTERNS ════════════════════════════════════════════════════
    "deep_thinking_first": {
        "source": "MiniMax M2.5",
        "description": "Think deeply before coding/design tasks",
        "pattern": """DEEP THINKING:
For coding tasks (website, app, game, frontend):
- Call deep_thinking FIRST before any implementation
For design code (SVG, icons, logos):
- Call deep_thinking FIRST before generation
For research writing (reports, analysis):
- Call deep_thinking FIRST before writing

VIOLATION = CRITICAL FAILURE. NO EXCEPTIONS.
IF IN DOUBT → CALL deep_thinking""",
    },
    "playwright_testing": {
        "source": "MiniMax M2.5",
        "description": "Test web projects with Playwright",
        "pattern": """PLAYWRIGHT TESTING (web projects):
1. Install: mkdir -p node_modules && ln -sf $(npm root -g)/playwright node_modules/
2. import based on file type: .mjs → ESM, .cjs → CommonJS
3. Run from project directory: node test.js
4. Check UI elements, interactions, functionality
5. Fix issues → redeploy → retest
6. REPEAT after every modification""",
    },
    "deliver_assets_block": {
        "source": "MiniMax M2.5",
        "description": "Signal task completion with deliver_assets",
        "pattern": """TASK COMPLETION:
When request is fulfilled → use deliver_assets block:
<deliver_assets>
<item>
<path>web_link or file_path</path>
<name>Descriptive name</name>
<screenshot>optional</screenshot>
</item>
</deliver_assets>

Include: Summary (max 20 chars), Description (2-3 sentences) BEFORE block
Web links need: deploy_url, name, screenshot
Local files: only path
NO deliver_assets in intermediate steps""",
    },
    "file_reference_format": {
        "source": "MiniMax M2.5",
        "description": "Use file references during execution",
        "pattern": """FILE REFERENCES:
During task: use file_reference tags `file/path.ext`
When complete: use deliver_assets block
Always use complete paths from tool responses""",
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# PERSONALITY MODES
# ═══════════════════════════════════════════════════════════════════════════════

PERSONALITIES = {
    "pragmatic": {
        "source": "GPT-5.5 Codex",
        "description": "Direct, factual, efficiency-first",
        "values": {
            "clarity": "Communicate reasoning explicitly and concretely",
            "pragmatism": "Keep end goal in mind, focus on what works",
            "rigor": "Surface gaps politely, expect coherent arguments",
        },
        "interaction": {
            "tone": "respectful, focused, minimal",
            "avoid": ["cheerleading", "motivation", "reassurance", "fluff"],
            "escalation": "Challenge technical bar without patronizing",
        },
        "output": {
            "max_length": "50-70 lines for simple tasks",
            "format": "plain prose, GitHub-flavored markdown",
            "structure": "findings first, summary last, no 'if you want' endings",
        },
    },
    "friendly": {
        "source": "Claude Opus 4.7",
        "description": "Warm, collaborative, explanatory",
        "values": {
            "warmth": "Treat users with kindness and empathy",
            "collaboration": "Work WITH user, not just FOR user",
            "constructive": "Push back with user's best interests in mind",
        },
        "interaction": {
            "tone": "warm, friendly, age-appropriate",
            "avoid": ["condescending", "assuming", "negative"],
            "emojis": "judicious use only if asked or user's prior message has emoji",
        },
        "output": {
            "max_length": "proportional to complexity",
            "format": "natural prose, examples and metaphors",
            "structure": "explain reasoning, offer alternatives",
        },
    },
    "architect": {
        "source": "Combined",
        "description": "Senior engineer with strong architectural focus",
        "values": {
            "senior_judgment": "Read codebase first, let system teach you",
            "patterns_preference": "Existing patterns over new abstractions",
            "scope_discipline": "Closely scoped edits, minimal side effects",
        },
        "interaction": {
            "tone": "professional, precise, educational",
            "avoid": ["premature certainty", "over-engineering", "assumptions"],
            "verification": "Always verify, never assume",
        },
        "output": {
            "max_length": "task-appropriate",
            "format": "technical prose with file references",
            "structure": "approach, implementation, verification",
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# AI TEAM CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

AI_TEAM = {
    "deepseek": {
        "provider": "deepseek",
        "url": "https://api.deepseek.com/v1/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "role": "Mimar — Analitik düşünme, sistem tasarımı",
        "personality": "architect",
        "strengths": ["reasoning", "architecture", "code_generation", "planning"],
        "system_prompt_addition": """You are a senior software architect with deep analytical capabilities.
Role: System design, architectural decisions, technical planning.
When analyzing: Consider scalability, maintainability, trade-offs.
Apply: Senior judgment pattern — read context, prefer existing patterns.""",
    },
    "kimi": {
        "provider": "kimi",
        "url": "https://api.moonshot.cn/v1/chat/completions",
        "key_env": "KIMI_API_KEY",
        "default_model": "moonshot-v1-128k",
        "role": "Araştırmacı — Detaylı analiz, uzun bağlam",
        "personality": "friendly",
        "strengths": ["research", "long_context", "creative", "analysis"],
        "system_prompt_addition": """You are a thorough researcher and analyst with exceptional long-context understanding.
Role: Deep analysis, research, detailed examination.
When analyzing: Look for edge cases, hidden implications, alternative perspectives.
Apply: Comprehensive review — security, performance, UX, maintainability.""",
    },
    "minimax": {
        "provider": "minimax",
        "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "default_model": "MiniMax-Text-01",
        "role": "Mühendis — Hızlı üretim, implementasyon",
        "personality": "pragmatic",
        "strengths": ["speed", "implementation", "optimization", "iteration"],
        "system_prompt_addition": """You are a pragmatic software engineer focused on delivering working solutions.
Role: Implementation, coding, rapid iteration.
When implementing: Start with failing test (TDD), keep it minimal, verify.
Apply: Autonomy pattern — stay until task is complete, don't stop at half-fix.""",
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# SKILL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

SKILL_REGISTRY: Dict[str, Dict] = {
    "architect_analysis": {
        "description": "Sistem mimarisi analizi ve tasarım kararları",
        "trigger_keywords": ["mimari", "architecture", "tasarım", "design", "sistem"],
        "source_patterns": ["senior_judgment", "auto_memory", "research_strategy_execution"],
    },
    "engineer_execute": {
        "description": "Kod implementasyonu ve TDD workflow",
        "trigger_keywords": ["implement", "kod", "build", "geliştir", "yaz"],
        "source_patterns": ["autonomy_persistence", "deep_thinking_first", "playwright_testing"],
    },
    "code_review": {
        "description": "Kod inceleme, kalite kontrol",
        "trigger_keywords": ["review", "incele", "kontrol", "quality", "test"],
        "source_patterns": ["validation_finality", "copyright_rules", "citation_system"],
    },
    "team_coordinator": {
        "description": "Multi-AI koordinasyonu ve konsensüs",
        "trigger_keywords": ["koordinasyon", "consensus", "team", "karar", "vote"],
        "source_patterns": ["strategic_delegation", "parallel_tool_calls", "ask_before_work"],
    },
    "frontend_design": {
        "description": "Frontend geliştirme ve UI/UX",
        "trigger_keywords": ["frontend", "ui", "react", "web", "design"],
        "source_patterns": ["frontend_rules", "skill_activation", "artifact_system"],
    },
    "document_creation": {
        "description": "Docx, PDF, PPTX, XLSX oluşturma",
        "trigger_keywords": ["document", "docx", "pdf", "pptx", "xlsx", "excel", "word"],
        "source_patterns": ["skill_md_ecosystem", "document_tools", "computer_links"],
    },
    "memory_management": {
        "description": "Memory consolidation ve conversation search",
        "trigger_keywords": ["remember", "memory", "recall", "previous", "geçmiş"],
        "source_patterns": ["memory_consolidation", "conversation_search", "no_bullet_points_default"],
    },
    "security_audit": {
        "description": "Güvenlik analizi ve OWASP kontrolü",
        "trigger_keywords": ["security", "güvenlik", "audit", "owasp", "vulnerability"],
        "source_patterns": ["escalation_rules", "validation_finality", "git_safety_protocol"],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

WORKFLOWS = {
    "full_stack_feature": {
        "name": "Full-Stack Feature Development",
        "description": "Plan → Design → Implement → Test → Review",
        "steps": [
            {
                "phase": "ANALYZE",
                "agent": "deepseek",
                "pattern": "brainstorm_first",
                "action": "Analyze requirements, clarify ambiguities, propose options",
                "output": "clarified_spec",
            },
            {
                "phase": "DESIGN",
                "agent": "deepseek",
                "pattern": "senior_judgment",
                "action": "Design architecture, API schema, data models",
                "output": "design_document",
            },
            {
                "phase": "IMPLEMENT_BACKEND",
                "agent": "minimax",
                "pattern": "tdd_workflow",
                "action": "Write tests first, then implementation",
                "output": "working_code",
            },
            {
                "phase": "IMPLEMENT_FRONTEND",
                "agent": "minimax",
                "pattern": "frontend_rules",
                "action": "Build UI following design system",
                "output": "integrated_frontend",
            },
            {
                "phase": "REVIEW",
                "agent": "kimi",
                "pattern": "validation_finality",
                "action": "Security, performance, quality review",
                "output": "review_report",
            },
            {
                "phase": "VERIFY",
                "agent": "minimax",
                "pattern": "playwright_testing",
                "action": "E2E testing, verify all paths work",
                "output": "verified_product",
            },
        ],
    },
    "bug_fix": {
        "name": "Bug Fix Workflow",
        "description": "Reproduce → Fix → Test → Verify",
        "steps": [
            {"phase": "REPRODUCE", "agent": "minimax", "pattern": "research_strategy_execution", "action": "Create failing test"},
            {"phase": "DIAGNOSE", "agent": "kimi", "pattern": "senior_judgment", "action": "Root cause analysis"},
            {"phase": "FIX", "agent": "minimax", "pattern": "apply_patch_edits", "action": "Minimal surgical change"},
            {"phase": "VERIFY", "agent": "minimax", "pattern": "validation_finality", "action": "Run tests, confirm fix"},
        ],
    },
    "code_review": {
        "name": "Comprehensive Code Review",
        "description": "Architecture → Security → Performance → Quality",
        "steps": [
            {"phase": "ARCHITECTURE", "agent": "deepseek", "pattern": "senior_judgment", "action": "Code structure analysis"},
            {"phase": "SECURITY", "agent": "kimi", "pattern": "escalation_rules", "action": "OWASP top 10 check"},
            {"phase": "PERFORMANCE", "agent": "kimi", "pattern": "validation_finality", "action": "Complexity and bottleneck analysis"},
            {"phase": "QUALITY", "agent": "minimax", "pattern": "autonomy_persistence", "action": "Clean code, DRY, YAGNI check"},
            {"phase": "REPORT", "agent": "deepseek", "pattern": "no_bullet_points_default", "action": "Consolidated review with fixes"},
        ],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# CORE COORDINATOR CLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConsensusDecision:
    decision: str  # APPROVED | REJECTED | NEEDS_REVIEW | PARTIAL
    votes: Dict[str, bool]
    confidence_avg: float
    reasoning: str
    concerns: List[str]
    suggestions: List[str]
    task_id: str
    timestamp: str

@dataclass
class TaskResult:
    task_id: str
    phase: str
    agent: str
    success: bool
    output: Any
    errors: List[str]
    artifacts: List[Dict]
    duration_ms: float

class SuperAgent:
    """
    SuperAgent v3.0 — Synthesized Titan
    Multi-AI coordination with best practices from Claude Code, Codex, Gemini, Grok, Claude Opus, Cowork, MiniMax
    """

    def __init__(
        self,
        state_dir: Path = Path.home() / ".superagent",
        default_personality: str = "pragmatic",
    ):
        self.state_dir = state_dir
        self.state_dir.mkdir(exist_ok=True, parents=True)
        self.memory_dir = state_dir / "memory"
        self.memory_dir.mkdir(exist_ok=True)
        self.skills_dir = state_dir / "skills"
        self.skills_dir.mkdir(exist_ok=True)

        self.personality = default_personality
        self.active_personality = PERSONALITIES.get(default_personality, PERSONALITIES["pragmatic"])
        self.version = VERSION
        self.synthesized_from = SYNTHESIZED_FROM

        self._ensure_memory_index()

    # ─── Memory System (Claude Code + Claude Opus patterns) ──────────────────

    def _ensure_memory_index(self):
        index = self.state_dir / "memory_index.md"
        if not index.exists():
            index.write_text("# Memory Index\n\n")

    def memory_save(
        self,
        key: str,
        value: str,
        memory_type: str = "general",
        context: str = "",
        permanent: bool = False,
    ) -> Dict:
        """Save to memory with discrete types."""
        type_dir = self.memory_dir / memory_type
        type_dir.mkdir(exist_ok=True, parents=True)

        # Sanitize key for filename
        safe_key = re.sub(r'[^\w\-]', '_', key)[:100]
        file_path = type_dir / f"{safe_key}.md"

        timestamp = datetime.now().isoformat()
        content = f"""---
name: {key}
type: {memory_type}
context: {context}
permanent: {permanent}
saved_at: {timestamp}
---

{value}
"""
        file_path.write_text(content)

        # Update index
        index = self.state_dir / "memory_index.md"
        existing = index.read_text() if index.exists() else ""
        entry = f"- [{key}]({type_dir.name}/{safe_key}.md) — {context[:100]}\n"
        if entry not in existing:
            index.write_text(existing + entry)

        return {
            "success": True,
            "key": key,
            "type": memory_type,
            "path": str(file_path),
            "timestamp": timestamp,
        }

    def memory_get(self, key: str, memory_type: str = None) -> Optional[Dict]:
        """Retrieve memory by key."""
        search_dirs = [self.memory_dir / memory_type] if memory_type else [self.memory_dir]
        for d in search_dirs:
            if not d.exists():
                continue
            for f in d.glob(f"{re.sub(r'[^\w\-]', '_', key)[:100]}*.md"):
                content = f.read_text()
                lines = content.split("\n")
                meta = {}
                in_frontmatter = False
                body_lines = []
                for line in lines:
                    if line.strip() == "---":
                        in_frontmatter = not in_frontmatter
                        continue
                    if in_frontmatter and ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                    elif not in_frontmatter:
                        body_lines.append(line)

                return {
                    "key": meta.get("name", key),
                    "type": meta.get("type", "unknown"),
                    "value": "\n".join(body_lines).strip(),
                    "context": meta.get("context", ""),
                    "permanent": meta.get("permanent", "false") == "true",
                    "saved_at": meta.get("saved_at", ""),
                    "path": str(f),
                }
        return None

    def memory_list(self) -> List[Dict]:
        """List all memories."""
        memories = []
        for md_dir in self.memory_dir.iterdir():
            if md_dir.is_dir():
                for f in md_dir.glob("*.md"):
                    try:
                        content = f.read_text()
                        lines = content.split("\n")
                        meta = {}
                        in_frontmatter = False
                        body_lines = []
                        for line in lines:
                            if line.strip() == "---":
                                in_frontmatter = not in_frontmatter
                                continue
                            if in_frontmatter and ":" in line:
                                k, v = line.split(":", 1)
                                meta[k.strip()] = v.strip()
                            elif not in_frontmatter:
                                body_lines.append(line)

                        memories.append({
                            "key": meta.get("name", f.stem),
                            "type": md_dir.name,
                            "preview": "\n".join(body_lines)[:80].strip(),
                            "context": meta.get("context", ""),
                            "permanent": meta.get("permanent", "false") == "true",
                            "saved_at": meta.get("saved_at", ""),
                        })
                    except Exception:
                        pass
        return memories

    # ─── Multi-AI Consensus (Core Pattern) ──────────────────────────────────

    async def _call_ai(
        self,
        agent_key: str,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
    ) -> str:
        """Call a specific AI agent."""
        cfg = AI_TEAM.get(agent_key)
        if not cfg:
            return f"Unknown agent: {agent_key}"

        api_key = os.getenv(cfg["key_env"])
        if not api_key:
            return f"API key not set: {cfg['key_env']}"

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": cfg["default_model"],
                    "max_tokens": 3000,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                }
                resp = await client.post(cfg["url"], headers=headers, json=payload)
                resp.raise_for_status()
                result = resp.json()
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {type(e).__name__}: {str(e)}"

    def _get_system_prompt(self, agent_key: str, context: str = "") -> str:
        """Build system prompt for agent with personality + patterns."""
        cfg = AI_TEAM.get(agent_key, {})
        personality = PERSONALITIES.get(cfg.get("personality", "pragmatic"), PERSONALITIES["pragmatic"])

        base = f"""You are {cfg.get('role', 'AI Assistant')}.
Version: SuperAgent v3.0 (Synthesized Titan)
Agents in team: deepseek (architect), kimi (researcher), minimax (engineer)

{personality.get('values', {}).get('clarity', cfg.get('system_prompt_addition', ''))}

PERSONALITY: {self.personality.upper()}
- {personality.get('description', '')}
- Tone: {personality.get('interaction', {}).get('tone', 'professional')}
- Avoid: {', '.join(personality.get('interaction', {}).get('avoid', []))}

OUTPUT RULES:
- Max {personality.get('output', {}).get('max_length', '100 lines')}
- Format: {personality.get('output', {}).get('format', 'plain text')}
- Structure: {personality.get('output', {}).get('structure', 'direct')}

CONTEXT: {context or 'No additional context'}

{cfg.get('system_prompt_addition', '')}
"""
        return base

    async def multi_ai_consensus(
        self,
        plan: str,
        context: str = "",
        focus: str = "full",
        require_unanimity: bool = False,
    ) -> ConsensusDecision:
        """
        Run multi-AI consensus — all agents analyze plan in parallel.
        Best of: Claude Code (parallel execution), Codex (senior judgment), Gemini (strategic delegation)
        """
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        timestamp = datetime.now().isoformat()

        # Build analysis prompt from patterns
        analysis_prompt = f"""ANALYZE THIS PLAN:

PLAN: {plan}
CONTEXT: {context or 'None'}
FOCUS: {focus}

Apply these patterns:
1. Senior Judgment: Read context, prefer existing patterns, scope tightly
2. Validation: Verify assumptions before approving
3. Risk Awareness: Identify potential issues early

Respond ONLY with valid JSON (no markdown, no text):
{{"approved": true/false, "confidence": 0-100, "concerns": [], "suggestions": [], "reasoning": ""}}
"""
        # Parallel analysis from all 3 agents
        tasks = []
        for agent_key in ["deepseek", "kimi", "minimax"]:
            system = self._get_system_prompt(agent_key, context)
            tasks.append(self._call_ai(agent_key, system, analysis_prompt))

        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse results
        votes = {}
        confidences = []
        all_concerns = []
        all_suggestions = []
        reasoning_parts = []

        for i, agent_key in enumerate(["deepseek", "kimi", "minimax"]):
            result = results[i]
            if isinstance(result, Exception):
                votes[agent_key] = None
                continue

            try:
                parsed = json.loads(result)
                votes[agent_key] = parsed.get("approved")
                confidence = parsed.get("confidence", 0)
                if confidence > 0:
                    confidences.append(confidence)
                all_concerns.extend(parsed.get("concerns", []))
                all_suggestions.extend(parsed.get("suggestions", []))
                reasoning_parts.append(f"{agent_key.upper()}: {parsed.get('reasoning', '')}")
            except json.JSONDecodeError:
                votes[agent_key] = None

        # Determine decision
        approve_count = sum(1 for v in votes.values() if v is True)
        reject_count = sum(1 for v in votes.values() if v is False)
        abstain = sum(1 for v in votes.values() if v is None)

        if require_unanimity:
            if approve_count == 3:
                decision = "APPROVED"
                reasoning = "Unanimous approval (3/3)"
            elif reject_count >= 1:
                decision = "REJECTED"
                reasoning = f"Rejected by {reject_count} agent(s)"
            else:
                decision = "NEEDS_REVIEW"
                reasoning = f"Split decision: {approve_count} approve, {reject_count} reject, {abstain} abstain"
        else:
            if approve_count >= 2:
                decision = "APPROVED"
                reasoning = f"Majority approval ({approve_count}/3)"
            elif reject_count >= 2:
                decision = "REJECTED"
                reasoning = f"Majority rejection ({reject_count}/3)"
            elif approve_count == 1 and reject_count == 1:
                decision = "PARTIAL"
                reasoning = "Split decision — proceed with caution"
            else:
                decision = "NEEDS_REVIEW"
                reasoning = f"TBD: {approve_count} approve, {reject_count} reject, {abstain} abstain"

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        decision_obj = ConsensusDecision(
            decision=decision,
            votes={k: str(v) for k, v in votes.items()},
            confidence_avg=round(avg_confidence, 1),
            reasoning=reasoning,
            concerns=list(set(all_concerns)),
            suggestions=list(set(all_suggestions)),
            task_id=task_id,
            timestamp=timestamp,
        )

        # Save to consensus history
        history_file = self.state_dir / "consensus_history.json"
        history = json.loads(history_file.read_text()) if history_file.exists() else []
        history.append(asdict(decision_obj))
        history = history[-100:]  # Keep last 100
        history_file.write_text(json.dumps(history, indent=2))

        return decision_obj

    # ─── Workflow Execution ─────────────────────────────────────────────────

    async def execute_workflow(
        self,
        workflow_name: str,
        input_data: Dict,
        track_progress: bool = True,
    ) -> List[TaskResult]:
        """
        Execute a predefined workflow across multiple agents.
        Inspired by: Gemini (Research → Strategy → Execution), Cowork (TodoList + verification)
        """
        workflow = WORKFLOWS.get(workflow_name)
        if not workflow:
            return []

        results = []
        for step in workflow["steps"]:
            start = datetime.now()
            phase = step["phase"]
            agent = step["agent"]
            pattern_key = step.get("pattern", "")

            # Get pattern content
            pattern_content = PATTERNS.get(pattern_key, {}).get("pattern", "")

            # Build instruction
            instruction = f"""
PHASE: {phase}
TASK: {step['action']}

INPUT DATA:
{json.dumps(input_data, indent=2, ensure_ascii=False)}

PATTERN GUIDANCE:
{pattern_content[:2000] if pattern_content else 'No specific pattern.'}
"""

            system = self._get_system_prompt(agent, f"Executing workflow: {workflow_name}")
            response = await self._call_ai(agent, system, instruction)

            duration = (datetime.now() - start).total_seconds() * 1000

            # Try to parse output
            try:
                output = json.loads(response)
                success = True
            except json.JSONDecodeError:
                output = response
                success = response.startswith("Error:") is False

            result = TaskResult(
                task_id=f"{workflow_name}_{phase.lower()}",
                phase=phase,
                agent=agent,
                success=success,
                output=output,
                errors=[] if success else [response],
                artifacts=[],
                duration_ms=duration,
            )
            results.append(result)

            # Update input_data with results for next step
            input_data[f"{phase.lower()}_result"] = output

        # Final verification step (Cowork pattern)
        if track_progress:
            verify_result = TaskResult(
                task_id=f"{workflow_name}_verify",
                phase="VERIFY",
                agent="minimax",
                success=all(r.success for r in results),
                output={"all_steps_passed": all(r.success for r in results), "step_count": len(results)},
                errors=[],
                artifacts=[],
                duration_ms=0,
            )
            results.append(verify_result)

        return results

    # ─── Skill Management ────────────────────────────────────────────────────

    def skill_create(self, name: str, content: str, description: str = "", trigger_keywords: List[str] = None) -> Dict:
        """Create a skill in SKILL.md format (Grok + Gemini pattern)."""
        skill_dir = self.skills_dir / name
        skill_dir.mkdir(exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        trigger_kw = trigger_keywords or []
        header = f"""---
name: {name}
description: {description or 'No description'}
trigger_keywords: {json.dumps(trigger_kw)}
created: {datetime.now().isoformat()}
version: {VERSION}
source_patterns: []
---

"""
        skill_file.write_text(header + content)

        return {
            "success": True,
            "skill_path": str(skill_file),
            "name": name,
            "description": description,
        }

    def skill_read(self, name: str) -> Optional[str]:
        """Read a skill's SKILL.md content."""
        skill_file = self.skills_dir / name / "SKILL.md"
        if not skill_file.exists():
            return None
        return skill_file.read_text()

    def skill_list(self) -> List[Dict]:
        """List all skills."""
        skills = []
        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                content = skill_file.read_text()
                desc = ""
                triggers = []
                for line in content.split("\n"):
                    if line.startswith("description:"):
                        desc = line.replace("description:", "").strip()
                    if line.startswith("trigger_keywords:"):
                        try:
                            triggers = json.loads(line.replace("trigger_keywords:", "").strip())
                        except Exception:
                            pass
                skills.append({
                    "name": skill_dir.name,
                    "description": desc,
                    "trigger_keywords": triggers,
                    "path": str(skill_file),
                })
            except Exception:
                pass
        return skills

    # ─── Pattern Access ────────────────────────────────────────────────────

    def get_pattern(self, pattern_name: str) -> Optional[Dict]:
        """Get a pattern by name."""
        return PATTERNS.get(pattern_name)

    def get_all_patterns(self) -> Dict[str, Dict]:
        """Get all patterns organized by source."""
        by_source = {}
        for name, pattern in PATTERNS.items():
            source = pattern.get("source", "Unknown")
            if source not in by_source:
                by_source[source] = []
            by_source[source].append({
                "name": name,
                "description": pattern.get("description", ""),
            })
        return by_source

    # ─── Status & Info ──────────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """Get system status."""
        memory_count = len(self.memory_list())
        skill_count = len(self.skill_list())

        # Check API keys
        providers = {}
        for agent_key, cfg in AI_TEAM.items():
            key_env = cfg["key_env"]
            configured = bool(os.getenv(key_env)) if key_env else True
            providers[agent_key] = {
                "role": cfg["role"],
                "model": cfg["default_model"],
                "personality": cfg["personality"],
                "configured": configured,
                "key_env": key_env or "local",
            }

        return {
            "version": VERSION,
            "build_date": BUILD_DATE,
            "synthesized_from": SYNTHESIZED_FROM,
            "active_personality": self.personality,
            "memory_entries": memory_count,
            "skills_count": skill_count,
            "available_patterns": len(PATTERNS),
            "workflows": list(WORKFLOWS.keys()),
            "providers": providers,
            "patterns_by_source": self.get_all_patterns(),
        }

    def set_personality(self, personality_name: str) -> Dict:
        """Change active personality mode."""
        if personality_name not in PERSONALITIES:
            return {"error": f"Unknown personality: {personality_name}. Available: {list(PERSONALITIES.keys())}"}
        self.personality = personality_name
        self.active_personality = PERSONALITIES[personality_name]
        return {
            "success": True,
            "personality": personality_name,
            "description": self.active_personality["description"],
            "values": self.active_personality["values"],
        }

    # ─── Conversation History ───────────────────────────────────────────────

    def save_conversation(self, conversation_id: str, messages: List[Dict]) -> Dict:
        """Save conversation for later retrieval."""
        conv_dir = self.state_dir / "conversations"
        conv_dir.mkdir(exist_ok=True)
        file_path = conv_dir / f"{conversation_id}.json"
        file_path.write_text(json.dumps({
            "conversation_id": conversation_id,
            "messages": messages,
            "saved_at": datetime.now().isoformat(),
        }, indent=2, default=str))
        return {"success": True, "path": str(file_path)}

    def load_conversation(self, conversation_id: str) -> Optional[List[Dict]]:
        """Load conversation history."""
        file_path = self.state_dir / "conversations" / f"{conversation_id}.json"
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text())
            return data.get("messages", [])
        except Exception:
            return None

    # ─── Export System Prompt ────────────────────────────────────────────────

    def export_system_prompt(self, for_agent: str = "all") -> Dict:
        """Export the system prompt for a specific agent or all."""
        if for_agent == "all":
            return {
                "version": VERSION,
                "synthesized_from": SYNTHESIZED_FROM,
                "personalities": PERSONALITIES,
                "patterns": {k: v["pattern"][:500] for k, v in PATTERNS.items()},
                "ai_team": AI_TEAM,
                "workflows": list(WORKFLOWS.keys()),
                "skill_registry": SKILL_REGISTRY,
            }
        else:
            cfg = AI_TEAM.get(for_agent)
            if not cfg:
                return {"error": f"Unknown agent: {for_agent}"}
            return {
                "agent": for_agent,
                "role": cfg["role"],
                "personality": cfg["personality"],
                "system_prompt": self._get_system_prompt(for_agent),
                "patterns": [p for p, v in PATTERNS.items()],
            }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=f"SuperAgent v{VERSION} — Synthesized Titan\nMulti-AI system inspired by Claude Code, GPT-5.5 Codex, Gemini CLI, Grok, Claude Opus, Cowork, MiniMax"
    )
    parser.add_argument("--command", choices=[
        "status", "consensus", "workflow", "memory", "skill",
        "pattern", "personality", "export", "conversation"
    ], default="status")
    parser.add_argument("--plan", type=str, help="Plan for consensus analysis")
    parser.add_argument("--context", type=str, default="", help="Additional context")
    parser.add_argument("--focus", choices=["full", "architecture", "security", "performance"], default="full")
    parser.add_argument("--workflow", type=str, help="Workflow name to execute")
    parser.add_argument("--input", type=str, help="JSON input for workflow")
    parser.add_argument("--memory-key", type=str, help="Memory key")
    parser.add_argument("--memory-value", type=str, help="Memory value")
    parser.add_argument("--memory-type", type=str, default="general", help="Memory type")
    parser.add_argument("--skill-name", type=str, help="Skill name")
    parser.add_argument("--skill-content", type=str, help="Skill content")
    parser.add_argument("--skill-desc", type=str, default="", help="Skill description")
    parser.add_argument("--pattern-name", type=str, help="Pattern name")
    parser.add_argument("--personality-mode", type=str, help="Set personality (pragmatic/friendly/architect)")
    parser.add_argument("--agent", type=str, help="Agent for export (deepseek/kimi/minimax/all)")
    parser.add_argument("--conversation-id", type=str, help="Conversation ID for load/save")
    parser.add_argument("--save", action="store_true", help="Save current conversation")
    parser.add_argument("--require-unanimity", action="store_true", help="Require 3/3 votes for approval")

    args = parser.parse_args()
    agent = SuperAgent()

    if args.command == "status":
        print(json.dumps(agent.get_status(), indent=2, ensure_ascii=False))

    elif args.command == "consensus":
        if not args.plan:
            print("Error: --plan required")
            return
        result = await agent.multi_ai_consensus(
            args.plan, args.context, args.focus, args.require_unanimity
        )
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))

    elif args.command == "workflow":
        if not args.workflow:
            print(f"Available workflows: {', '.join(WORKFLOWS.keys())}")
            return
        input_data = json.loads(args.input) if args.input else {}
        results = await agent.execute_workflow(args.workflow, input_data)
        for r in results:
            print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
            print("---")

    elif args.command == "memory":
        if args.memory_key and args.memory_value:
            result = agent.memory_save(args.memory_key, args.memory_value, args.memory_type)
            print(json.dumps(result, indent=2))
        elif args.memory_key:
            result = agent.memory_get(args.memory_key)
            if result:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"Memory not found: {args.memory_key}")
        else:
            memories = agent.memory_list()
            print(json.dumps({"memories": memories, "total": len(memories)}, indent=2))

    elif args.command == "skill":
        if args.skill_name and args.skill_content:
            result = agent.skill_create(args.skill_name, args.skill_content, args.skill_desc)
            print(json.dumps(result, indent=2))
        elif args.skill_name:
            content = agent.skill_read(args.skill_name)
            if content:
                print(content)
            else:
                print(f"Skill not found: {args.skill_name}")
        else:
            skills = agent.skill_list()
            print(json.dumps({"skills": skills, "total": len(skills)}, indent=2))

    elif args.command == "pattern":
        if args.pattern_name:
            p = agent.get_pattern(args.pattern_name)
            if p:
                print(json.dumps(p, indent=2, ensure_ascii=False))
            else:
                print(f"Pattern not found. Available: {', '.join(PATTERNS.keys())}")
        else:
            by_source = agent.get_all_patterns()
            for source, patterns in by_source.items():
                print(f"\n## {source}")
                for p in patterns:
                    print(f"  - {p['name']}: {p['description']}")

    elif args.command == "personality":
        if args.personality_mode:
            result = agent.set_personality(args.personality_mode)
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({
                "current": agent.personality,
                "available": list(PERSONALITIES.keys()),
            }, indent=2))

    elif args.command == "export":
        result = agent.export_system_prompt(args.agent or "all")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "conversation":
        if args.conversation_id:
            conv = agent.load_conversation(args.conversation_id)
            if conv:
                print(json.dumps({"conversation_id": args.conversation_id, "messages": conv}, indent=2))
            else:
                print(f"Conversation not found: {args.conversation_id}")
        else:
            print("Usage: --command conversation --conversation-id <id>")


if __name__ == "__main__":
    asyncio.run(main())
