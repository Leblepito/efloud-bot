---
name: efloud-social-publishing
description: "efloud-bot social media publishing pipeline — automated chart/video generation and multi-platform posting (X, Instagram, YouTube) from trade signals. Use when asked to publish trades, generate chart images, create reels/shorts, or wire the content pipeline."
version: 1.0.0
metadata:
  trigger_keywords: [social, publish, chart, video, reels, shorts, Instagram, YouTube, X, Twitter, content, marketing, signal, trade image, post]
  platform_targets: [x, instagram, ig_reels, youtube]
---

# efloud-bot Social Publishing Pipeline

Automatically turns bot trade signals into branded chart images and short-form
videos, packages them per platform (X, Instagram, YouTube), and dispatches
through three safety gates.

## Quick start (one command)

```bash
cd /opt/efloud-bot
python -m scripts.daily_social_run --date "$(date -u +%F)"
```

This runs the FULL chain (Lane B → C → D → G → publish). Default posture is
**safe**: charts and clips are generated, bundles land in `pending_review`,
publish is a dry-run. Nothing leaves the machine.

## Architecture (6 lanes)

```
Lane A (bot)        ContentJobEmitter → JSONL             engine/content_jobs.py
Lane B (analysis)   reads JSONL, produces analysis        scripts/lane_b_consumer.py
Lane C (copy)       compliance-gated captions             scripts/lane_c_copywriter.py
Lane D (visual)     annotated chart PNGs                  scripts/chart_render.py
                        ↓
                   lane_d_visual.py (orchestrator)
Lane G (package)    per-platform bundles + MP4 clips      scripts/lane_g_social.py
Lane G (publish)    approved bundles → Lane E dispatch     scripts/lane_g_publish.py
```

Daily runner that chains everything: `scripts/daily_social_run.py`

## Key modules (what they do)

| Module | Input | Output | Notes |
|---|---|---|---|
| `scripts/chart_render.py` | signal (entry/SL/TP) + OHLCV cache | branded PNG (1080×1350 + 1080×1920) | Offline-first, matplotlib |
| `scripts/video_render.py` | chart PNG | MP4 (H.264+AAC, 7-8s Ken Burns) | ffmpeg default (pixel-exact) |
| `scripts/higgsfield_adapter.py` | chart PNG + MCP token | MP4 (AI-animated) | Opt-in, ⚠️ alters price labels |
| `scripts/lane_g_social.py` | Lane C copy + Lane D PNG | per-platform bundles | X/IG/Reels/YT |
| `scripts/lane_g_publish.py` | approved bundles | Lane E → platform dispatch | 3-gate safety |
| `scripts/lane_c_copywriter.py` | Lane B analysis | compliance-gated caption + levels | Ratio-only, never absolute $ |

## Three safety gates (all default-closed)

1. **Approval gate** — bundles are `pending_review` unless `--auto-approve`
2. **Live gate** — dispatch is dry-run unless `--live`
3. **Platform flags** — each publisher is OFF unless its env var is set:
   `X_API_ENABLED`, `INSTAGRAM_ENABLED`, `YOUTUBE_ENABLED`

All three must be open for a real post to go out.

## Per-platform output

| Platform | Media | Geometry | Clip? | Caption limit |
|---|---|---|---|---|
| X | still PNG | 1080×1350 | no | 280 chars |
| Instagram | still PNG | 1080×1350 | no | 2200 |
| IG Reels | vertical MP4 | 1080×1920 | yes | 2200 |
| YouTube Shorts | vertical MP4 | 1080×1920 | yes | 5000 |

Every caption carries the mandatory disclaimer:
`Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.`

## Video backends

**ffmpeg (default, free, pixel-exact):** Deterministic Ken Burns push-in over
the chart still. The chart is never reinterpreted — published SL/TP prices are
always the real ones. No API key, no credits, no network. Runs on VPS.

**Higgsfield (opt-in, paid, ⚠️ DATA INTEGRITY WARNING):** Generative
image-to-video. MEASURED 2026-07-26: rewrites price labels (TP1 64,800 →
64,400), garbles y-axis ticks, invents candles. Do NOT use for signal charts.
Opt-in via `EFLOUD_VIDEO_BACKEND=higgsfield` + `HIGGSFIELD_MCP_TOKEN`.

## Compliance rules (automatic, defense-in-depth)

Checked at TWO points in the pipeline:
1. **Lane C** — before copy is written
2. **Lane E** — at publish time (re-checks the envelope)

Rules (from `scripts/content_compliance.py`):
- Banned Turkish/English promise phrases
- No absolute $ amounts (PNL, account balance)
- No performance-% claims
- Disclaimer must be present
- Unlabeled simulation must carry `[BACKTEST]`/`[SIM]` tag

## Bug fixes applied (2026-07-26)

1. **Instagram:** `backend/social/instagram_client.py:post_draft()` imported
   `render_promo_card` from `tier2_renderers` — that function does NOT exist in
   that module. Every Instagram publish raised `ImportError`. Fixed: media is
   now resolved from the draft's own `meta['media']` (the chart/clip paths
   already produced by Lane D/Lane G).

2. **YouTube:** `backend/social/youtube_client.py:post_draft()` hardcoded
   `video_path=None`. A Shorts upload could never carry a video. Fixed: media
   is resolved from `draft.meta['media']`.

## Common cron patterns

```bash
# Generate charts + clips + bundles (safe — nothing published):
0 * * * * cd /opt/efloud-bot && python -m scripts.daily_social_run --date "$(date -u +%F)" >> /app/logs/social.log 2>&1

# Auto-approve + live (needs platform env flags set!):
0 12 * * * cd /opt/efloud-bot && python -m scripts.daily_social_run --date "$(date -u +%F)" --auto-approve --live >> /app/logs/social.log 2>&1
```

## Testing

```bash
# All social pipeline tests (229 tests):
python -m pytest tests/test_social_publishing.py tests/test_lane_g_publish.py tests/test_higgsfield_adapter.py --import-mode=importlib -q

# Full project (exclude vendored repos):
python -m pytest --ignore=external_repos --ignore=graphify-out --import-mode=importlib -q
```

## Related project docs

- `HERMES.md` — operator guide (deploy, config, incident response)
- `CLAUDE.md` — project memory, architecture, rules
- `pine/publish/PUBLISH_efloud_signals.md` — Pine Script publish steps
- `docs/schemas/content_job-1.0.0.json` — Lane A event schema
