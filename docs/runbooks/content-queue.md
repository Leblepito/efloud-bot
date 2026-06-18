# Content Approval Queue Runbook (P-002 M6)

## Amaç
Taslak → onay → gönderim state machine. Operatör M6 template'lerini
getirince `tier2_renderers.py` ile bağlanır
(signal/educational/recap/promo/market_update).

## Lifecycle

```
DRAFT → PENDING_REVIEW → APPROVED → SENT   (happy path)
                  ↓           ↓
                REJECTED ←────┘ (revize)
                  ↓
                DRAFT (revise_rejected)
```

## Acceptance Gate

`scripts/content_compliance.find_violations(body, lang)` çıktısı
`violation_count == 0` olmalı. Aksi halde `ComplianceGateError`.

## Akış

### 1. Migration uygula

```bash
docker exec efloud-bot python3 -m backend.migrate up
# veya lokal:
psql $DATABASE_URL -f backend/migrations/009_content_drafts.sql
```

### 2. Draft oluştur (CLI / programmatic)

```python
from backend.social.content_queue import create_draft, submit_for_review
from scripts.content_compliance import find_violations

d = create_draft(
    body="BTC long bias, 65k breakout",
    lang="en",
    post_type="signal",
    meta={
        "side": "long",
        "entry": 65000,
        "sl": 63500,
        "tp1": 68000,
        "chart_url": "https://...",
    },
)
report = find_violations(d.body, d.lang)
submit_for_review(d, report)
```

### 3. Onay (şimdilik manual, Telegram gateway sonra)

```python
approve_draft(d, reviewer_id="utku")
# veya
reject_draft(d, reviewer_id="utku", reason="çok ajitatif")
```

### 4. Persistence

```python
from backend.social.queue_storage import save_draft, load_draft
import asyncpg, os

async def persist():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    await save_draft(pool, d)
    loaded = await load_draft(pool, d.draft_id)
    await pool.close()
```

### 5. Gönderim (T-026/T-025 entegrasyonu sonrası)

```python
from backend.social.xurl_client import XurlClient
# veya
from backend.social.manus_client import ManusClient

# ... approve + send ...
mark_sent(d)
```

## Tehlike Sinyalleri

1. **`violation_count > 0` ile PENDING_REVIEW'a geçemez** — gate
   ihlali, reddet ve revize ettir.
2. **`draft_id` collision** — `secrets.token_urlsafe(12)` 16-char,
   çakışma astronomik düşük; PRIMARY KEY constraint ekledik.
3. **Migration uygulanmamış** — `relation "content_drafts" does not
   exist` hatası → migration 009 çalıştır.
4. **`meta` JSON serialize hatası** — DB `JSONB` cast edemezse
   `_draft_to_params` loguna bak; non-serializable tip (set, custom
   obj) kullanma.

## Schema

- Tablo: `content_drafts` (migration 009)
- Index: `status`, `(lang, post_type)`, `created_at DESC`
- Constraint: `lang IN (en, tr, ru, kz, all)`,
  `post_type IN (signal, educational, performance_recap, promo, market_update)`,
  `status IN (draft, pending_review, approved, rejected, sent, failed)`

## Bilinmeyen / Bilinen TODO

- Telegram inline `callback_data=approve:<draft_id>` gateway hook'u
  (sonraki sprint)
- `tier2_renderers.py` (signal/educational/recap/promo/market_update) —
  operatör M6 template deliverable'ını bekliyor
- xurl/Manus gönderim sonrası `mark_sent` wiring (T-026 + T-025 merge
  sonrası)
