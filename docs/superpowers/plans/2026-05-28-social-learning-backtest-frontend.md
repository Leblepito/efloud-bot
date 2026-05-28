# Social Learning Backtest + Frontend Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Efloud-bot, Efloud Telegram/X paylaşımlarındaki SMC/MPA mantığını yapılandırılmış veri olarak öğrenebilsin; bu içeriği backtest araştırmasına ve dashboard gözlemine bağlayarak canlı bot stratejisini sadece kanıtlanmış, güvenli adaylarla geliştirsin.

**Architecture:** Üç katmanlı güvenli öğrenme döngüsü kurulacak: (1) sosyal içerik toplama + doktrin çıkarımı, (2) doktrin hipotezlerini backtest/compare/grid üstünde ölçme, (3) frontend'de kanıt, metrik ve karar panelleri. Sistem production `config.yaml`, `docker-compose.prod.yml`, `.env` ve canlı emir akışını değiştirmeyecek; sadece candidate config, rapor ve inert strateji modülleri üretecek.

**Tech Stack:** FastAPI backend, Python async/httpx, Pydantic/dataclass modelleri, mevcut `backtest` CLI, Next.js 15 frontend, pytest, TypeScript typecheck.

---

## Safety invariants

1. Canlı trading davranışı bu plan boyunca değişmeyecek.
2. Sosyal içerik veya LLM çıktısı doğrudan emir kararı vermeyecek.
3. Üretilen her strateji değişikliği önce `backtest.cli compare` + gate raporu + shadow gözleminden geçecek.
4. Live `config.yaml` editlenmeyecek; yalnızca `configs/candidate_*.yaml` ve `reports/` çıktıları üretilecek.
5. Sosyal medya verisi eksik/bozuk/API-limit olduğunda bot `NEUTRAL/no-op` davranacak.

---

## Domain model: Efloud sosyal içerikten çıkarılacak kavramlar

Her Telegram/X postu aşağıdaki yapılandırılmış sinyallere çevrilecek:

- `symbols`: BTC/USDT, ETH/USDT vb.
- `timeframes`: 1D, 4H, 1H, 15M vb.
- `bias`: bullish, bearish, neutral, educational
- `structure_terms`: MSB, BOS, CHoCH, HH, HL, LH, LL
- `zones`: FVG, Order Block, OTE, premium/discount, breaker
- `liquidity_terms`: sweep, equal highs/lows, stop hunt, liquidity pool
- `risk_terms`: invalidation, SL, TP, TP1, TP2, BE, RR
- `setup_recipe`: HTF bias -> zone pullback -> liquidity sweep/confirmation -> entry -> SL -> target
- `confidence`: parser confidence, not trade confidence
- `source_url/source_id`: traceability

Bu alanlar stratejiye doğrudan emir verdirmeyecek; yalnızca research/backtest hipotezi üretmek için kullanılacak.

---

### Task 1: Extract social feed logic out of `backend/api.py`

**Objective:** `/api/social/feeds` endpointindeki scraper/fallback mantığını test edilebilir modüle taşı.

**Files:**
- Create: `backend/social/__init__.py`
- Create: `backend/social/feeds.py`
- Modify: `backend/api.py:325-417`
- Test: `backend/tests/test_social_feeds.py`

**Step 1: Write failing tests**

Test cases:
- Telegram HTML içinden message text + datetime parse edilir.
- HTML boşsa fallback postlar döner.
- Endpoint response shape `{telegram: list, twitter: list}` olarak kalır.

Run:

```bash
pytest backend/tests/test_social_feeds.py -v
```

Expected: FAIL because `backend.social.feeds` does not exist yet.

**Step 2: Implement module**

`backend/social/feeds.py` içinde:
- `FeedItem` dataclass/Pydantic model
- `parse_telegram_public_html(html: str) -> list[dict]`
- `fallback_telegram_posts() -> list[dict]`
- `fallback_x_posts() -> list[dict]`
- `async fetch_social_feeds(client: httpx.AsyncClient | None = None) -> dict`

**Step 3: Wire API**

`backend/api.py` endpointi sadece şunu yapsın:

```python
from backend.social.feeds import fetch_social_feeds

@router.get("/social/feeds", dependencies=[Depends(require_auth)])
async def social_feeds() -> dict:
    return await fetch_social_feeds()
```

**Step 4: Verify**

```bash
pytest backend/tests/test_social_feeds.py -v
pytest backend/tests/test_api_smoke.py -v
```

---

### Task 2: Add social doctrine parser

**Objective:** Paylaşımlardaki SMC/MPA kavramlarını deterministik ve test edilebilir şekilde çıkar.

**Files:**
- Create: `backend/social/doctrine.py`
- Test: `backend/tests/test_social_doctrine.py`

**Step 1: Write failing tests**

Inputs:
- `BTC Güncelleme: 1D grafikte market yapısı bullish (MSB gerçekleşti). OTE bölgesinden... FVG... 103k hedef...`
- `ETH/USDT: 4H grafikte FVG test edildi... 2480 korunduğu sürece... 2650 - 2800...`
- `Likidite temizliği yapılan her bölge potansiyel dönüş noktasıdır.`

Expected extraction:
- symbols, timeframes, bias, structure_terms, zones, liquidity_terms, levels, targets.

**Step 2: Implement deterministic parser**

Use regex + keyword dictionaries first. Do not use LLM as source of truth in this task.

Core function:

```python
def extract_doctrine(feed_item: dict) -> dict:
    ...
```

Output shape:

```json
{
  "feed_id": "tg-...",
  "symbol": "BTC/USDT",
  "timeframes": ["1d"],
  "bias": "bullish",
  "structure_terms": ["MSB"],
  "zones": ["OTE", "FVG"],
  "liquidity_terms": [],
  "levels": [93200, 94100, 103000],
  "setup_recipe": ["htf_bias", "pullback_to_ote", "fvg_support", "target_upper_liquidity"],
  "confidence": 0.75
}
```

**Step 3: Verify**

```bash
pytest backend/tests/test_social_doctrine.py -v
```

---

### Task 3: Persist social doctrine snapshots safely

**Objective:** İçerik ve çıkarılan doktrinler yeniden analiz edilebilsin diye local state JSONL arşivi oluştur.

**Files:**
- Create: `backend/social/archive.py`
- Create: `state/social_doctrine.jsonl` only through runtime, not committed
- Test: `backend/tests/test_social_archive.py`

**Implementation:**
- Atomic append helper: `append_doctrine_snapshot(path, item, doctrine)`
- Dedup key: `source + id + content_hash`
- No secrets, no cookies.

**Verification:**

```bash
pytest backend/tests/test_social_archive.py -v
```

---

### Task 4: Add research hypothesis generator

**Objective:** Sosyal doktrinlerden test edilebilir strateji hipotezleri üret.

**Files:**
- Create: `backend/social/hypotheses.py`
- Test: `backend/tests/test_social_hypotheses.py`

**Examples:**
- Posts emphasize `HTF MSB + OTE pullback + FVG reaction` -> candidate config increasing weight for HTF trend alignment and pullback confirmation.
- Posts emphasize `liquidity sweep before reversal` -> candidate metric requiring sweep-before-entry and measuring stop hunt reduction.
- Posts emphasize `TP1 + BE` -> validate lifecycle settings rather than entry filter.

**Output shape:**

```json
{
  "id": "social_ote_fvg_htf_bias_v1",
  "rationale": "Efloud posts repeatedly require HTF structure + OTE/FVG pullback confluence.",
  "candidate_config_patch": {
    "engine.confluence_weights.htf_bias": 1.2,
    "engine.smc_v2.require_pullback_zone": true
  },
  "metrics_to_watch": ["win_rate", "avg_realized_rr", "stop_hunt_rate", "max_drawdown_pct"],
  "risk": "research_only"
}
```

---

### Task 5: Extend backtest comparison reports with doctrine tags

**Objective:** Backtest sonuçlarında hangi sosyal/doktrin hipotezinin test edildiği açıkça görünsün.

**Files:**
- Modify: `backtest/comparison.py`
- Modify: `backtest/cli.py`
- Test: `backend/tests/test_backtest_social_tags.py`

**CLI addition:**

```bash
python -m backtest.cli compare \
  --symbols BTC/USDT,ETH/USDT \
  --period-days 180 \
  --config configs/config.phase2_1k.yaml \
  --hypothesis social_ote_fvg_htf_bias_v1
```

**Report addition:**

```json
{
  "hypothesis": "social_ote_fvg_htf_bias_v1",
  "doctrine_tags": ["HTF_BIAS", "OTE", "FVG", "MSB"],
  "gates": {...}
}
```

---

### Task 6: Create research runner script

**Objective:** Sosyal doktrinlerden aday config üretip backtest koşturan güvenli research scripti yaz.

**Files:**
- Create: `scripts/research_social_strategy.py`
- Test: `backend/tests/test_research_social_strategy.py`

**Command:**

```bash
python -m scripts.research_social_strategy \
  --symbols BTC/USDT,ETH/USDT,SOL/USDT \
  --period-days 180 \
  --base-config configs/config.phase2_1k.yaml \
  --state state/social_doctrine.jsonl
```

**Safety checks:**
- Refuse to write `config.yaml`.
- Write only under `configs/candidates/` and `reports/social_research/`.
- Emit `NO_PROMOTION` flag in every report.

---

### Task 7: Add backend API for social research status

**Objective:** Dashboard, sosyal doktrin ve research sonuçlarını okuyabilsin.

**Files:**
- Create: `backend/social/reports.py`
- Modify: `backend/api.py`
- Test: `backend/tests/test_social_research_api.py`

**Endpoints:**
- `GET /api/social/doctrine` -> latest extracted doctrine list
- `GET /api/social/hypotheses` -> generated research hypotheses
- `GET /api/social/research-runs` -> latest backtest reports summary

All endpoints auth-protected.

---

### Task 8: Upgrade frontend SocialFeeds into Learning Center

**Objective:** Kullanıcı yalnızca postları değil, bottaki öğrenme döngüsünü de görebilsin.

**Files:**
- Modify: `frontend/components/SocialFeeds.tsx`
- Create: `frontend/components/SocialLearningCenter.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/lib/api.ts`

**UI sections:**
- Raw Telegram/X posts
- Extracted doctrine tags
- Hypothesis cards
- Latest backtest verdict badges: PASS / WARN / REJECT
- Hard warning: `Research only — live config unchanged`

**Verify:**

```bash
cd frontend
npm run typecheck
npm run build
```

---

### Task 9: Add doctrine-to-engine gap report

**Objective:** Efloud içerikleriyle mevcut engine arasında hangi kavramların eksik/yarım olduğunu raporla.

**Files:**
- Create: `scripts/report_doctrine_engine_gap.py`
- Output: `reports/social_research/latest_gap_report.md`

**Checks:**
- Social posts mention concept X.
- Existing modules implementing X:
  - `engine/smc_v2/zones.py` for FVG/OB zones
  - `engine/smc_v2/swing_anchor.py` for HTF swing anchor
  - `engine/smc_v2/confirmation.py` for LTF confirmation
  - `engine/smc_v2/liquidity_pools.py` if present/needed
- Missing concept becomes candidate task, not live behavior.

---

### Task 10: Promotion gate document

**Objective:** Backtest ile iyi çıkan hipotezlerin canlıya geçmeden önceki karar sürecini standardize et.

**Files:**
- Create: `docs/runbooks/social-research-promotion.md`

**Promotion gates:**
1. 180d compare report: no `hard_reject`.
2. v2 shadow: at least 7 days.
3. Stop-hunt rate improves or does not worsen.
4. Max drawdown does not exceed baseline by >10%.
5. Human approval before any `config.yaml` change.

---

## Recommended first implementation slice

Implement Tasks 1-3 first. This gives immediate value with low risk:

- Cleaner social feed code.
- Testable Efloud doctrine extraction.
- Persistent research dataset.
- No strategy/live behavior changes.

Then implement Tasks 4-6 to connect the doctrine to backtest research. Frontend should come after backend response shapes stabilize.

---

## Verification suite for the whole feature

```bash
pytest backend/tests/test_social_feeds.py -v
pytest backend/tests/test_social_doctrine.py -v
pytest backend/tests/test_social_archive.py -v
pytest backend/tests/test_social_hypotheses.py -v
pytest backend/tests/test_backtest_social_tags.py -v
pytest backend/tests/test_social_research_api.py -v
cd frontend && npm run typecheck && npm run build
```

---

## Definition of done

- Efloud Telegram/X content is parsed into doctrine tags with tests.
- Doctrine snapshots are archived with deduplication.
- Backtest reports can be tied to a social hypothesis.
- Frontend shows raw content, extracted logic, hypothesis status, and research-only warning.
- No live config or production compose/env changed.
- A human can inspect evidence before deciding whether any strategy improvement deserves shadow rollout.
