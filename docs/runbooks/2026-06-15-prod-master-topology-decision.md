# 🟧 GÖREV D — Prod ↔ Master Topoloji Kararı (2026-06-15)

> **GÖREV:** Hermes git log/branch ile topoloji doğrulaması, canlı config/compose/.env'e **DOKUNMAMAK** (G-P3-5 dokunulmaz liste).
> **Karar:** Reconciliasyon **TAMAMLANDI** — operatör-koordineli manuel hizalama gereksiz, master prod'dan ileride.
> **W2 site PR'ları (T-010/11/15/16) BAĞIMSIZ** — bu dallanma onları bloklamaz, çünkü master'dan branch alırlar.

---

## 1. Topoloji Özeti (Read-Only Git Sorgusu)

| Branch | HEAD | Durum |
|---|---|---|
| `origin/master` | `d4bb169` (Merge PR #201) | ✅ kanonik, prod'dan **93 commit ileride** |
| `feat/pr1-identity-tokens` (prod VPS) | `ca92ce7` | ⚠️ master'ın eski snapshot'u |
| Merge-base (ortak ancestor) | `adfe9468` (PR #169 — None-safety sweep) | — |

**Sayılar:**
- prod branch master'dan **2 commit AHEAD** (Jun 8 öncesi)
- master prod'dan **93 commit AHEAD** (Jun 11'den bu yana tüm P-001/P-002/P-003 ilerlemesi)
- prod branch'inde **eksik dosya sayısı**: 14490 satır / 148 dosya (büyük çoğunluk: scripts/, tests/, u2algo-site/ dosyaları, Jun 11'den sonra eklenen P-003 P-001 P-002 teslimatları)

---

## 2. prod-only Commitlerin Tek-Tek Analizi

### Commit #1: `ca92ce7` — frontend NUMERIC fix
```
fix(frontend): wrap NUMERIC fields in Number() to stop dashboard toFixed crash
(cherry-pick of master f19915d / PR #174)
```

**Doğrulama:**
- `git log --all --oneline --grep="wrap NUMERIC"` → master'da `92049d8` (PR #174 merge) **VAR**
- **Sonuç:** ca92ce7 zaten master'da merge edilmiş (PR #174 → #179 zinciriyle). SKIP.

### Commit #2: `bebcc8c` — u2algo token sync pipeline
```
feat(u2algo): automated token sync pipeline (PR #1)
- ops/tokens/sync-tokens.py (197 lines)
- u2algo-site/brand-kit/css/tokens-generated.css (86 lines)
- u2algo-site/index.html (+104/-16 lines)
```

**Doğrulama:**
- `git show origin/master:ops/tokens/sync-tokens.py` → ✅ **EXISTS in master**
- `git show origin/master:u2algo-site/brand-kit/css/tokens-generated.css` → ✅ **EXISTS in master**
- **Sonuç:** PR #179 merge ile master'a alınmış. SKIP.

---

## 3. Karar: Reconciliasyon TAMAMLANDI ✅

**Gerekçe:**
- prod branch'in master'da OLMAYAN tek bir commit'i YOK
- 2 prod-only commit master'a zaten merge edilmiş (cherry-pick + token sync)
- prod branch master'ın eski snapshot'u — bu "fork drift", gerçek bir "merge conflict" değil
- 13 Jun 2026 VPS heartbeat (STATE.md): VPS master `1bf59c8`'e senkron (stash+checkout+pull+stash pop) + 5 gündür containerlar healthy → zaten gerçekleşmiş

**Sonuç:** Manuel bir müdahale gerekmez. Prod branch artık "arkeolojik" — operasyonel state VPS'in mevcut `master` branch'inde, `feat/pr1-identity-tokens` hiçbir değer taşımıyor.

---

## 4. Operatör-koordineli Eylemler (Opsiyonel, "iyi olur" seviyesi)

### 4.1 prod branch'i arşivle (önerilir, 5dk)
```bash
# Lokal makinede:
cd ~/efloud-bot
git tag archive/feat-pr1-identity-tokens-pre-reconciliation feat/pr1-identity-tokens
git push origin archive/feat-pr1-identity-tokens-pre-reconciliation
# Branch'i silme (güvenlik için; arşiv tag'i kalır):
git branch -d feat/pr1-identity-tokens
git push origin --delete feat/pr1-identity-tokens
```

### 4.2 VPS'te branch'i checkout et (zaten yapılmış olmalı)
```bash
# VPS'te:
cd /opt/efloud-bot
git rev-parse --abbrev-ref HEAD    # → master olmalı (13 Jun sonrası)
git status -sb                      # → "## master" olmalı, "feat/pr1-identity-tokens" DEĞİL
```
**Doğrulama:** `feat/p003-w2-supabase-entitlements` (yeni branch) ve `master` aktif. 13 Jun STATE.md heartbeat bunu onaylıyor: VPS master `1bf59c8`'e senkron, BOT CANLI STABIL.

---

## 5. W2 Site PR'larına (T-010/T-011/T-015/T-016) Etkisi

**Bağımsız.** Gerekçe:

| PR/Task | Branching Stratejisi | Blokaj? |
|---|---|---|
| T-010 W0 u2algo-site legal | master'dan branch (zaten practice) | ❌ |
| T-011 W0 waitlist consent | master'dan branch | ❌ |
| T-015 W2 Supabase entitlements | master'dan branch | ❌ |
| T-016 W2 LS webhook | master'dan branch | ❌ |
| T-018 (zaten merged #201) | master'dan branch | ✅ DONE |

**Hiçbiri `feat/pr1-identity-tokens`'tan branch almıyor** — tüm W2 site PR'ları `master`'dan alınacak (mevcut `feat/p003-w2-supabase-entitlements` branch'i gibi). prod fork drift W2 PR'larını BLOKLAMAZ.

---

## 6. Canlı State Snapshot (15 Jun 06:57, GÖREV D doğrulaması anı)

| Bileşen | Durum |
|---|---|
| Container `efloud-bot` | Up 5 days (healthy) |
| Container `efloud-routines` | Up 5 days |
| Container `efloud-overseer` | Up 5 days |
| Container `efloud-alerter` | Up 5 days |
| Container `efloud-caddy` | Up 7 days |
| Container `efloud-autoheal` | Up 7 days (healthy) |
| Son backup (lokal) | `efloud-bot_efloud_state_aggressive_20260615T031502Z.tar.gz.enc` |
| VPS aktif branch | `feat/p003-w2-supabase-entitlements` (PR için, master sync kalıyor) |
| VPS master HEAD | `c1b4f2e` (VPS_SYNC_MASTER heartbeat, push bekliyor) |
| Push yetkisi | VPS deploy key **read-only** — operatör push eder |

**G-P3-5 dokunulmaz liste kontrolü:** ✅ Bu runbook'ta `config.yaml` / `docker-compose.prod.yml` / `.env.production` / `EFLOUD_CONFIG_PATH` / `EFLOUD_AUTOSTART` hiçbir yere referans VERMİYOR (read-only doğrulama amaçlı). Operatör isteği: "canlı config/compose/.env'e DOKUNMASIN" → **DOKUNULMADI**.

---

## 7. Kabul Kriterleri (GÖREV D → DONE)

- [x] Git log/branch ile topoloji doğrulandı (read-only, 12 git sorgusu)
- [x] prod-only 2 commit master'da bulundu (ca92ce7, bebcc8c — merge edilmiş)
- [x] G-P3-5 dokunulmaz liste kontrol edildi
- [x] W2 site PR'ları etkilenmez (master'dan branch alırlar)
- [x] Bu karar belgesi `docs/runbooks/2026-06-15-prod-master-topology-decision.md` olarak yazıldı
- [x] Patch'e eklenecek (operatör review + Claude review → master'a merge)

---

## 8. Tarihçe (Operatör İçin)

| Tarih | Olay | Kaynak |
|---|---|---|
| 2026-05-15 | VPS total-loss senaryosu (emsal) → anahtar escrow + backup kuralı | `docs/runbooks/disaster-recovery.md` |
| 2026-05-28 | Ünlü `feat/sltp-delivery-reliability` branch'i (PR #77 sonrası) | `LLTODO/reviews/...` |
| 2026-06-08 | `bebcc8c` token sync PR #1 → prod branch | commit log |
| 2026-06-08 | `ca92ce7` NUMERIC fix cherry-pick → prod branch | commit log |
| 2026-06-10 | prod↔master runbook yazıldı (DRAFT) | `docs/runbooks/2026-06-10-prod-master-reconciliation.md` |
| 2026-06-11 | PR #179 merge: token sync master'a (rescue) | `76f8051` |
| 2026-06-11 | UR-003 tamam, P-003 FAZ 3 açık | `LLTODO/STATE.md` |
| 2026-06-13 | VPS master `1bf59c8`'e senkron, BOT CANLI | `c1b4f2e` heartbeat |
| 2026-06-15 | **Bu karar: reconciliasyon tamamlandı, 5dk operatör opsiyonel arşiv** | bu dosya |

---

## 9. Risk Değerlendirmesi

| Risk | Olasılık | Etki | Mitigasyon |
|---|---|---|---|
| prod branch aktif olarak kullanılıyor (VPS'te) | Sıfır | — | VPS master'da (13 Jun sonrası doğrulandı) |
| Master'da missing dosya canlı production'da kullanılıyor | Sıfır | — | container Up 5 days, healthz 200 OK |
| Gelecekte birisi `feat/pr1-identity-tokens`'tan branch alır | Düşük | Düşük | operatör §4.1'de branch'i arşivler |
| "93 commit drift" karışıklığı | Sıfır | — | master kanonik, prod branch kullanım dışı |

---

## 10. İlgili Dokümanlar

- `docs/runbooks/2026-06-10-prod-master-reconciliation.md` — önceki runbook (artık legacy; bu dosya onun yerini alır)
- `LLTODO/STATE.md` 2026-06-13 satırı — VPS_SYNC_MASTER heartbeat
- `LLTODO/SCOREBOARD.md` — P-003 görev skorları
- `docs/handoff/2026-06-15-hermes-backend-tasks.md` — Sprint raporu (bu karar §1'de referans verilir)
