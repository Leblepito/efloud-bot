# Runbook: Manus.im API Kurulumu + Operasyonu (M3 / P-002 Faz A)

> **Amaç:** Hermes'i Manus.im REST API'sına bağlamak (P-002 Faz A M3). Manus, içerik üretim
> pipeline'ının (M6) beyni olacak — X thread, YouTube Shorts scripti, haftalık blog snapshot'u
> üretecek. **Default OFF** — API key yokken veya flag false iken client no-op.

---

## 1. Mimari

```
┌──────────────────────┐    ┌─────────────────────┐
│  scripts/routines/   │    │  backend/social/     │
│  content_pipeline.py │ →  │  manus_client.py    │ → [https://api.manus.ai]
│  (M6 — ileride)      │    │  + templates/*.json │
└──────────────────────┘    └─────────────────────┘
                                      │
                                      ↓
                            ┌─────────────────────┐
                            │  Manus task queue   │
                            │  (web app + webhooks│
                            │   → döner result    │
                            │   → Hermes poll'lar)│
                            └─────────────────────┘
```

**Manus API v2** (kaynak: <https://open.manus.im/docs>)
- Base URL: `https://api.manus.ai`
- Auth header: `x-manus-api-key: <KEY>` (basit, OAuth'a gerek yok)
- POST `/v2/task.create` → task başlatır (async)
- GET `/v2/task.listMessages?task_id=...` → poll progress
- Task statusları: `running`, `stopped` (tamam), `waiting` (input gerekli), `error`
- Webhook desteği var (ileride kullanılabilir — şimdilik polling)

---

## 2. Operatör Kurulumu (5 dakika)

### Adım 1 — Manus hesabı aç

1. <https://manus.im> → "Sign Up" (Google veya email)
2. Email doğrula, hesap aktif.

### Adım 2 — API key üret

1. Manus web app → avatar (sağ üst) → **Settings** → **API Integration**
   (veya doğrudan: <https://manus.im/settings/api>)
2. **"Create API Key"** tıkla, isim ver: `efloud-production` (prod) veya
   `efloud-staging` (test).
3. Key'i **hemen kopyala** — yalnız bir kez gösterilir.
4. **Güvenli yere kaydet** (password manager veya `~/.hermes/secrets`).

### Adım 3 — Manus API key'i VPS'e ekle

`/etc/efloud-backup.env` (zaten var, yeni entry ekle):

```bash
# Manus REST API — P-002 Faz A M3
MANUS_API_ENABLED=true
MANUS_API_KEY=sk-...
MANUS_API_BASE_URL=https://api.manus.ai  # default, override only for testing
```

> **Güvenlik:** `/etc/efloud-backup.env` chmod 600, root only. Repo'ya ASLA commit etme.
> `.env` veya `.env.*` dosyaları `.gitignore`'da (18 Jun hardening eklendi).

**Doğrulama (VPS'te):**

```bash
sudo chmod 600 /etc/efloud-backup.env
sudo chown root:root /etc/efloud-backup.env
source /etc/efloud-backup.env
python3 -c "from backend.social.manus_client import ManusClient; c=ManusClient(); print('active=', c.is_active())"
# → active= True (key doğruysa) veya active= False (key yanlış/eksik)
```

### Adım 4 — Smoke test

```bash
cd /opt/efloud-bot
python3 -m backend.tests.test_manus_client  # veya pytest
# → 41 passed
```

**İlk canlı test** (gerçek Manus API'ye minimal istek):

```bash
source /etc/efloud-backup.env
python3 <<'EOF'
from backend.social.manus_client import ManusClient, load_template
c = ManusClient()
assert c.is_active(), "client not active — check MANUS_API_ENABLED + MANUS_API_KEY"
template = load_template("manus_x_thread")
result = c.create_task(
    prompt="Test: efloud manus bağlantısı çalışıyor.",
    template=template,
)
print("task_id:", result.task_id)
print("req_id:", result.request_id)
status = c.wait_for_completion(result.task_id, timeout_sec=120)
print("status:", status.agent_status)
print("result:", (status.result_text or "")[:200])
EOF
```

Beklenen: `task_id` döner, `wait_for_completion` 30-60 saniyede `stopped` döner, `result`
alanı 200 char taslak X thread içerir.

---

## 3. Manus Pricing (operatör kararı)

| Plan | Fiyat | Task kotası | Not |
|---|---|---|---|
| **Free** | $0 | Günde ~5 task (deneme) | Sadece dev/test |
| **Pro** | $39/ay | ~500 task/ay | Bireysel maker |
| **Team** | $99/ay | ~2000 task/ay | Production marketing |

**Tavsiye:** MVP için **Free tier** yeterli (haftada 3-5 içerik × 1 task). Üretim ölçeğinde
**Pro**'ya geçiş (aylık $39, u2algo premium gelirinin %100'ünü zaten 1 müşteri karşılıyor —
runitup öncesi düşünülebilir).

---

## 4. Rate Limit + Maliyet Kontrolü

Manus API rate limit'leri plan'a göre değişir, per-user:
- Free: dakikada ~2 task
- Pro: dakikada ~10 task

**Hermes tarafında otomatik koruma** (zaten implement):
- Exponential backoff 429/5xx (MAX_RETRIES=3)
- 4xx client error → non-retryable (budget yanmasın)
- Default OFF → key yokken rate limit'e takılmaz

**İzleme:** `efloud.manus` logger INFO/WARN/ERROR seviyesinde her çağrıyı loglar.
`request_id` her çağrıda loglanır → Manus web app'te task eşleştirmesi kolay.

---

## 5. Mevcut 3 Template

`backend/social/templates/`:

| Template | Amaç | Kanal | Token |
|---|---|---|---|
| `manus_x_thread.json` | X/Twitter thread üretimi (4-6 tweet) | x.com | taslak → Hermes onayı → manuel post |
| `manus_youtube_short.json` | YouTube Shorts script üretimi (<60sn) | youtube.com | taslak → seslendirme → upload |
| `manus_weekly_snapshot.json` | Haftalık performans blog yazısı | u2algo.com /blog | taslak → Hermes edit → publish |

Her template:
- `name`, `prompt_template`, `compliance.{tr,en}`, `task_metadata.{type,version}` alanları zorunlu
- `prompt_template` içinde `{{input}}` placeholder + compliance disclaimer token'ları (TR + EN) zorunlu
- `_validate_template()` şeması boot'ta hatalı template'i yakalar

---

## 6. Tehlike Sinyalleri + Aksiyon

| Sinyal | Olası neden | Aksiyon |
|---|---|---|
| `is_active()` False dönüyor | `MANUS_API_ENABLED` false veya `MANUS_API_KEY` boş | env'i kontrol et, `source /etc/efloud-backup.env` |
| `ManusAuthError: http_401` | Key invalid veya revoked | Manus settings → key regenerate, env güncelle, restart |
| `ManusRateLimit: http_429_after_retries` | Dakikada >10 task (Pro limit) | script throttle ekle veya Free → Pro upgrade |
| `TemplateValidationError: missing_compliance_tr_token` | Yeni template'te TR disclaimer unutulmuş | template'i düzelt, tekrar yükle |
| Sürekli `timeout` hatası | Manus API yavaş veya network | `MANUS_API_BASE_URL` override dene, status sayfasını kontrol et |
| Log'da `sk-***` yerine raw key görünüyor | Yeni log path eklenmiş, maskeleme unutulmuş | `_mask_key()` kullan, code review'a aç |

---

## 7. Operasyon: Yeni Template Ekleme

İhtiyaç: yeni bir kanal/format için template (örn. LinkedIn post, Newsletter).

**PR örneği:**

1. `backend/social/templates/manus_<isim>.json` oluştur.
2. Zorunlu alanlar: `name`, `prompt_template`, `compliance.{tr,en}`, `task_metadata.{type,version}`.
3. `prompt_template` içinde `{{input}}` placeholder + TR + EN compliance token.
4. PR'da açıklama: hangi kanal, hangi sıklıkta kullanılacak, kim onaylayacak.
5. Review → merge → template otomatik aktif (validation build-time).
6. Smoke test: `python3 -c "from backend.social.manus_client import load_template; load_template('manus_<isim>')"`.

---

## 8. Referanslar

- P-002 plan: `LLTODO/plans/P-002-marketing-growth-pipeline.md` (§2 Faz A M3, §4 S5 secrets).
- LLTODO M3 kartı: `LLTODO/tasks/IN_PROGRESS/M3-manus-rest-client.md`.
- Manus API docs: <https://open.manus.im/docs> (v2 aktif).
- Client modülü: `backend/social/manus_client.py` (410 satır).
- Test: `backend/tests/test_manus_client.py` (41 test, hermetic — network YOK).
- Templates: `backend/social/templates/manus_*.json` (3 adet).
