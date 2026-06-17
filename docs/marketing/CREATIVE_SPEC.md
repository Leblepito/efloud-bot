# CON-1 — Creative Brand + Compliance Spec (single source of truth)

| Field | Value |
|---|---|
| Task | CON-1 (gates CON-2..CON-7, CON-9; Design/Brand review lens) |
| Owner | @claude |
| Status | v1 2026-06-17 |
| Spec | §4.2 CON-1 |
| Source | `u2algo-site/brand-kit/BRAND.md`, logo SVGs, live index/premium.html |

## 1. Background token (RESOLVED — Design HIGH)
BRAND.md canonical `--u2-bg-base: #050510` (near-black, blue-tinted) and **both logo SVGs are drawn on `#050510`**. Live `index.html`/`premium.html` override `--bg` to pure `#000000` — a drift.

**Decision: canonical background = `#050510`.** Higgsfield renders + all new creative use `#050510` so they match the logo and brand kit. **Live reconcile:** a small CSS fix to align live `--bg` `#000000 → #050510` is filed as a WEB/site nit (so the page a viewer lands on matches the hero they saw). Until that lands, CON briefs note the 5px delta as known.

## 2. Gradients — two systems, non-overlapping roles
| Gradient | Hex | Role — USE ONLY FOR |
|---|---|---|
| **Logo gradient** | `#0EA5E9 → #6366F1 → #7C3AED` (135°) | the u²Algo logo mark/wordmark ONLY. Never recolor the logo with the accent triple. |
| **Accent / UI** | cyan `#00f0ff` → blue `#0080ff` → purple `#a855f7` | CTAs, text gradient, motion graphics, on-screen highlights, chart annotations in video. |

Higgsfield motion/brand frames use the **accent** system for graphics; when the actual logo appears in-frame it keeps its **logo** gradient. The two never get swapped.

## 3. Color + type tokens (from BRAND.md)
- Core accent: `--u2-cyan #00f0ff`, `--u2-blue #0080ff`, `--u2-indigo #6366f1`, `--u2-purple #a855f7`.
- CTA gradient `#00f0ff → #0080ff`; text gradient `#00f0ff → #0080ff → #a855f7`.
- Surfaces: card bg `rgba(255,255,255,0.03)` (never solid); borders ALWAYS `rgba(255,255,255,opacity)`, never solid color.
- Text: primary `#f8fafc`, secondary `#94a3b8`, muted `#64748b`.
- Hero glow: 3-layer radial (cyan .10 / indigo .07 / purple .06).

## 4. Wordmark + voice
- Wordmark: **u²Algo** (superscript ²). Pronounced "u-squared algo" (EN) / "u-kare algo" (TR). On-screen always `u²Algo`, never `efloud` / `u2algo bot` / `Leblepito`.
- Tone: technical, honest, builder-to-builder. "Proof, not promise." No hype, no emoji-spam, no profit cosplay.

## 5. Compliance baked into every asset (HARD)
- **Disclaimer card** (CON assets): B1-EN on-screen + spoken — "Not investment advice. Trade at your own risk." (`has_disclaimer(text,'en')==True`; EN-first → `lang='en'`, never `'both'`). See CMP-1.
- **Conservative proof:** zero `$` amounts, zero win-rate/return %, equity SHAPE only (research-log frame). `$39` founding price allowed (PRICE_WHITELIST) but NO PnL `$`.
- **Shipped-feature allowlist** (what the indicator ACTUALLY draws — never fabricate): **Order Block (OB), Fair Value Gap (FVG), Equal Highs/Lows (EQH-EQL), Breaker Block (BB).** 
- **FORBIDDEN on-screen:** drawn "CHoCH" / "BOS" labels (the indicator does NOT draw these — the #221 honesty fix; claiming them is a false feature claim), any `$`-PnL, any fabricated win-rate overlay, any "signal/buy/sell" framing (use "market-structure visualization").
- All chart visuals sourced from **real TradingView captures**, not AI-fabricated charts (CON-9 requires human visual-QC of burned-in pixels — text gate can't see them).

## Acceptance (CON-1)
- [x] bg token resolved (#050510 canonical + live reconcile note).
- [x] both gradients named with non-overlapping roles.
- [x] color/type tokens + disclaimer card + EN-first rule.
- [x] shipped-feature allowlist + forbid CHoCH/BOS-drawn + no-$ + real-capture rule.
- [x] u²Algo wordmark + pronunciation + no internal-name leak.
