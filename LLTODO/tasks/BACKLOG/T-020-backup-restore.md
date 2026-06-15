# T-020: State Backup Otomasyonu + Restore Runbook

**Epic:** P-003
**Claimed by:** @claude (2026-06-11, parked — GÖREV F operatör)
**Tahmini süre:** 2-3 gün
**Bağımlılık:** GÖREV F (backup hedefi provizyonu — Hermes); **pre-UR-exempt** (canlı bot için ticaretten bağımsız KRİTİK; UR-003 öncesi başlayabilir)

## Hedef

Prod'daki korumasız named volume'ların (`efloud_state`, `efloud_state_1k`, `efloud_state_aggressive` — `trade_journal.jsonl` dahil) günlük şifreli off-VPS yedeğini almak ve test edilmiş restore prosedürü kurmak. Bugün backup stratejisi SIFIR — disk kaybı = track-record + breaker/pozisyon state kaybı.

## Çıktılar

- [ ] `deploy/backup/backup_state.sh` — read-only snapshot: `docker run --rm -v efloud_state:/src:ro ... tar czf` (canlı volume'a ASLA yazma)
- [ ] Şifreli off-VPS hedef (Hetzner Storage Box / S3 — GÖREV F kararı)
- [ ] **Anahtar escrow (UR-003 düzeltmesi):** şifreleme anahtarı VPS'te + **operatör password-manager'ında
      offline escrow kopyası ZORUNLU** — DR'nin ana senaryosu VPS total-loss (2026-05-15 rebuild emsali)
      anahtarı veriyle birlikte yok ederse şifreli backup açılamaz. "Repo'ya asla" kuralı değişmez
- [ ] Restore runbook'una tutarlılık notu: trade_journal.jsonl append-only — canlı yazım sırasındaki
      snapshot'ta kesik (torn) son satır tolere edilir
- [ ] VPS lokal staging için disk-doluluk/retention hijyeni (disk full → journal yazımına dolaylı etki)
- [ ] Cron entry + başarısızlıkta alerter'a Telegram alarmı
- [ ] `docs/runbooks/backup-restore.md` — RTO/RPO hedefleri + scratch-volume restore tatbikatı adımları
- [ ] İlk restore tatbikatı SCRATCH volume'da koşulup PASS olarak loglanır

## Acceptance Kriterleri

- [ ] Snapshot read-only mount ile alınır; canlı bot davranışı etkilenmez (blast-radius sıfır)
- [ ] Restore-to-live operatör-gated (runbook'ta açık uyarı)
- [ ] **G-P3-6 enabler:** ilk public proof yayını (G-P3-B4) bu tatbikat PASS olmadan açılamaz

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W-R — pre-UR-exempt, GÖREV F ile koordineli |
| 2026-06-11 | IN_PROGRESS | @claude claim — `deploy/backup/{backup_state.sh,restore_state.sh}` + `docs/runbooks/backup-restore.md` (escrow zorunlu, :ro mount, drill-default restore, live-restore çift kilit). VPS kurulum+cron+ilk drill = GÖREV F sonrası Hermes/operatör |
