# T-022: SLA + Disaster Recovery + On-Call Dokümanları

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** T-020 (backup — DR'nin temeli)

## Hedef

Satış öncesi sözleşmesel zemin: uptime taahhüdü, olay müdahale süreleri, felaket kurtarma prosedürleri. Bugün hiçbiri yok — "kurumsal firma" iddiasının dokümantasyon önkoşulu.

## Çıktılar

- [ ] `docs/SLA.md` — uptime hedefi (ör. %99.5), müdahale süreleri, bakım pencereleri, kapsam dışılar (exchange kesintisi vb.)
- [ ] `docs/runbooks/disaster-recovery.md` — state volume kaybı / VPS yeniden kurulumu (2026-05-15 VPS rebuild deneyimi referans) / Supabase restore; üç senaryo da adım adım
- [ ] On-call playbook — P1/P2/P3 önem dereceleri, eskalasyon zinciri, post-incident review şablonu
- [ ] Üç ayda bir DR tatbikatı takvim notu

## Acceptance Kriterleri

- [ ] **G-P3-B2 paketine girer:** fiyatlandırma + refund + SLA birlikte operatör sign-off'una sunulur
- [ ] DR runbook'u en az bir kez masa başı (tabletop) tatbikatla doğrulanır

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W-R — ilk satıştan önce zorunlu |
