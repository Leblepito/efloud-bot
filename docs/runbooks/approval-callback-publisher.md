# Approval Callback + xurl Publisher Runbook (P-002 follow-up)

## 1. Approval Callback (T-030)

`backend/social/approval_callback.py` — Telegram inline button callback'lerini
queue state transition'a bağlayan generic handler.

**Contract:**

```python
# Callback data format (Telegram uyumlu):
"approve:<draft_id>"  → state.pending_review → state.approved
"reject:<draft_id>"   → state.pending_review → state.rejected
```

**Adapter yazma (Telegram):**

```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from backend.social.approval_callback import (
    build_callback_data, parse_callback, handle_callback,
)
from backend.social.content_queue import load_draft

async def on_callback(update: Update, context):
    cb = parse_callback(update.callback_query.data)
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        draft = await load_draft(pool, cb.draft_id)
        updated = handle_callback(cb, reviewer_id=str(update.effective_user.id), draft=draft)
        await update.callback_query.answer(text=cb.response_text)
```

**Adapter yazma (Slack/Discord/web):** Aynı `callback_data` parse'ı.

## 2. xurl Publisher (T-031)

`scripts/lane_e/publishers/xurl.py` — `xurl` Go binary üzerinden X/Twitter'a yayın.

**Default OFF** (config.xurl.enabled=false veya X_API_ENABLED=false):
publish noop döner (`PublishResult.ok=True, ref=None`).

**Aktivasyon:**

```bash
# VPS .env.production
X_API_ENABLED=true
# xurl binary yüklü olmalı (operatör runbook xurl-setup.md)
go install github.com/anthonyrabiaza/xurl@latest
```

**Lane topology:**

```
backend/social/   → research (renderer, queue, callback handler)
                    ↓ (approved drafts)
scripts/lane_e/   → publish (xurl publisher)
                    ↓ (subprocess)
xurl binary       → X/Twitter API
```

## 3. End-to-end akış

```
1. tier2_renderers.render_and_enqueue(...)
   → queue: draft.status = DRAFT, then submit_for_review → PENDING_REVIEW

2. Telegram adapter (T-030 entegrasyonu sonrası):
   → inline buttons: build_callback_data("approve", draft_id)
   → build_callback_data("reject", draft_id)
   → chat_id'ye gönderir

3. User butona basar:
   → callback "approve:draft_001_xyz12" gelir
   → handle_callback(...) → draft.status = APPROVED

4. LaneEPublisher (şu an yazılmadı, sonraki sprint):
   → approved drafts → dispatch enabled publishers
   → xurl publisher (T-031) → subprocess xurl post
   → mark_sent(draft) on success
```

## 4. Test & validate

```bash
python -m pytest backend/tests/test_approval_callback.py -v   # 23 PASS
python -m pytest scripts/lane_e/tests/test_xurl_publisher.py -v   # 13 PASS
python -m pytest backend/tests/ scripts/lane_e/tests/ -q --tb=no   # 1378 PASS (regression)
python LLTODO/scripts/lltodo_lint.py                              # 8/8 PASS
```

## 5. Tehlike sinyalleri

1. **Callback mismatch (draft_id uyuşmuyor)** → log warning + raise.
   Telegram adapter bunu answer() ile "draft not found" reply etmeli.
2. **xurl binary yok ama enabled=True** → PublishResult.ok=False.
   Operatör runbook xurl-setup.md §1 takip etmeli.
3. **subprocess timeout** → 30s, sonra PublishResult.ok=False.
   Network issue → retry (LaneEPublisher sorumluluğu).

## 6. Bilinmeyen / Bilinen TODO

- **Telegram adapter:** bu modül yazılmadı (operatör kararı: önce bu generic
  handler PR'a girsin, sonra Telegram adapter ayrı PR). Adapter yazımı ~100
  satır + test, T-032 olur.
- **LaneEPublisher:** approved drafts → xurl dispatch pipeline (şu an yok).
  Şu an xurl publisher tek başına çalışır; LaneEPublisher multi-publisher
  koordinasyonu sağlar.
- **Retry/backoff:** xurl timeout → retry (operatör policy).
- **Manus publisher:** T-025 merge sonrası ayrı publisher (handmirror).
