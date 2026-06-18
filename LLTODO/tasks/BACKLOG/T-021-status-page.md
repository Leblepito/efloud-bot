# T-021: Public Status Page + External Uptime Monitor

**Epic:** P-003
**Claimed by:** — (as-code kısmı @hermes 2026-06-18 hazır; BACKLOG kalır — operatör canlı-aktivasyon gated, T-020 emsali)
**Tahmini süre:** 1 gün
**Bağımlılık:** T-024 (healthz kontratı), T-014 (uptime alanı), GÖREV E (sağlayıcı seçimi — Hermes/operatör)

## Hedef

Müşterilerin servis durumunu kendi kendine kontrol edebileceği public status page + harici uptime monitörü kurmak. Bugün müşteri dashboard'a login olmadan servisin ayakta olup olmadığını göremez.

## Çıktılar

- [ ] Harici uptime monitör (UptimeRobot/BetterStack — GÖREV E kararı) `/healthz` probe'u
- [ ] **Probe healthz JSON `status` alanını parse ETMELİ** — HTTP 200 + `status:"suspended"` = trading durdu ama servis ayakta (`suspended` ≠ up olarak raporlanmalı; T-024 kontratı)
- [ ] Public status sayfası (sağlayıcının hosted page'i veya u2algo-site `/status`)
- [ ] Incident log alanı (geriye dönük, insan yazımı)

## Acceptance Kriterleri

- [ ] Breaker HALT senaryosunda status page "degraded/suspended" gösterir, "operational" DEĞİL
- [ ] Public görünürlük kapsamı operatör onaylı (G-P3-B4 ile aynı paket)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W-R — T-024 + GÖREV E sonrası |
| 2026-06-18 | BACKLOG (as-code DONE) | @hermes — **as-code kısmı DONE** (görev BACKLOG kalır, T-020 emsali: kod hazır, operatör-gated): monitör + status page tanımı kod oldu. `ops/uptimerobot/monitors.yaml` + idempotent `scripts/setup_uptimerobot.py` (create-or-update, key env'den, `--dry-run`) + 20 test (API mock, ağ yok) + runbook `docs/runbooks/uptimerobot-as-code.md`. Kalan: operatör hesap aç + API key + `python scripts/setup_uptimerobot.py` çalıştır + public URL'i STATE'e ekle → o zaman LIVE/DONE. |

## As-Code Teslimat (2026-06-18, @hermes)

Monitör tanımı dashboard'da elle değil repo'da kod olarak (drift yok):

| Dosya | Rol |
|---|---|
| `ops/uptimerobot/monitors.yaml` | Monitör + status page tanımı (source of truth) |
| `scripts/setup_uptimerobot.py` | Idempotent uygulayıcı: friendly_name eşleştirme → editMonitor/newMonitor; `UPTIMEROBOT_API_KEY` env; `--dry-run` (key gerektirmez) |
| `tests/scripts/test_setup_uptimerobot.py` | 20 birim test — UptimeRobot API mock'lu, ağ erişimi YOK |
| `docs/runbooks/uptimerobot-as-code.md` | Operatör adımları: hesap → API key → env → çalıştır → doğrula |

Kritik kısıt korundu: keyword monitör (`keyword_type=2`, `"status":"ok"` yoksa DOWN)
→ breaker HALT iken "operational" yalanı söylenmez (healthz-contract.md).

**Operatöre kalan canlı-aktivasyon (kod değil):** hesap açma + API key + opsiyonel
Telegram alert contact ID + script çalıştırma + public status URL'ini STATE.md'ye ekleme.
