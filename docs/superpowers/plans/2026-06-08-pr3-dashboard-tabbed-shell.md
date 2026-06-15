# PR #3 — Dashboard tabbed/anchored shell Implementation Plan

> **For agentic workers:** repo-local execution. Steps use checkbox (`- [ ]`). START ritual = `writing-plans` (this doc); END = `/review` (efloud-code-reviewer) + tests (`tsc`, `vitest`, `next build`) + **a mandatory human visual-review checkpoint via the Railway preview** (this is the first deliberately-visual step — headless build/typecheck proves it compiles, NOT that it looks right).

**Goal:** Break the dashboard's single long scroll (`frontend/app/page.tsx`, ~10 sections) into a 4-tab shell — **Overview / Positions / Research / Config** — keeping every existing component and all cross-component interactions intact.

**Architecture:** `page.tsx` keeps ownership of `selectedSymbol`/`selectedTrade` and gains `activeTab` state. A new presentational `TabNav` renders the tab bar. Panels are **kept mounted** and toggled with a `hidden` class (NOT unmounted) so the live chart's WebSocket and all component state survive tab switches, and the `selectedSymbol`/`selectedTrade` cross-links keep working. Selecting a trade auto-switches to Overview so the chart jump is visible. No router change (stays a single client route).

**Tech Stack:** Next 15 (client component), React 19, Tailwind v3 + `@efloud/tokens` terminal palette, vitest.

---

## Why keep-mounted (the load-bearing decision)

`page.tsx` wires shared state across components that would land on **different** tabs:
- `selectedSymbol`: `InteractiveChart` (Overview) ↔ `PositionsTable`/`OpenOrdersTable` (Positions).
- `selectedTrade`: `TradesTable` (Positions) → `InteractiveChart` (Overview, jumps to the trade's time range) + `TradeDetailPanel` (modal).

If inactive tabs were **unmounted**, switching tabs would tear down the chart's Binance WebSocket + lose HUD/zoom state, and the trade→chart jump would break. So inactive panels are hidden with `className="hidden"` (display:none) — mounted, inert visually, state preserved. `LiveSync` (side-effect only) and `TradeDetailPanel` (modal) stay outside the panels, always mounted. On `selectedTrade` set, auto-switch to Overview so the user sees the chart react.

## Tab → section mapping (every existing section kept)

| Tab | Sections (current page.tsx order preserved within tab) |
|---|---|
| **Overview** | `StatusGrid`; `AISentimentCard` + `SocialFeeds` (2-col grid); `InteractiveChart`; `EquityChart` |
| **Positions** | `PositionsTable`; `OpenOrdersTable`; `TradesTable` |
| **Research** | `SocialLearningCenter`; `MarketIndicators` |
| **Config** | `ConfigPanel` |
| **always-mounted** | `TopBar` (above nav), `LiveSync`, `TradeDetailPanel`, footer |

---

## File Structure

- **Create** `frontend/components/TabNav.tsx` — presentational tab bar (a11y `role="tablist"`, `aria-selected`, keyboard-focusable buttons, token-styled). One responsibility: render tabs + emit `onChange`.
- **Create** `frontend/components/__tests__/TabNav.test.tsx` — unit test (renders 4 tabs, active styling, onChange fires).
- **Modify** `frontend/app/page.tsx` — add `activeTab` state + auto-switch effect; render `TabNav`; wrap section groups in keep-mounted panels. Auth gate (`:25-32`) preserved verbatim.

---

## Task 1: TabNav component (TDD)

**Files:**
- Create: `frontend/components/TabNav.tsx`
- Create: `frontend/components/__tests__/TabNav.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/components/__tests__/TabNav.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { TabNav, type TabKey } from "../TabNav";

describe("TabNav", () => {
  it("renders all four tabs and marks the active one", () => {
    render(<TabNav active="overview" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: /overview/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /positions/i })).toHaveAttribute("aria-selected", "false");
    expect(screen.getAllByRole("tab")).toHaveLength(4);
  });

  it("fires onChange with the tab key when a tab is clicked", () => {
    const onChange = vi.fn();
    render(<TabNav active="overview" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: /config/i }));
    expect(onChange).toHaveBeenCalledWith<[TabKey]>("config");
  });
});
```

- [ ] **Step 2: Run it — verify it fails**

Run: `npm run test --workspace efloud-frontend`
Expected: FAIL (`Cannot find module '../TabNav'`).

- [ ] **Step 3: Implement TabNav**

```tsx
// frontend/components/TabNav.tsx
"use client";

export type TabKey = "overview" | "positions" | "research" | "config";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "positions", label: "Positions" },
  { key: "research", label: "Research" },
  { key: "config", label: "Config" },
];

export function TabNav({ active, onChange }: { active: TabKey; onChange: (k: TabKey) => void }) {
  return (
    <div
      role="tablist"
      aria-label="Dashboard sections"
      className="sticky top-0 z-20 -mx-6 mb-2 flex gap-1 border-b border-border bg-bg/80 px-6 py-2 backdrop-blur"
    >
      {TABS.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(t.key)}
            className={`px-4 py-1.5 text-xs font-mono uppercase tracking-widest rounded-sm transition-colors ${
              isActive
                ? "bg-accent-green/10 text-accent-green font-bold"
                : "text-text-muted hover:text-text-secondary hover:bg-bg-surface"
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run it — verify it passes**

Run: `npm run test --workspace efloud-frontend`
Expected: PASS (existing KronosCard 3 + new 2 = 5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/TabNav.tsx frontend/components/__tests__/TabNav.test.tsx
git commit -m "feat(frontend): TabNav component for dashboard shell (PR #3)"
```

## Task 2: Wire the tabbed shell into page.tsx

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Add imports + state + auto-switch (keep auth gate verbatim)**

Add `import { TabNav, type TabKey } from "@/components/TabNav";`. After the existing `selectedTrade` state add:

```tsx
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  // Selecting a trade (from TradesTable on the Positions tab) jumps the chart on
  // Overview — switch there so the user sees it.
  useEffect(() => {
    if (selectedTrade) setActiveTab("overview");
  }, [selectedTrade]);
```

Leave the existing auth-gate `useEffect` (`:25-32`) byte-for-byte unchanged.

- [ ] **Step 2: Replace the `<main>` body with tab panels (keep-mounted)**

Render `<TabNav active={activeTab} onChange={setActiveTab} />` first inside `<main>`, then wrap each group; inactive panels get `hidden`:

```tsx
      <main className="mx-auto max-w-7xl px-6 py-8">
        <TabNav active={activeTab} onChange={setActiveTab} />

        <div className={activeTab === "overview" ? "space-y-6" : "hidden"}>
          <section><StatusGrid /></section>
          <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <AISentimentCard />
            <SocialFeeds />
          </section>
          <section>
            <InteractiveChart selectedSymbol={selectedSymbol} selectedTrade={selectedTrade} onSelectSymbol={setSelectedSymbol} />
          </section>
          <section><EquityChart /></section>
        </div>

        <div className={activeTab === "positions" ? "space-y-6" : "hidden"}>
          <section><PositionsTable onSelectSymbol={setSelectedSymbol} selectedSymbol={selectedSymbol} /></section>
          <section><OpenOrdersTable onSelectSymbol={setSelectedSymbol} /></section>
          <section><TradesTable onSelectTrade={setSelectedTrade} selectedId={selectedTrade?.id} /></section>
        </div>

        <div className={activeTab === "research" ? "space-y-6" : "hidden"}>
          <section><SocialLearningCenter /></section>
          <section><MarketIndicators /></section>
        </div>

        <div className={activeTab === "config" ? "space-y-6" : "hidden"}>
          <section><ConfigPanel /></section>
        </div>

        <footer className="pt-8 pb-12 text-[10px] tracking-widest font-mono text-text-muted text-center uppercase">
          Efloud SMC Bot v2.2 ▪ Not financial advice ▪ DYOR
        </footer>
      </main>
```

`LiveSync` and `TradeDetailPanel` stay after `</main>`, unchanged (always mounted).

- [ ] **Step 3: Typecheck**

Run: `npm run typecheck --workspace efloud-frontend`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): tabbed dashboard shell over page.tsx (PR #3)"
```

## Task 3: Verify (headless gates + human visual checkpoint)

- [ ] **Step 1: Tests + build**

Run: `npm run typecheck --workspace efloud-frontend && npm run test --workspace efloud-frontend && npm run build --workspace efloud-frontend`
Expected: tsc PASS; vitest 5/5; Compiled + Exporting OK; `frontend/out/index.html` present.

- [ ] **Step 2: Auth-gate guard (regression check)**

Run: `grep -n "efloud_demo_mode\|status === 401\|/login" frontend/app/page.tsx`
Expected: the gate logic is present and unchanged (demo bypass + 401→/login).

- [ ] **Step 3: 🚦 HUMAN VISUAL REVIEW (blocks merge)** — headless tests cannot confirm appearance/UX. Operator reviews on the Railway preview:
  - all four tabs render; each shows its mapped sections; nothing missing vs the old scroll;
  - the live chart keeps its WebSocket + zoom when switching tabs (keep-mounted works);
  - clicking a row in TradesTable (Positions) jumps the chart AND switches to Overview;
  - selecting a symbol in PositionsTable updates the chart;
  - mainnet/testnet badge + circuit-breaker visibility unaffected (TopBar/StatusGrid).

- [ ] **Step 4: Commit (if visual review requested tweaks, fold them first)** — then END ritual: `/review` + push; on green, `writing-plans` (START) for PR #5 (responsive/density).

---

## Self-Review
- **Spec coverage:** all ~10 sections mapped into 4 tabs, none dropped (table above); auth gate preserved verbatim (Task 2 Step 1); keep-mounted design preserves cross-state + WS; nav is a client component, no router change; explicit visual checkpoint (Task 3 Step 3). ✅
- **Placeholder scan:** none — full TabNav code, full panel JSX, exact commands. ✅
- **Type consistency:** `TabKey` defined in TabNav (Task 1), imported + used for `activeTab` (Task 2). `onChange(k: TabKey)` matches `setActiveTab`. ✅
- **Risk:** deliberately-visual — Task 3 Step 3 is a human gate; do not merge on headless-green alone.
