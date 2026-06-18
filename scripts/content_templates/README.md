# M6 — P-002 X (Twitter) content templates

Compliance-clean X/Twitter post templates for the efloud trading product, plus a
reproducible verifier. The M6 **second half** (Hermes `tier2_renderers`) renders these
into the existing approval queue → Lane E publishing spine.

| File | Purpose |
|---|---|
| `templates.yaml` | **Machine-readable source. The renderer consumes this.** |
| `verify_compliance.py` | Runs the REAL repo gate on every filled example — reproducible proof. |
| `templates.md` | Human-readable view: filled examples + per-template gate result. |
| `README.md` | This file — placeholder dictionary, Hermes consume contract, RU/KZ TODO. |

## Re-verify (anytime)

```bash
# repo root is auto-derived from the script location; run from anywhere:
python scripts/content_templates/verify_compliance.py
# override the repo root if needed:
EFLOUD_REPO=/opt/efloud-bot python scripts/content_templates/verify_compliance.py
```

Expected tail: `checked=12  clean=12  failed=0` + `RESULT: ALL TEMPLATES PASS`.
The negative-control block must show 4×`PASS` — that proves the gate is live, so a
`[]` result on our templates is meaningful (not an inert checker).

## Placeholder dictionary

| Placeholder | Meaning | Example | Compliance note |
|---|---|---|---|
| `{symbol}` | Pair ticker | `BTCUSDT`, `ETHUSDT` | safe; no digit immediately before USDT |
| `{tf}` | Timeframe | `15m`, `1h`, `4h` | — |
| `{direction}` | Trade side | `LONG`, `SHORT` | — |
| `{bias}` | Directional lean (commentary) | `neutral → long above mid` | — |
| `{structure}` | SMC structure desc | `bullish OB + FVG retest` | free text; avoid % near perf words |
| `{entry}` `{sl}` `{tp1}` `{tp2}` | Price levels | `64200` | **BARE number — never add $/₺/USDT/USD/TL** |
| `{rr}` | Risk:reward ratio | `1:2.6` | use ratio, never absolute $ |
| `{risk_pct}` | Per-trade risk % | `1.1` | risk-% is allowed (`risk`≠perf word) |
| `{invalidation_note}` | Invalidation condition | `1h close above breaker` | — |
| `{chart_img}` | M2 chart-export image | (media path/URL) | **attached as media, NOT inlined in caption text** |
| `{concept}` | Educational topic | `Order Block (OB)` | — |
| `{one_line_definition}` `{how_to_spot}` `{how_to_use}` | Educational body | free text | keep % away from perf words |
| `{week}` | ISO week / range | `2026-W24` | — |
| `{n_ideas}` `{n_reached}` | Recap counts | `7`, `4/7` | counts, **not %** |
| `{avg_r}` | Avg R-multiple | `+1.8` | **R, never $; no % near it** |
| `{feature}` | Promo feature line | `New: 15m+1h chart exports` | no income/guarantee claims |
| `{cta_url}` | Waitlist link | `https://u2algo.com/waitlist` | free waitlist; X shortens to ~23 chars |
| `{date}` | Post date | `2026-06-18` | — |
| `{levels}` `{watch_note}` | Commentary context | free text | — |

## Compliance rules baked into every template

The real gate (`scripts/content_compliance.py → find_violations`) enforces 4 checks
(it also scans a `BANNED_EN_PHRASES` list now — EN parity, CMP-3):

1. **`banned_phrase`** — verbatim promise phrases (case/comma-insensitive). TR (6):
   `Kesin kazanç`, `Garantili getiri`, `Her gün kâr`, `Pasif gelir makinesi`,
   `Sinyal al, kazan`, `Fonumuza para yatır`. EN (CMP-3): `guaranteed profit/returns/win`,
   `risk-free`, `no loss`, `can't lose`, `double your money`, `passive income machine`,
   `get rich`, `get-rich-quick`, `signal and earn`. We never use them.
   *Note:* `garanti değildir` / `garanti yok` are SAFE — only the exact phrase
   `Garantili getiri` is banned, so "no guarantees" copy is fine.
2. **`absolute_money`** — `$`/`₺` next to a number, or a number tagged
   `USD|USDT|dolar|TL` — except the single whitelisted `$39` product price. → We use
   **bare price numbers** and express outcomes as **R-multiples + risk-%**, never money.
3. **`performance_pct_claim`** — a `%` token within 30 chars of a perf word
   (`kazanç|kazan|getiri|kâr|kar|win rate|isabet|başarı|return|profit`). → We keep
   every `%` next to `risk` only (allowed), and recap win-stats are **counts**
   (`4/7`), never `% win rate`.
4. **`unlabeled_simulation`** (CMP-3) — any sim-word
   (`backtest|simulated|simülasyon|simulasyon|shadow|testnet|replay|hypothetical`)
   REQUIRES a bracket label token `[BACKTEST]`/`[TESTNET]`/`[SIMULATED]`/`[SIM]`/`[REPLAY]`
   in the same post. → The `performance_recap` template carries **`[SIMULATED]`** in its
   header; the human-readable "Simulated/backtest results" footer stays for readers.

Plan-intent guardrails honored but **not** gate-enforced: disclaimer present on every
template (exact `engine.content_jobs` strings), no income/guarantee promise in promo
copy (EN side too).

## How Hermes wires this into the approval queue (M6 second half)

The repo already has the publishing spine; templates plug in as the **caption source**
ahead of the existing Phase 5 DraftStore → Phase 4b Lane E flow:

1. **Render** — load `scripts/content_templates/templates.yaml`, pick
   `template.langs[lang]`, `str.format(**values)`. For `format: thread`, render each
   `tweets[]` entry; tweet 1 carries `{chart_img}` media.
2. **Pre-gate** — run `scripts.content_compliance.find_violations(text)` on the rendered
   text *before* enqueueing. If non-empty → quarantine, don't enqueue (same pattern as
   `LaneCCopywriter.run` in `scripts/lane_c_copywriter.py`).
3. **Enqueue draft** — build a draft dict `{draft_id, state:"pending_review", payload:{
   caption, media:[chart_img], thread:[...]}, template_id, lang}` into the DraftStore
   FSM (`pending_review → approved/rejected`). Operator approves in queue.
4. **Publish** — `LaneEPublisher.publish_draft(draft)` (`scripts/lane_e/publisher.py`,
   only `state=="approved"`): re-runs `find_violations` (defense in depth), appends
   `COMPLIANCE_TR` if absent, dispatches to enabled publishers. Add an **X publisher**
   under `scripts/lane_e/publishers/` that calls `xurl` (T-026) — keep it flag-gated
   `enabled=False` by default, like the existing default-OFF publishers in prod.
5. **Idempotency** — Lane E already dedupes on `(draft_id, platform)`; threads post as a
   reply chain under one logical draft.

**Contract for Hermes:** templates are the input to step 1; the gate at step 2 is the
same `find_violations` already imported by Lane C/E. No new compliance code needed —
templates were authored against the live gate.

## RU / KZ addition (what's required)

RU/KZ are skeleton stubs (`body: "TODO"` / `tweets: ["TODO"]`) in `templates.yaml`.
The verifier reports them as `(stub) TODO` and skips them — they are not falsely
reported as passing. To activate, in priority order:

1. **Disclaimer strings** — add RU + KZ `COMPLIANCE_RU` / `COMPLIANCE_KZ` to
   `engine/content_jobs.py` (today only TR + EN exist). Mirror exact-match usage.
2. **Banned-phrase list per language** — the gate's `BANNED_TR_PHRASES` is TR-only.
   Add RU/KZ promise-phrase equivalents to `scripts/content_compliance.py`
   (e.g. `BANNED_RU_PHRASES`, `BANNED_KZ_PHRASES`) and fold into `find_violations`.
   *Until then the gate cannot catch RU/KZ promise language — do not publish RU/KZ.*
3. **Perf-word regex** — `_PERF_WORDS` is TR+EN only; extend with RU/KZ profit/return
   words (e.g. RU `прибыль|доход|выигрыш`) so `performance_pct_claim` works.
4. **Money regex** — `_MONEY` covers `$ ₺ USD USDT dolar TL`; add `₽`/`RUB`/`₸`/`KZT`
   if RU/KZ copy ever shows local currency (our templates use bare numbers, so low risk).
5. **Native-speaker review** — translate each `body`/`tweets`, then re-run
   `verify_compliance.py` (it auto-includes RU/KZ once the stubs have real text) and
   confirm 0 violations + ≤280 per tweet.
