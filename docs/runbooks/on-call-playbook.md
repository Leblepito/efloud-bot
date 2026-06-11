# Runbook: On-Call Playbook (T-022 / P-003 W-R)

> **Amaç:** Olay önem dereceleri, müdahale hedefleri, eskalasyon ve post-incident disiplini.
> Tek-operatör gerçekliğine göre yazıldı (eskalasyon zinciri = alerter → operatör Telegram);
> ekip büyürse §4 güncellenir.

## 1. Önem Dereceleri

### P1 — ANINDA müdahale (para/pozisyon riski)

| Tetik | Kaynak |
|---|---|
| Binance'te TP/SL'siz ("bare") pozisyon | alerter / dashboard / bağımsız ccxt (2026-05-14 emsali) |
| Bot down + açık pozisyon var | healthz 503 sürekli + positions kontrolü |
| Breaker HALT etmesi gerekirken etmiyor / beklenmeyen emir akışı | loglar + Binance emir geçmişi |
| Backup FAILED + aynı gün state değişikliği riski | `🔴 efloud backup FAILED` alarmı |
| Secret sızıntısı şüphesi | gitleaks / herhangi bir kanal |

**Müdahale hedefi: ≤ 15 dk onay (acknowledge), ≤ 1 saat kontrol altına alma.**
İlk refleks her zaman: **pozisyon güvenliği** (bağımsız kanaldan Binance kontrolü) →
sonra sistem onarımı. Bot'u düşünmeden önce parayı düşün.

### P2 — Aynı gün müdahale

| Tetik | Not |
|---|---|
| healthz `suspended` (breaker_halted / crash_loop) | Tasarım gereği durmuş — restart ÇÖZMEZ. `breaker_halted` → `docs/runbooks/breaker-reset.md`; `crash_loop_suspended` → `docs/runbooks/crash-loop-recovery.md` |
| Alerter/overseer down (gözlerimiz kapalı) | heartbeat bayat: `docker exec efloud-bot cat /app/state/alerter_heartbeat.json` — ts > 5dk eskiyse alerter down |
| u2algo-site down / webhook 5xx (W2 sonrası satış kaybı) | T-021 monitörü |
| Backup başarısız ama state riski düşük | ertesi cron öncesi düzelt |

### P3 — Planlı işle

Dokümantasyon, kozmetik, lint/CI iyileştirmeleri, tekil flaky test.

## 2. Müdahale Akışı (her olayda)

1. **Acknowledge** — Telegram alarmına yanıt/not (dedup pencereleri sessizliği maskelemesin).
2. **Sınıflandır** (P1/P2/P3) — emin değilsen bir üst sınıf.
3. **Stabilize et** — P1'de önce pozisyon güvenliği; "geçici çözüm + sonra kök neden" meşrudur.
4. **Kaydet** — zaman çizelgesi notu (tek satır bile olsa) olay anında tutulur.
5. **Kapat** — post-incident şablonu (§3) 48 saat içinde; aksiyonlar LLTODO kartına döner.

## 3. Post-Incident Şablonu

```markdown
# Incident: <kısa başlık> — <tarih>
**Sınıf:** P1/P2/P3 · **Süre:** tespit → çözüm
**Etki:** (pozisyon/para etkisi AYRI satır — sıfırsa "sıfır" yaz)
## Zaman çizelgesi
## Kök neden
## Ne iyi çalıştı / Ne çalışmadı
## Aksiyonlar (her biri LLTODO kartı veya runbook PR'ı olur)
```

Kayıt yeri: `docs/handoff/` (incident-raporu olarak) + memory/wrapup akışı.
Emsaller: 2026-05-14 (bare positions + breaker halt), 2026-05-15 (VPS wipe → rebuild).

## 4. Eskalasyon

| Seviye | Kim | Kanal |
|---|---|---|
| L1 | Operatör (Utku) | alerter Telegram (30s healthz poll + log kuralları) |
| L2 | Claude/Hermes oturumu | operatör açar; teşhis + runbook yürütme |
| Dış | Hetzner/Railway/Supabase destek | altyapı arızalarında |

**Kural hatırlatmaları:** mainnet'e davranış değişikliği = PR + onay (olay anında bile
hotfix branch'le); destructive op = açık fiil onayı; secrets yalnız VPS/Railway.

## 5. Hazırlık Kontrolleri (aylık, 10 dk)

- [ ] Alerter'a test alarmı düşür (kanal canlı mı?)
- [ ] `last_backup_status.json` ok + en son `.enc` tarihi < 48h
- [ ] Bağımsız ccxt ile pozisyon listesi çek (kanal hazır mı?)
- [ ] ESCROW anahtarı password manager'da erişilebilir mi?
