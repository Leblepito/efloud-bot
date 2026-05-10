---
name: efloud-uiux-audit
description: Comprehensive UI/UX research and audit for the efloud-bot Next.js dashboard before any redesign work begins. Use when user requests UI/UX analysis, dashboard improvements, or before any frontend feature work.
---

# efloud-uiux-audit

This skill produces a research document — not code changes. The output should
be detailed enough that subsequent UI work can follow it without re-auditing.

## Scope (frontend = `frontend/`, Next.js 15 + React 19 + Tailwind)

Audit these dimensions:

### 1. Information architecture
- Pages / routes inventory (`frontend/app/` or `frontend/pages/`).
- Per-page: primary user goal, key data shown, primary actions.
- Navigation hierarchy: how does a trader move between status → positions → orders → config → reports?

### 2. Real-time data UX
- WebSocket subscriptions (`frontend/lib/ws.*`, `backend/api.py` /ws endpoint).
- How are stale states surfaced? (disconnect indicator, reconnect logic, last-update timestamp)
- Latency budget: what feels acceptable for position PnL refresh?

### 3. Critical user journeys
- "Did the bot just open a position?" — where does a trader confirm in < 5s?
- "Is the bot halted by circuit breaker?" — visibility, color, alert noise.
- "What's my equity curve today / this week?" — chart presence, scale, anomaly highlighting.
- "Is mainnet live or testnet?" — must be UNAMBIGUOUS at all times.

### 4. Visual hierarchy & color
- Profit / loss color contrast — accessible to red-green colorblind users?
- Status pills (LIVE / TESTNET / DRY_RUN / HALTED) — distinct, not just tonal.
- Density: too noisy or too sparse for power users vs. casual checks?

### 5. Mobile / responsive
- Is the dashboard usable on phone for a trader on the go?
- Touch targets ≥ 44px? Charts pinch-zoomable?

### 6. Auth & session
- `EFLOUD_WEB_PASSWORD` flow — UX of login, session expiry, error states.
- Idle timeout vs. trader expectation (long-running watch).

### 7. Performance
- Initial load size (Next.js bundle analyzer if possible).
- WebSocket message rate vs. render cost — any list re-renders on every tick?

### 8. Accessibility (a11y baseline)
- Keyboard navigation reaches all primary actions?
- ARIA labels on status pills, alerts, modals?
- Focus management on route change?

## Method

1. `ls frontend/` and map directory structure.
2. Read `frontend/package.json` for stack confirmation (React/Next versions, UI libs).
3. Read each page component (root + nested layouts).
4. Read shared components (`components/`, `lib/`).
5. Read backend API surface (`backend/api.py`) — what data is available vs. what's actually displayed?
6. Optionally: run `npm run dev` in `frontend/` and capture screenshots of each page (only if user asks; document URLs not screenshots in output).

## Output

Produce a single Markdown document with sections matching the dimensions above,
plus:

```
## Top 10 UX issues (prioritized)
1. [P0|P1|P2] <issue> — file:line — <impact> — <suggested fix>
...

## Recommended next PRs (atomic)
- PR-A: <smallest valuable change>
- PR-B: ...

## Open questions for Hermes/Utku
- ...
```

## Hard rules
- This is **research**, not implementation. No frontend file edits in this skill.
- No new dependencies suggested without justification.
- Mainnet/testnet badge ambiguity = automatic P0.
- Circuit-breaker visibility regression = automatic P0.
