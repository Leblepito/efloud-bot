# RUNBOOK: Prod → Master Reconciliation (2026-06-10)

> Hazırlayan: @hermes
> Durum: DRAFT — operatör onayı + deploy penceresi bekliyor
> Son güncelleme: 2026-06-10

---

## 1. Mevcut Durum

| Ortam | Branch/Commit | Açıklama |
|---|---|---|
| **Prod VPS** | `feat/pr1-identity-tokens` @ `ca92ce7` | ⚠️ **CANLI MAINNET** — `EFLOUD_CONFIG_PATH=configs/config.phase2_1k.yaml` → `dry_run: false`, `testnet: false` = GERÇEK ORDER. (Root `/app/config.yaml`'daki `dry_run: true` İNERT default'tur, bot onu KULLANMAZ — Claude review düzeltmesi.) |
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

- [x] Prod bot çalışıyor (⚠️ CANLI MAINNET, dry_run=false — gerçek emir/pozisyon riski var)
- [x] `bebcc8c` patch'i hazır
- [ ] Operatör onayı (ZORUNLU — canlı para)
- [ ] Flat-book penceresi (0 açık pozisyon + 0 açık emir; Binance UI Conditional sekmesinden doğrula)

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

# Önce state backup — DİKKAT: canlı state docker NAMED VOLUME'larda
# (/opt/efloud-bot/state_1k host dizini DEĞİL). Container'dan kopyala:
docker cp efloud-bot:/app/state /tmp/state_backup_$(date +%s)/
docker cp efloud-bot:/app/state_aggressive /tmp/state_aggr_backup_$(date +%s)/ 2>/dev/null || true

# Master'a geç
git fetch origin
git checkout master
git -c safe.directory=/opt/efloud-bot pull origin master

# AUTOSTART=0 → manuel start
# .env.production'da EFLOUD_AUTOSTART=0 olduğundan emin ol

# ⚠️ KOD IMAGE'E BAKED — build OLMADAN up -d ESKİ kodu çalıştırır
docker compose -f docker-compose.prod.yml build efloud-bot

# Recreate (yeni image ile)
docker compose -f docker-compose.prod.yml up -d

# Doğrula
docker logs efloud-bot --tail 50
curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/healthz
```

### Adım 3 — Post-deploy doğrulama

| Check | Komut | Beklenen |
|---|---|---|
| Container UP | `docker ps \| grep efloud` | `Up (running)` |
| healthz | `curl -s -o /dev/null -w "%{http_code}" localhost:8080/healthz` | `200` (bot STARTED ise; idle/breaker-halted → `503` beklenen) |
| Startup log | `docker logs efloud-bot --tail 30` | hata yok |
| dry_run flag | `docker exec efloud-bot grep dry_run /app/configs/config.phase2_1k.yaml` | `false` (⚠️ CANLI — root `/app/config.yaml` İNERT, ona bakma) |
| v2 shadow | `docker exec efloud-bot grep -E "smc_version\|smc_v2_shadow" /app/configs/config.phase2_1k.yaml` | `v2` + `shadow: true` (v1 canlı trade, v2 sadece log) |

---

## 3. Rollback

```bash
cd /opt/efloud-bot
git checkout feat/pr1-identity-tokens
git -c safe.directory=/opt/efloud-bot reset --hard ca92ce7
docker compose -f docker-compose.prod.yml build efloud-bot   # eski koddan image rebuild — şart
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

**Çözüm seçenekleri (Claude review düzeltmesi):**
1. **Reset (tek geçerli yol):** Prod **DB-LESS** (DATABASE_URL yok, file-only StateStore) →
   SQL `UPDATE breaker_state ...` ÇALIŞMAZ. Doğru yol: bot RUNNING iken
   `POST /api/breaker/reset` (login → Secure-cookie'yi manuel `Cookie` header'ı olarak gönder;
   bot idle iken 503 "Bot not running" döner — önce `/api/bot/start`).
2. **Bekle / olduğu gibi bırak:** ⚠️ bot CANLI MAINNET'tir (dry_run=false) — "zaten gerçek
   emir yok" varsayımı YANLIŞ. Breaker OPEN iken davranışı operatörle teyit et.

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
