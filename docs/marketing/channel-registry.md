# SD-1 — Channel-Handle Registry + Brand Audit

| Field | Value |
|---|---|
| Task | SD-1 (SEO-3 `sameAs` depends on this; SD-2 derivatives reference) |
| Owner | @claude (rename = @operator-gated) |
| Status | v1 2026-06-17 |
| Spec | §4.3 SD-1 |

## 1. Current handles (VERIFIED in `u2algo-site/index.html` — INCONSISTENT)

| Channel | Current handle | Source | Verdict |
|---|---|---|---|
| X / Twitter | **@Ualgobot** | `index.html:17,588,690` (twitter:site, footer) | off-target (not "u2algo") |
| Instagram | **u2algo** | `index.html:589,692` | ✅ on-brand |
| Telegram | **@Ualgo_bot** | `index.html:590,691` | off-target |
| YouTube | **@Leblepito** | `index.html:592,693` | ❌ totally off-brand (old name) |
| Email | hello@u2algo.com | all pages | ✅ consistent |

**Problem:** four channels, three different identities, none consistently "u2algo." For a zero-follower brand in a brand-search-driven niche this fragments authority and breaks `sameAs` trust signals.

## 2. Target (operator-gated rename)

Consolidate to a single consistent handle. Preferred: **`u2algo`** (or `u2algo_bot` where `u2algo` is taken) on every channel.

| Channel | Target | Action | Gate |
|---|---|---|---|
| X | `@u2algo` (fallback `@u2algo_bot`) | rename or claim | @operator: check availability + rename |
| Instagram | `u2algo` | keep | — |
| Telegram | `@u2algo` (fallback `@u2algobot`) | rename channel | @operator |
| YouTube | `@u2algo` | rename `@Leblepito` → u2algo | @operator (YT allows 1 handle change / 14 days) |

**Until rename is done:** the live site keeps the working links, but **no copy/schema claims an unclaimed handle.** SEO-3 `sameAs` uses ONLY the handles that resolve today (see §3). After rename, SD-1 v2 + SEO-3 update.

## 3. `sameAs` list for SEO-3 (use ONLY confirmed-live URLs)
```
https://x.com/Ualgobot            (until renamed → https://x.com/u2algo)
https://instagram.com/u2algo
https://t.me/Ualgo_bot            (until renamed → https://t.me/u2algo)
https://youtube.com/@Leblepito    (until renamed → https://youtube.com/@u2algo)
```
SEO-3 must read the FINAL post-rename values if the operator renames before SEO-3 lands; otherwise the current values. SD-1 is the single source for this list — SEO-3 does not hardcode.

## 4. Brand-leak scrub (feeds SD-2)
`launch-assets/2026-05-31-first-share/captions.md` and any asset referencing **`efloud` / `efloud-bot` / `Leblepito`** as a public name must be scrubbed before reuse (internal engine name never goes public — INV). SD-2 audits this before mapping any TR-derivative.

## Acceptance (SD-1)
- [x] Current handles audited from live source with line refs.
- [x] Target consolidation + per-channel operator action + availability gate.
- [x] `sameAs` list (confirmed-live only; no unclaimed-handle claims).
- [x] efloud/Leblepito leak scrub flagged for SD-2.
