# u2algo brand voice — social and site copy

This profile is derived from the copy u2algo already ships: the site (`u2algo-site/*.html`), the
generated trade posts (`scripts/lane_c_copywriter.py` → `scripts/lane_g_social.py`, samples in
`collab/outputs/abacus/T-20261106-02/`), and the compliance rules (`scripts/content_compliance.py`).
Use it for every caption, thread, Reel script or landing-page edit, whichever model writes it.
The hard rules (§3) are enforced by code; the rest is guidance.

## 1. Voice

| Trait | What it means here | Evidence in the shipped copy |
|---|---|---|
| **Decision support, not signals-for-sale** | We show structure and risk; the reader decides. | Site: "decision-support indicator"; every post ends with the disclaimer |
| **Structure first** | Lead with the setup: symbol · TF · direction, then *why* (CHoCH, OB, FVG, liquidity). | `SOL/USDT · 15m · LONG` / `yapı: CHoCH + OB` |
| **Risk is always visible** | Risk %, R:R and the invalidation level belong in the post, not in a footnote. | `Risk ~1.8% · R:R 1:1.8 (TP1) · Geçersizleşme: …` |
| **Plain and terse** | Short lines, no hype words, no exclamation marks, no emojis in trade facts. | X caption = 4 lines |
| **Honest about evidence** | Simulations and demos are labelled; no backtest number without its cost assumptions. | `live.html` "İLLÜSTRATİF SİMÜLASYON" banner; ADR-0005 |

Language: TR for the community channel and IG; EN for the site and X when the audience is
international. One language per post, so don't mix within a sentence. Domain terms follow
[`CONTEXT.md`](../../CONTEXT.md) (for example "SMC v2", never "Bot V2", when you mean the engine).

## 2. Platform adaptation (one source, native per platform)

| Platform | Shape | Notes |
|---|---|---|
| X (280) | Caption only: setup line, one *why* line, risk line, disclaimer, then the coin tag + 3 tags | The coin hashtag follows the post's symbol (`#SOL`, not a fixed `#BTC`) |
| Instagram (2200) | Caption + bullet breakdown (structure, zones, risk, invalidation) + disclaimer + 5 tags | 1080×1350 still from the real chart |
| IG Reels / YouTube Shorts | Vertical clip; voice-over explains *why entry here, why SL/TP there* | Skill `producing-trade-explainer-reels` |
| Site / OG card | One idea per page; titles ≤ 65 chars, descriptions ≤ 160 | `u2algo-site/scripts/test_seo_meta.js` |

Never post the same text to two platforms. Adapt the length and shape; keep the facts identical.

## 3. Hard rules (enforced, not optional)

- **Disclaimer on every post:** `COMPLIANCE_TR` / `COMPLIANCE_EN` (`engine/content_jobs.py`). Captions
  are trimmed so the disclaimer survives.
- **Banned promise phrases, no absolute-$ PnL, no win-rate or return %:** `scripts/content_compliance.py`
  (`find_violations`). A hit blocks the bundle (`blocked_compliance`).
- **Operator approval is bound to the exact content:** `approve_bundle` records `approved_digest`
  (sha256 of caption, thread, alt text and media bytes). `scripts/lane_g_publish.py` refuses a bundle
  edited after approval (`approval_stale`). Re-approve after any edit.
- **Publishing is default-closed:** per-platform env flags off, `--dry-run` default, `--live` explicit.

## 4. Words

Prefer: *setup, structure, confluence, invalidation, risk, R:R, zone, decision support*.
Avoid: *guaranteed, sure, signal service, passive income, "%X win rate", "$X profit"*. The
compliance lists in `scripts/content_compliance.py` are the source of truth; this list only
summarises them.
