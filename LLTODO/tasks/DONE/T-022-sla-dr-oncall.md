# T-022: SLA + Disaster Recovery + On-Call Dokümanları

**Epic:** P-003
**Claimed by:** @claude (2026-06-11, T-023/T-024 emsali — R2: IN_PROGRESS'te T-020 var)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** T-020 (backup — DR'nin temeli)

## Hedef

Satış öncesi sözleşmesel zemin: uptime taahhüdü, olay müdahale süreleri, felaket kurtarma prosedürleri. Bugün hiçbiri yok — "kurumsal firma" iddiasının dokümantasyon önkoşulu.

## Çıktılar

- [x] `docs/SLA.md` — **iki katman ayrımıyla** (UR-003 "proof ≠ ürün" bulgusu): müşteri taahhütleri (destek ≤2 iş günü, TV erişim ≤2 iş günü, site %99) sözleşmesel; bot uptime/RPO/RTO İÇ hedef. `trading_active`'e bilinçli hedef YOK ("safety suspension üründür")
- [x] `docs/runbooks/disaster-recovery.md` — 3 senaryo adım adım (S2 = 2026-05-15 gerçek rebuild deneyimi; S2 adım 1 = ÖNCE pozisyon güvenliği)
- [x] `docs/runbooks/on-call-playbook.md` — P1/P2/P3 + müdahale akışı + post-incident şablonu + aylık hazırlık kontrolleri
- [x] Üç ayda bir tatbikat takvimi (DR §5 log + tabletop kaydı)
- [x] **BONUS:** `docs/runbooks/breaker-reset.md` — tabletop'un bulduğu boşluk (iki doc var olmayan runbook'a referans veriyordu)

## Acceptance Kriterleri

- [x] **G-P3-B2 paketine girer** — SLA.md başlığında sign-off statüsü açık; fiyat+refund ile birlikte operatöre sunulur
- [x] **Tabletop tatbikatı: PASS** (live-ops-sentinel, 2 tur — 1. tur 2 BLOCKING + 3 advisory buldu, fix'ler sonrası 2. tur temiz; kayıt DR §5)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W-R — ilk satıştan önce zorunlu |
| 2026-06-11 | IMPL | @claude — 3 doküman + tabletop 1. tur FAIL (2 BLOCKING: yok-runbook referansı → breaker-reset.md yazıldı; AUTOSTART kod-default uyarısı; eksik komutlar) → fix → 2. tur PASS |
| 2026-06-11 | ✅ DONE | Bu PR merge'üyle. G-P3-B2 operatör paketi hazır (SLA + fiyat + refund). Sıradaki gerçek drill: T-020 VPS kurulumu sonrası (G-P3-6) |
