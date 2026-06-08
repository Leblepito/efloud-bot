# PR #4 — InteractiveChart token adoption Implementation Plan

> **For agentic workers:** repo-local execution (superpowers execution skills not installed here). Steps use checkbox (`- [ ]`) syntax. START ritual = `writing-plans` (this doc); END ritual = `/review` (efloud-code-reviewer) + tests (`tsc --noEmit`, `vitest`, `next build`).

**Goal:** Complete the dashboard's `@efloud/tokens` adoption by sourcing `InteractiveChart.tsx`'s chart-chrome + order-line solid hex from a new `terminal.chrome` token group — a strictly NO-VISUAL-CHANGE refactor (byte-identical / CSS-equivalent values only).

**Architecture:** Extend `@efloud/tokens` `terminal` with a `chrome` sub-group (lightweight-charts canvas palette: bg/text/grid/crosshair/label + indigo order-line). Swap the inline JS hex in `InteractiveChart.tsx` for those token refs; back the one `className="bg-[#09090b]"` with a Tailwind `chrome.bg` color sourced from the same token. Leave rgba alpha washes + generic `#ffffff` inline (consistent with PR #2's smcOverlay handling). Candle bull/bear already map to existing `terminal.chart.bull/bear`.

**Tech Stack:** TS, `@efloud/tokens`, lightweight-charts, Tailwind v3, Next 15 static export.

**globals.css decision (deferred-from-#2 item):** `globals.css` stays as the canonical CSS-layer base theme (body/scrollbar/focus/`.row-selected`). CSS cannot `import` TS tokens; the only true single-source fix is a `tokens → :root CSS-var` codegen step, which is disproportionate to this PR. **Out of scope for #4** — recorded as a future enhancement. We add a comment in `globals.css` noting the values mirror `@efloud/tokens.terminal`. (No value change → no visual change.)

---

## File Structure

- **Modify** `packages/tokens/src/index.ts` — add `chrome` sub-group to the `terminal` export.
- **Modify** `frontend/components/InteractiveChart.tsx` — import `terminal`, swap chart-chrome + order-line solids, replace `className="bg-[#09090b]"` with `bg-chrome-bg`.
- **Modify** `frontend/tailwind.config.ts` — add a `chrome` color group sourced from `terminal.chrome` (enables `bg-chrome-bg`, identical value).
- **Modify** `frontend/app/globals.css` — add a one-line mirror comment only (no value change).

Value map (each swap is byte-identical or CSS-case-equivalent):

| Current literal | New ref | Sites (InteractiveChart.tsx) |
|---|---|---|
| `#09090b` | `terminal.chrome.bg` | `:402` bg; `:998` className → `bg-chrome-bg` |
| `#a1a1aa` | `terminal.chrome.text` | `:403` textColor |
| `#111113` | `terminal.chrome.grid` | `:408,:409` grid |
| `#3f3f46` | `terminal.chrome.crosshair` | `:414,:418` crosshair |
| `#18181b` | `terminal.chrome.label` | `:415,:419,:423,:427` labelBg + scale/time borders |
| `#6366F1` | `terminal.chrome.orderLine` (`#6366f1`) | `:801` order price line (case-equivalent) |
| `#00FF88`/`#FF4D4D` | `terminal.chart.bull`/`.bear` (exist) | `:437-442` candle, `:868,:881` markers |
| `#ffffff`, all `rgba(...)` | **left inline** (generic white + alpha washes) | `:139,:248,:252` + PositionOverlay/funding washes |

---

## Task 1: Extend @efloud/tokens with terminal.chrome

**Files:**
- Modify: `packages/tokens/src/index.ts` (the `terminal` object, after `chart`)

- [ ] **Step 1: Add the `chrome` sub-group**

In `terminal`, after the `chart: { ... }` block, add:

```ts
    /* lightweight-charts canvas chrome (InteractiveChart) — zinc neutrals */
    chrome: {
      bg: "#09090b",        // canvas background (zinc-950)
      text: "#a1a1aa",      // axis text (zinc-400)
      grid: "#111113",      // grid lines
      crosshair: "#3f3f46", // crosshair (zinc-700)
      label: "#18181b",     // crosshair label bg + price/time scale borders (zinc-900)
      orderLine: "#6366f1", // pending order price line (indigo-500; case-equivalent to #6366F1)
    },
```

- [ ] **Step 2: Typecheck the package**

Run: `npm run typecheck --workspace @efloud/tokens`
Expected: PASS (no output / exit 0).

## Task 2: Back the className arbitrary value with a Tailwind chrome color

**Files:**
- Modify: `frontend/tailwind.config.ts` (colors block, import already has `terminal`)

- [ ] **Step 1: Add a `chrome` color group from the token**

In `theme.extend.colors`, add (alongside `bg`/`border`/`text`/`accent`):

```ts
        chrome: {
          bg: terminal.chrome.bg,
          grid: terminal.chrome.grid,
          crosshair: terminal.chrome.crosshair,
          label: terminal.chrome.label,
        },
```

- [ ] **Step 2: Typecheck frontend**

Run: `npm run typecheck --workspace efloud-frontend`
Expected: PASS.

## Task 3: Swap InteractiveChart solids to tokens

**Files:**
- Modify: `frontend/components/InteractiveChart.tsx`

- [ ] **Step 1: Add the import** (top of file, after the `n` import ~`:11`)

```ts
import { terminal } from "@efloud/tokens";
```

- [ ] **Step 2: Swap the `createChart` chrome block** (`:401-431`)

Replace the literal colors with refs: `background.color` → `terminal.chrome.bg`; `textColor` → `terminal.chrome.text`; both `grid` colors → `terminal.chrome.grid`; both crosshair `color` → `terminal.chrome.crosshair`; both `labelBackgroundColor` + `rightPriceScale.borderColor` + `timeScale.borderColor` → `terminal.chrome.label`.

- [ ] **Step 3: Swap candle series + markers** (`:437-442`, `:868`, `:881`)

`#00FF88` → `terminal.chart.bull`; `#FF4D4D` → `terminal.chart.bear`.

- [ ] **Step 4: Swap the order price line** (`:801`)

`color: "#6366F1"` → `color: terminal.chrome.orderLine`.

- [ ] **Step 5: Swap the className arbitrary value** (`:998`)

`bg-[#09090b]` → `bg-chrome-bg`.

- [ ] **Step 6: Leave inline** — `#ffffff` (`:139,:248,:252`) and all `rgba(...)` washes (PositionOverlay + funding histogram) unchanged; add a short comment at the first PositionOverlay rgba noting the washes are derived alpha variants left inline (consistent with smcOverlay/PR #2).

## Task 4: globals.css mirror comment

**Files:**
- Modify: `frontend/app/globals.css` (top, near `:5 :root`)

- [ ] **Step 1: Add a mirror note (no value change)**

Add a comment above `:root`: `/* Base theme values mirror @efloud/tokens.terminal (CSS layer — TS tokens can't be imported here; a tokens→CSS-var codegen is a future enhancement). */`

## Task 5: Verify zero visual delta (the "test")

- [ ] **Step 1: Typecheck + unit tests**

Run: `npm run typecheck --workspace @efloud/tokens && npm run typecheck --workspace efloud-frontend && npm run test --workspace efloud-frontend`
Expected: all PASS (vitest 3/3).

- [ ] **Step 2: Build (resolves tokens at build, produces export)**

Run: `npm run build --workspace efloud-frontend`
Expected: Compiled + Exporting OK; `frontend/out/index.html` present.

- [ ] **Step 3: Value-identity grep**

Run: confirm `InteractiveChart.tsx` has no remaining solid chrome/candle/order hex (only `#ffffff` + `rgba(`):
`grep -nE "#[0-9A-Fa-f]{3,6}" frontend/components/InteractiveChart.tsx | grep -vE "rgba|#ffffff"` → expected: empty.

- [ ] **Step 4: Commit**

```bash
git add packages/tokens/src/index.ts frontend/components/InteractiveChart.tsx frontend/tailwind.config.ts frontend/app/globals.css
git commit -m "feat(frontend): InteractiveChart adopts @efloud/tokens chrome palette (PR #4)"
```

## END ritual
- `/review` (efloud-code-reviewer) on the staged diff — confirm every swap byte-identical/CSS-equivalent, no risk paths.
- Push; CI green; then `writing-plans` (START) for the following step.

## Self-Review
- **Spec coverage:** InteractiveChart 23 hex → all chrome/candle/order solids tokenized; rgba washes + `#ffffff` explicitly left inline; globals.css decision recorded (mirror comment, codegen deferred). ✅
- **Placeholder scan:** none — every swap has exact value + line. ✅
- **Type consistency:** `terminal.chrome.{bg,text,grid,crosshair,label,orderLine}` defined in Task 1, consumed in Tasks 2-3; Tailwind `chrome.{bg,grid,crosshair,label}` subset used only for `bg-chrome-bg` (Task 3 Step 5). ✅
