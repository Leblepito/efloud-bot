# PROD-0 — Premium Product Definition / Funnel Terminus

| Field | Value |
|---|---|
| Task | PROD-0 (gates SEO-3, CON-4, all CTA copy) |
| Owner | @claude (decision recorded with @operator) |
| Status | DECIDED 2026-06-17 |
| Spec | §2.1b, §4.0 |

## Decision (operator, 2026-06-17)

**Funnel terminus = "free indicator + waitlist for a future premium tier."** There is no differentiated `$39` premium product today, so nothing markets one until PROD-0 is revisited with a real definition.

### Why (ground truth)
- The repo has exactly **one** Pine script, `pine/u2algo/wave1_signals.pine` — the **free** published indicator (the funnel entry asset). There is no second, differentiated premium artifact.
- The Wave-2 premium strategy was **DROPPED** (OOS walk-forward falsification failed; indicator-only ship is the final product). So there is no premium *strategy* to sell.
- The only live track record (`u2algo-site/premium_proof.json`) is **negative** (-5.3% / 24.1% win / 9 days), explicitly noted as "not the indicator." Selling a "premium product" on this footing is dishonest and converts ~0.

## What this means (binding for every copy/schema/CTA task)

| Surface | Rule |
|---|---|
| **CTAs** | "Get the free indicator" / "Join the waitlist." NEVER "Buy premium" / "Buy now" as the primary action. |
| **SEO-3 schema** | `SoftwareApplication` JSON-LD describes the **free** indicator. Do **NOT** publish an `offers` block with `$39 price` as a sellable premium product until a differentiated premium exists. |
| **Live `$39` Lemon Squeezy checkout** | Reposition as **"Founding / Early-access supporter"**: supports development, locks a lifetime price for the *future* premium tier, and grants early access. It is a supporter pledge, NOT a "premium product that outperforms." premium.html / quickstart.html copy reframed accordingly (CMP-5 wires it). |
| **Ad copy / social** | "Free SMC indicator + research log + waitlist." No premium-product claims. |
| **Proof** | Per the `research-log` decision (§2.1b): metrics shown honestly framed; zero dollar/positive claims pre-90-day. |

The `$39` token itself stays whitelisted in `content_compliance.py` (CMP-3 PRICE_WHITELIST) so the Founding/early-access price can appear, while `$`-PnL stays blocked.

## When PROD-0 is revisited (future premium definition criteria)

A real premium tier may be defined later. It must be **genuinely differentiated** from the free indicator AND backed by a credible track record. Candidate differentiators (pick a coherent subset, then spec separately):
- Real-time **alerts** (the free script is visual-only).
- **Multi-timeframe** confluence view / HTF bias overlay.
- **Confluence score** + ranked setups (the engine's scoring, not in the free script).
- **Invite-only** community + priority support.
- Backtest/parameter presets per market.

**Gate:** no premium is *marketed as outperforming* until the 90-day proof gate (GROW-8) reports a credible positive record. Until then, premium = "early access to what's coming," not "a better signal."

## Acceptance (PROD-0)
- [x] This doc states the funnel terminus = free + waitlist (DECIDED).
- [x] `$39` repositioned as Founding/early-access, not "premium product."
- [x] SEO-3 instructed: no `$39` `offers` product markup; schema = free indicator.
- [x] Future-premium criteria + 90-day gate recorded.

*Downstream: SEO-3, CON-4, CON-7, SD-2/3/4, CMP-5, GROW-1/8 consume this. The reframe is the unblock — these tasks proceed with "free + waitlist" framing.*
