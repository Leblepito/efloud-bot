# Unified Social Learning + Hedge Mode Integration Note

Date: 2026-05-28
Source reviewed: `C:\Users\utkuc\Downloads\research_notes.md`
Status: Integrated as research-only backend slice; no live config or production deployment files changed.

---

## Evaluation summary

The report is directionally correct and useful. It connects two important parts of the system:

1. Social Learning Loop
   - Public Telegram/X content is ingested through `backend/social/feeds.py`.
   - SMC/MPA language is parsed deterministically through `backend/social/doctrine.py`.
   - This is the right architecture because the parser is local, reproducible, cheap, and testable.

2. Hedge Mode / Fail-Fast Execution Layer
   - Recent core engine changes align Binance position mode at startup and avoid the Binance `reduceOnly` + `positionSide` incompatibility in hedge mode.
   - This belongs to the production execution layer, separate from social research.

The report’s most important recommendation is correct: keep social learning as a research pipeline that produces archived doctrine, hypotheses, candidate configs, and backtest reports; never let social/LLM outputs drive live orders directly.

---

## Corrections / caveats

- The diagram’s promotion edge should not imply direct promotion into `config.phase2_1k.yaml` or live config. Candidate outputs must remain under research/candidate paths until explicit human approval.
- Social posts are public analysis and educational material; they should be treated as hypothesis seeds, not ground truth labels.
- The hedge-mode execution layer and social-learning layer should stay decoupled. Their integration point is only the verified promotion gate after backtest + shadow.
- Frontend display must include a clear `Research only — live config unchanged` warning.

---

## Integrated backend slice

Implemented Phase A from the report:

- `backend/social/archive.py`
  - JSONL archive for parsed doctrine snapshots.
  - Dedup key: `source:id:sha256(content)`.
  - Atomic append via temp file + `os.replace`.

- `backend/social/hypotheses.py`
  - Converts doctrine tags into research-only hypotheses.
  - Produces candidate config patches as metadata only.
  - Current hypotheses:
    - `social_ote_fvg_htf_bias_v1`
    - `social_liquidity_sweep_filter_v1`
    - `social_tp1_be_lifecycle_audit_v1`

- `backend/social/reports.py`
  - Builds a read-only dashboard/API snapshot from the archive.

- `backend/api.py`
  - Added auth-protected read-only endpoints:
    - `GET /api/social/doctrine`
    - `GET /api/social/hypotheses`
    - `GET /api/social/research-snapshot`

---

## Verification

Command run:

```bash
pytest backend/tests/test_social_feeds.py backend/tests/test_social_doctrine.py backend/tests/test_social_archive.py backend/tests/test_social_hypotheses.py backend/tests/test_social_reports.py backend/tests/test_api_smoke.py backend/tests/test_reverse_guard.py -q
```

Result:

```text
43 passed in 1.95s
```

---

## Next integration slice

1. Add a small collection job/script:
   - Fetch `/api/social/feeds` logic directly via `fetch_social_feeds()`.
   - Run `extract_doctrine()` for each item.
   - Append to `state/social_doctrine.jsonl` through `append_doctrine_snapshot()`.

2. Add research runner:
   - `scripts/research_social_strategy.py`
   - Reads archive, generates hypotheses, writes candidate YAML under `configs/candidates/`, runs/links `backtest.cli compare`.

3. Add frontend Learning Center:
   - `frontend/components/SocialLearningCenter.tsx`
   - Reads `/api/social/research-snapshot`.
   - Shows raw doctrine tags, hypothesis cards, latest backtest gates, and research-only warning.

4. Promotion runbook:
   - No live promotion unless: tests green, 180d compare has no hard reject, 7d shadow observation, human approval.
