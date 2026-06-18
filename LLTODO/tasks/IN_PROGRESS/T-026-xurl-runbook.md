# T-026 (P-002 Faz A M1): xurl CLI Kurulum + Auth Runbook + Facade

**Epic:** P-002 (Marketing & Growth)
**Claimed by:** @hermes (2026-06-18)
**Tahmini süre:** 0.5 gün (küçük kapsam, doc-only + facade)
**Kaynak:** P-002 plan §2 Faz A M1 satırı:
> M1 | xurl CLI kurulum + auth runbook (doc-only) | `docs/runbooks/xurl-setup.md` | Runbook ile VPS'te xurl auth tamam; secrets .env-only

**ID mapping notu:** Kart operasyonel olarak P-002 planının "M1" PR'ına karşılık gelir;
LLTODO R3 naming kuralı gereği kart ID'si T-026. Plan referansları "M1" korur.

## Hedef

xurl CLI'ını (Go binary, <https://github.com/anthonyrabiaza/xurl>) Hermes'in sosyal pipeline'ına
bağlamak için **fail-safe Python facade** yazmak. xurl binary VPS'te YOK (OAuth browser flow
gerektiriyor, VPS'te browser yok) → facade `xurl` binary mevcutsa shell-out eder, yoksa
`NotImplemented` raise eder + runbook link'i verir. **Default OFF** — X API key'leri olmadan
client no-op kalır. M6 içerik onay kuyruğu bu client üzerine inşa edilecek.

## Çıktılar

- [ ] `backend/social/xurl_client.py` — `XurlClient` sınıfı (post, thread, dry_run)
- [ ] `backend/social/xurl_client.py` — flag-gated `_enabled()` (env: `X_API_ENABLED=true`)
- [ ] `backend/social/xurl_client.py` — env schema (`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`)
- [ ] `backend/social/xurl_client.py` — binary discovery (`shutil.which("xurl")` veya `XURL_BIN_PATH`)
- [ ] `backend/tests/test_xurl_client.py` — hermetic unit testler (binary yokken not-implemented, dry-run path, env gating, shell-out mock)
- [ ] `docs/runbooks/xurl-setup.md` — Go install + Twitter app + OAuth PIN flow + VPS caveat + secret hygiene
- [ ] `config.yaml` `notifications.x` şeması (default OFF, canlıya DOKUNULMAZ)

## Acceptance Kriterleri

- [ ] **Fail-safe:** key/flag eksik → `XurlDisabled` raise, hiçbir subprocess çağrısı yok
- [ ] **Binary discovery:** `xurl` PATH'te yoksa `XurlNotInstalled` + runbook URL ile raise
- [ ] **Dry-run:** `--dry-run` flag'i tüm post çağrılarında text'i validate eder, subprocess YAPMAZ
- [ ] **Hermetic testler:** network çağrısı YOK, subprocess `unittest.mock.patch` ile mock'lu
- [ ] **Compliance gate:** post text içinde BANNED_EN_PHRASES / BANNED_TR_PHRASES var mı validate (`content_compliance.py` entegre)
- [ ] **No secrets in logs:** 4 X credential env maskelenir (son 4 char)
- [ ] **CLI entry:** `python -m backend.social.xurl_client post --text "..." --dry-run` çalışır
- [ ] **Trade-path izolasyonu:** `engine/`, `lifecycle.py`, order path'e DOKUNULMAZ (G1)

## Tasarım Kararları

- **xurl binary VPS'e KURULMAZ** — OAuth PIN-based browser flow VPS'te yapılamaz.
  Operatör local macinesinde auth yapar, `~/.xurl` cache'lenir, sonra VPS'e **SSH tunnel** ile veya
  **manual post** yöntemiyle kullanır. Detay runbook §3'te.
- **Facade pattern:** binary varsa shell-out, yoksa `NotImplementedError` + runbook link.
  İleride xurl Python replacement yazılırsa facade aynı kalır (caller-safe).
- **Compliance integration:** `scripts/content_compliance.py` zaten `BANNED_*_PHRASES`
  set'lerini export ediyor. xurl_client bu fonksiyonu import edip post öncesi validate eder
  (DRY — duplicate phrase list yok).
- **Dry-run default:** `XurlClient(..., dry_run=True)` constructor param + CLI `--dry-run`.
  Post çağrısı dry_run=True ise subprocess YAPMAZ, payload'u log'a yazar.

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-18 | IN_PROGRESS | @hermes — P-002 M1 PR: xurl facade + dry-run + runbook. xurl binary VPS'te YOK (OAuth browser VPS'te yapılamaz), facade binary-yokken NotImplemented + runbook link. Default OFF (canlı config DEĞİŞMEDİ, X credentials yok). |
