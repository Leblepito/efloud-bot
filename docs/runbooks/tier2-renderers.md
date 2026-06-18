# Tier-2 Content Renderers Runbook (P-002 M6 second half)

## Amaç

`scripts/content_templates/templates.yaml` → render → pre-gate → enqueue.
**Tier-1 (T-027) queue skeleton + Tier-2 renderer köprüsü.**

## Lane topology (operatör kararı, 2026-06-19)

```
┌────────────────────────┐      values       ┌──────────────────────────┐
│  RESEARCH LANE         │  ──────────────►  │  RENDERER (this module)  │
│  backend/social/       │                   │  tier2_renderers.py      │
│  - ManusClient         │                   │                          │
│  - xurl_client         │                   │  1. render(values)       │
│  - feed scrapers       │                   │  2. pre_gate(text)       │
└────────────────────────┘                   │  3. enqueue(draft)       │
                                             └────────────┬─────────────┘
                                                          │ draft: pending_review
                                                          ▼
                                             ┌──────────────────────────┐
                                             │  PUBLISH LANE            │
                                             │  scripts/lane_e/         │
                                             │  - LaneEPublisher        │
                                             │  - xurl publisher (T-026)│
                                             │  - Manus publisher (T-025)│
                                             └──────────────────────────┘
```

**Bu modülün yaptığı:** research üretimi → formatlanmış + gate-validated draft.
**Bu modülün YAPMADIĞI:** outbound publish. `lane_e/publisher.py`'in işi.

## Akış

### 1. Render

```python
from backend.social.tier2_renderers import render

rc = render(
    "signal_idea",       # template_id (5 tip: signal_idea, signal_idea_thread,
                         #                       educational, performance_recap,
                         #                       promotional, market_commentary)
    "en",                # lang ("en" | "tr"; RU/KZ = stub, raise eder)
    {
        "symbol": "BTCUSDT", "tf": "15m", "direction": "LONG",
        "structure": "bullish OB + FVG retest",
        "entry": "64200", "sl": "63500", "tp1": "65400", "tp2": "66800",
        "rr": "1:2.6", "risk_pct": "1.1",
        "chart_img": "https://...",   # M2 chart export URL
    },
)
```

**`rc` (`RenderedContent`):**

| Field | Tip | Açıklama |
|---|---|---|
| `format` | "single" \| "thread" | template'in format'ı |
| `body` | str \| None | single ise body |
| `tweets` | list[str] | thread ise her tweet |
| `media` | list[str] | chart_img URL'leri (M2 deliverable) |
| `disclaimer_present` | bool | `meta.disclaimers[lang]` exact match |
| `sim_label_present` | bool | `[SIMULATED]`/`[BACKTEST]` etc. regex match |
| `values_used` | dict | hangi placeholder'lar kullanıldı (audit) |

### 2. Pre-gate

```python
from backend.social.tier2_renderers import pre_gate

violations = pre_gate(rc)        # scripts.content_compliance.find_violations
# [] == CLEAN, dolu == violation tag'leri
```

**Boş liste** → enqueue yapılabilir.
**Dolu liste** → quarantine; `enqueue()` raise eder `ComplianceGateViolationError`.

### 3. Enqueue (T-027 queue)

```python
from backend.social.content_queue import create_draft
from backend.social.tier2_renderers import render, pre_gate, enqueue

rc = render("performance_recap", "tr", values)
violations = pre_gate(rc)

if not violations:
    draft = enqueue(rc, violations, queue_create_draft_fn=create_draft)
    # draft: ContentDraft (T-027) — pending_review state'e geçirilmek için
    # submit_for_review() çağrılacak (compliance gate zaten PASS)
```

### 4. Tam pipeline (convenience)

```python
from backend.social.tier2_renderers import render_and_enqueue

rc, draft = render_and_enqueue(
    "signal_idea", "en", values,
    queue_create_draft_fn=create_draft,
)
```

## Mevcut template'ler (5 + 1 thread variant)

| ID | Kategori | Format | Placeholder'lar |
|---|---|---|---|
| `signal_idea` | signal | single | symbol, tf, direction, structure, entry, sl, tp1, tp2, rr, risk_pct, chart_img |
| `signal_idea_thread` | signal | thread | + invalidation_note |
| `educational` | educational | thread | concept, one_line_definition, how_to_spot, how_to_use, risk_pct |
| `performance_recap` | performance | single | week, n_ideas, n_reached, avg_r, risk_pct |
| `promotional` | promotional | single | feature, cta_url |
| `market_commentary` | commentary | single | symbol, tf, bias, levels, watch_note |

## Hata durumları

| Hata | Sebep | Çözüm |
|---|---|---|
| `TemplateNotFoundError` | template_id yanlış | 5 ID'den biri olmalı |
| `LanguageNotSupportedError` | lang bu template'de yok | EN veya TR kullan; RU/KZ için stub tamamla |
| `TemplateStubError` | RU/KZ TODO henüz tamamlanmamış | `templates.yaml` README §"RU/KZ addition" adımları |
| `MissingPlaceholderError` | values'da key eksik | sample dict'i `templates.yaml` `sample:` field'ından al |
| `ComplianceGateViolationError` | pre_gate FAIL | ihlal tag'lerini logla; renderer düzeltilmeli (operator action) |

## Gate evolüsyonu takibi

Master'a PR #226 ile **CMP-3/CMP-5 unlabeled_simulation** gate'i merged.
Yeni gate'ler gelirse:

1. `scripts/content_compliance.py` güncellenir (gate-side)
2. Template'ler `verify_compliance.py` ile yeniden doğrulanır
3. Bu renderer değişmez (pre_gate lazy import ediyor)
4. `tier2_renderers` testleri gate live olduğunu doğrular (negative control)

## Çalıştırma & test

```bash
# Template'lerin gate'i geçtiğini doğrula (operatör M6 deliverable)
python scripts/content_templates/verify_compliance.py
# → checked=12 clean=12 failed=0  +  RESULT: ALL TEMPLATES PASS

# Renderer unit testleri
python -m pytest backend/tests/test_tier2_renderers.py -v
# → 26 passed

# Global regression
python -m pytest backend/tests/ -q --tb=no
# → 1311 passed (eskisi 1285, +26 yeni)
```

## Bilinmeyen / Bilinen TODO

- **Telegram inline approve/reject hook:** `pending_review` → `approved` geçişi
  şu an manuel. Operatör kararı ile Telegram callback handler eklenecek.
- **xurl/Manus publisher entegrasyonu:** `mark_sent` wiring T-026 + T-025
  merge sonrası. Renderer → queue → publish katmanları sıralı bağlanacak.
- **M2 chart-export consumer:** `chart_img` placeholder şu an URL bekliyor
  (M2 Method A → CDN hosted snapshot). M2 deliverable sonrası URL otomatik
  resolve edilecek.
- **RU/KZ:** şu an TODO stub. README §"RU/KZ addition" 5 adım gerekiyor
  (disclaimer + banned-phrase + perf-word + money regex + native-speaker).
