# T-025 (P-002 Faz A M3): Manus REST Client + Task Template Şemaları

**Epic:** P-002 (Marketing & Growth)
**Claimed by:** @hermes (2026-06-18)
**Tahmini süre:** 1 gün
**Bağımlılık:** P-002 plan (`LLTODO/plans/P-002-marketing-growth-pipeline.md`) CONSENSUS_REACHED; operatör OQ kararları T-025 için bloker DEĞİL (default-OFF + key-yokken no-op)

**Kaynak:** P-002 plan §2 Faz A M3 satırı:
> M3 | Manus REST client (fail-safe, flag OFF) + task template şemaları | `backend/social/manus_client.py`, `tests/` hermetic unit | Key yokken no-op; template validate testleri yeşil

**ID mapping notu:** Bu kart operasyonel olarak P-002 planının "M3" PR'ına karşılık gelir;
LLTODO R3 naming kuralı (T-NNN-slug.md) gereği kart ID'si T-025'tir. Plan referansları "M3" korur.

## Hedef

Manus.im'in REST API'sini (base: `https://api.manus.ai`, auth header: `x-manus-api-key`) Hermes'e
bağlamak için fail-safe bir Python client yazmak. **Default OFF** — Manus API key yokken veya
flag false iken sıfır dış çağrı. İçerik pipeline (M6) bu client'ın üstüne inşa edilecek.

## Çıktılar

- [ ] `backend/social/manus_client.py` — `ManusClient` sınıfı (create_task, get_task, list_messages, wait_for_completion)
- [ ] `backend/social/manus_client.py` — flag-gated `_enabled()` (env: `MANUS_API_ENABLED=true`)
- [ ] `backend/social/manus_client.py` — key kontrolü (`MANUS_API_KEY` env, yoksa log+return None)
- [ ] `backend/social/templates/manus_x_thread.json` — X/Twitter thread template
- [ ] `backend/social/templates/manus_youtube_short.json` — YouTube Shorts script template
- [ ] `backend/social/templates/manus_weekly_snapshot.json` — Haftalık dashboard snapshot template
- [ ] `backend/tests/test_manus_client.py` — hermetic unit testler (key yokken no-op, network mock, schema validate)
- [ ] `docs/runbooks/manus-setup.md` — operatör için API key edinme + env set etme + webhook kurulumu
- [ ] `LLTODO/SCOREBOARD.md` — M3 satırı DONE, metrik güncelleme

## Acceptance Kriterleri

- [ ] **Fail-safe:** key yoksa veya flag false ise client metodları no-op + `ManusDisabled` log
- [ ] **Hermetic testler:** network çağrısı YOK (mocked), key olmadan test ortamı PASS
- [ ] **Schema validate:** task templates JSON schema ile doğrulanır, hatalı template → `TemplateValidationError`
- [ ] **Compliance gate:** her template'de zorunlu disclaimer alanı (TR + EN)
- [ ] **Retry/backoff:** 429/5xx durumunda exponential backoff (max 3 retry)
- [ ] **Logging:** tüm çağrılar `efloud.manus` logger'ına INFO/WARN, hata durumunda ERROR (request_id her zaman loglanır)
- [ ] **No secrets in logs:** API key maskelenir (`sk-***` veya son 4 karakter), response body truncate (1024 char)
- [ ] **Trade-path izolasyonu:** `engine/safety/`, `lifecycle.py`, order path'e DOKUNULMAZ (G1)

## Tasarım Kararları

- **Async yerine sync:** Manus API'sı HTTP polling tabanlı, blocking wrapper yeterli (start polling task in background thread, kullanım `wait_for_completion` ile blokla)
- **Retry:** `tenacity` kütüphanesi **YOK** (yeni dep) → elle exponential backoff (daha az yüzey alanı)
- **Mock strategy:** test'lerde `httpx_mock` veya `unittest.mock.patch` — gerçek network YOK
- **Schema:** `jsonschema` kütüphanesi **YOK** (yeni dep) → elle validate (basit şemalar için yeterli, 3 template)
- **Template lokasyonu:** `backend/social/templates/` (mevcut `backend/social/` pattern'ine uygun)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-18 | IN_PROGRESS | @hermes — P-002 M3 PR kod + test + runbook. Default OFF (canlı config DEĞİŞMEDİ, MANUS_API_KEY yok). Operatör sonra key ekleyince aktive. |
| 2026-06-18 | bugfix | @hermes — `urllib` → `requests` transport migration. **Kök neden:** Python `urllib` TLS fingerprint (JA3) Hetzner IP'sinde AWS WAF tarafından 403 dönüyordu (curl ile 200). `requests` (urllib3 transport) farklı JA3 → bypass. Doğrulama: gerçek `task.list` çağrısı 200 OK döndü (`request_id=92657253...`, task_id `Bnk8FCrVYgZ6Kavx3eA332`). Regression guard: 41 unit test PASS, `_SESSION` mock'lu. |
| 2026-06-18 | env_wired | @hermes — `MANUS_API_KEY` `.env.production`'a eklendi (permission 600), `MANUS_API_ENABLED=false` (default OFF). Container recreate gerektirmez — bot autostart=0 manuel kontrol altında. Operatör sonra `MANUS_API_ENABLED=true` yapıp `docker compose up -d` ile recreate. |

