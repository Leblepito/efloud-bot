# RUNBOOK: Prod → Master Reconciliation (2026-06-10)

> Hazırlayan: @hermes
> Durum: DRAFT — operatör onayı + deploy penceresi bekliyor
> Son güncelleme: 2026-06-10

---

## 1. Mevcut Durum

| Ortam | Branch/Commit | Açıklama |
|---|---|---|
| **Prod VPS** | `feat/pr1-identity-tokens` @ `ca92ce7` | Çalışan bot (dry_run=true, canlı değil) |
| **Master (GitHub)** | `39c2738` (PR #177) | Kanonik kaynak |

### Diff Özeti

```
master'da 11 commit prod'da YOK:
  a4e16b0..39c2738 (PR #172..#177):
  - #172: content pipeline (flags-OFF, default-safe)
  - #173: merged within #172
  - #174: frontend NUMERIC fix (cherry-pick → prod'da zaten var: ca92ce7)
  - #175: entry-slippage atomic (require_confirmation:true, default-safe)
  - #176: gitignore + handoff docs
  - #177: LLTODO scaffolding

prod'da 2 commit master'da YOK:
  - ca92ce7: frontend fix (CHERRY-PICK of #174 → zaten master'da, SKIP)
  - bebcc8c: u2algo token-sync pipeline → BUNU master'a entegre ET
```

**Davranış etkisi:** SIFIR. Tüm #172-#177 değişiklikleri default-safe/flags-OFF.
`bebcc8c` u2algo-site frontend assets + token sync script — core trade logic'e dokunmaz.

---

## 2. Hizalama Planı

### Adım 0 — Ön Koşul

- [x] Prod bot çalışıyor (dry_run=true)
- [x] `bebcc8c` patch'i hazır
- [ ] Operatör onayı
- [ ] Flat-book penceresi (en az 1 saat trade-free zaman)

### Adım 1 — bebcc8c'yi master'a entegre et

```bash
# Operatör lokal makinede:
cd ~/efloud-bot
git fetch origin
git checkout master && git pull origin master     # → 39c2738
git checkout -b feat/token-sync-merge
git am /tmp/i2-bebcc8c-token-sync.patch
git push -u origin feat/token-sync-merge
# PR aç → master'a merge
```

**Dosyalar (3):** `ops/tokens/sync-tokens.py`, `u2algo-site/brand-kit/css/tokens-generated.css`, `u2algo-site/index.html`

### Adım 2 — Prod'u master'a hizala

```bash
# VPS üzerinde (Hermes/operatör):
cd /opt/efloud-bot

# Önce state backup
cp -r state_1k/ /tmp/state_1k_backup_$(date +%s)/

# Master'a geç
git fetch origin
git checkout master
git -c safe.directory=/opt/efloud-bot pull origin master

# AUTOSTART=0 → manuel start
# docker-compose.prod.yml'da AUTOSTART=0 olduğundan emin ol

# Recreate (yeni kodla)
docker compose -f docker-compose.prod.yml up -d

# Doğrula
docker logs efloud-bot --tail 50
curl -s localhost:8080/api/healthz
```

### Adım 3 — Post-deploy doğrulama

| Check | Komut | Beklenen |
|---|---|---|
| Container UP | `docker ps \| grep efloud` | `Up (running)` |
| healthz | `curl -s localhost:8080/api/healthz` | `200 OK` |
| Startup log | `docker logs efloud-bot --tail 30` | `SafeOrchestrator cycle started` |
| dry_run flag | `docker exec efloud-bot grep dry_run /app/config.yaml` | `true` |
| v2 inert | `docker exec efloud-bot grep smc_version /app/config.yaml` | `v1` |

---

## 3. Rollback

```bash
cd /opt/efloud-bot
git checkout feat/pr1-identity-tokens
git -c safe.directory=/opt/efloud-bot reset --hard ca92ce7
docker compose -f docker-compose.prod.yml up -d
```

---

## 4. Risk Değerlendirmesi

| Risk | Olasılık | Etki | Mitigasyon |
|---|---|---|---|
| Config drift | Düşük | Orta | State backup + config.yaml diff öncesi |
| Container start fail | Düşük | Düşük | `docker logs` ile hata ayıklama |
| LLTODO overwrite | YOK | — | LLTODO master'da zaten kanonik, append-only |
| breaker OPEN (healthz 503) | Pre-existing | Düşük | **Operatör kararı.** Prod'da breaker HALTED durumda — db'den reset et veya beklet. Bu reconciliasyon öncesi mevcut, yeni kodla ilgili değil. |
| Token sync script çalışmama | Yok | — | `ops/tokens/sync-tokens.py` manuel çalıştırılan script, bot loop'da değil |

---

## 5. breaker OPEN Durumu

> **⚠️ Pre-existing issue (bu reconciliasyondan bağımsız)**

**Semptom:** healthz 503
**Neden:** Circuit breaker HALTED (daily/weekly limit aşıldı)
**Durum:** Prod'da açık — bot trade üretmiyor

**Çözüm seçenekleri:**
1. **Reset:** `UPDATE breaker_state SET status='READY' WHERE id=(SELECT MAX(id) FROM breaker_state)`
2. **Bekle:** Günlük reset window'da kendi açılır
3. **Olduğu gibi bırak:** Dry-run'da zaten gerçek emir yok

**Karar:** Operatör. Bu runbook dışında.

---

## 6. Sorumluluk Matrisi

| Görev | Sorumlu | Durum |
|---|---|---|
| `bebcc8c` patch hazırlama | @hermes | ✅ DONE |
| Runbook yazma | @hermes | ✅ DONE |
| `bebcc8c` PR + merge | Operatör / Claude | ⬜ BEKLİYOR |
| Prod → master hizalama | Operatör | ⬜ BEKLİYOR |
| Post-deploy doğrulama | Operatör / Hermes | ⬜ BEKLİYOR |
| breaker reset kararı | Operatör | ⬜ BEKLİYOR |
