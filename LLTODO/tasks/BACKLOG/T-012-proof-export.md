# T-012: Public Proof Snapshot Export (proof_export.py)

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** — (UR-003 onayı sonrası başlar)

## Hedef

`state/trade_journal.jsonl`'den yalnız oransal/aggregate metrik üreten, u2algo-site'ın statik servis edeceği `state/proof_snapshot.json` export routine'i yazmak.

## Çıktılar

- [ ] `scripts/routines/proof_export.py` (mevcut `scripts/routines/_base.py` routine kalıbı)
- [ ] Snapshot whitelist şeması: win_rate, profit_factor, max_dd_pct, trade_count, normalize % equity eğrisi, period
- [ ] Privacy testi: snapshot'ta mutlak bakiye / pozisyon büyüklüğü / sembol bazlı USDT alanı YOK
- [ ] Runbook notu: cron kurulumu (`docs/runbooks/routines-cron-setup.md` ek bölüm)

## Acceptance Kriterleri

- [ ] G-P3-1: whitelist dışı alan testi yeşil
- [ ] Bot API'si public'e AÇILMAZ — yayın statik dosya üzerinden
- [ ] Yayın öncesi operatör onayı (G-P3-B4)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W1 — UR-003 bekleniyor |
