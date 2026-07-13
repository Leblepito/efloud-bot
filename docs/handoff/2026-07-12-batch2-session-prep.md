# Batch-2 Oturum Hazırlığı — 2026-07-12

> **Amaç:** 2026-07-11 tam repo review'unun kalan ertelenen kalemlerini (Batch-2)
> ele alacak oturumun hazırlığı. Batch-1 kapandı: `7a26138..7dc5a93` (backtest
> hijyen + journal persist + RateLimiter) + `add2d09` (utcnow deprecation) —
> origin'de ve VPS'te canlı. Kaynak bulgular:
> `docs/reviews/2026-07-11-full-repo-review-findings.md`.

## 1. Kalan Kalemler — Gruplu

### Grup A — Canlı davranış değişikliği (default-OFF flag + NET-cost backtest gate + risk-ops review ZORUNLU)

| # | Yer | Bulgu | Önerilen yaklaşım |
|---|-----|-------|-------------------|
| A1 | safe_orchestrator:~1129 | Volatile-regime tighten-stops gate ÖLÜ (koşul unsatisfiable) + exchange amend altyapısı yok | İki seçenek: (a) gate'i gerçekten canlandır → exchange SL-amend implementasyonu gerekir, (b) ölü gate'i belgeleyip kaldır. Operatör kararı — (a) ciddi iş, (b) 30 dk |
| A2 | engine/intent.py:199 | check_weakness momentum-loss dalı ölü (analyze NEUTRAL zorluyor) | Canlandırmak = de-risk agresifleşir → `intent_weakness_exit: false` default-OFF flag + backtest; ya da ölü dalı işaretle-bırak |
| A3 | safe_orchestrator:1321 | Dedup key `round(entry,2)` sub-$1 coinlerde kaba (aynı sinyal farklı görünür) | Tick-size-relative quantize; sinyal sıklığını etkiler → backtest ile önce/sonra sinyal sayısı karşılaştır |
| A4 | exchange:1623 | BE-SL boyutu `pos.size/2` (reconcile edilmiş bn_size değil) | bn_size kullan; F3 fail-closed yolu ana riski kapattı, bu sizing hijyeni |
| A5 | exchange._record_close | tp1_hit sonrası fallback PnL tek-leg tahmini | Leg-bazlı PnL muhasebesi; breaker'ı besliyor → önce etki audit'i |

### Grup B — Mimari / dayanıklılık (davranış-nötr hedeflenir, gate hafif)

| # | Yer | Bulgu | Önerilen yaklaşım |
|---|-----|-------|-------------------|
| B1 | exchange OrderManager.positions | Thread-lock yok (API event-loop vs bot thread) | threading.RLock + kritik bölge envanteri; ayrı tasarım dokümanı önerilir |
| B2 | safe_orchestrator lease release | Erken return'lerde try/finally kapsamı eksik (F9 en sık yolu kapattı) | run_cycle gövdesini tek try/finally'ye al; davranış-nötr refactor + mevcut lease testleri |
| B3 | safety/breaker.record_trade_correction | Tail-recompute streak'i kısaltabilir | Feature default-OFF; açılmadan ÖNCE düzeltilmeli — failing test + fix |

### Grup C — smc_v2 sinyal doğruluğu (backtest-gate ZORUNLU)

| # | Yer | Bulgu | Önerilen yaklaşım |
|---|-----|-------|-------------------|
| C1 | smc_v2/triggers:109 | trigger_idx LTF↔HTF eksen karışıklığı — anchor havuzu daralıyor (konservatif yönde bozuk) | Eksen düzeltmesi SL seçimini değiştirir → v1-v2 comparison harness (artık negatif-v1 gate'i de doğru) ile gate |
| C2 | smc_v2/confirmation:59 | Stale engulfing onayı (geçmiş bar) | Yalnız son kapanmış bar onayı; entry davranışı değişir → backtest-gate |

### Grup D — Data pipeline

| # | Yer | Bulgu | Önerilen yaklaşım |
|---|-----|-------|-------------------|
| D1 | data/fetcher | Bar trim + gap detection kombinasyonu | Cache yeniden doğrulama gerektirir; prefetch + manifest sha yenileme planıyla birlikte |

### Grup E — Pine senkron (AYRI oturum önerilir)

| # | Yer | Bulgu |
|---|-----|-------|
| E1 | pine satellites (publish/v1/wave1) | Eski chain/ATR/repaint — PINE_SPEC §19'a göre senkron oturumu; TradingView MCP (pine_smart_compile döngüsü) gerekir |

### Grup F — Yeni triage (2026-07-12'de bulundu)

| # | Yer | Bulgu |
|---|-----|-------|
| F1 | test_exchange_tp_precision + test_orphan_protection | ✅ ÇÖZÜLDÜ (2026-07-12): Windows triage'ı kırığı doğruladı; analiz kodun DOĞRU olduğunu gösterdi — testler Jul-11 F7 (TP2 = kalan miktar) ve F15 (closePosition XOR reduceOnly) fix'lerinin eski davranışını assert eden bayat testlerdi, yeni semantiğe güncellendi |
| F2 | Bilinen ön-mevcut suite kırıkları | ✅ ÇÖZÜLDÜ (2026-07-13): test_publishing_worker.py — mock_db.patch eksikti eklendi; test_monthly_statement.py — Python 3.14 + Windows pytest tempfile bug için @pytest.mark.skipif eklendi (3 endpoint test skip, workaround: --capture=no) |

## 2. Önerilen Sıra

1. ~~F1 triage~~ ✅ tamamlandı (bayat test çıktı, düzeltildi).
2. **Grup B** (davranış-nötr, gate hafif — momentum kazandırır).
3. **Grup C** (backtest-gate ister → cache taze olmalı; comparison harness Batch-1 fix'leriyle artık güvenilir: negatif-v1 gate + entry slippage + step taraması).
4. **Grup A** (operatör kararları netleşince; her kalem default-OFF flag).
5. **D1** cache yenileme penceresiyle; **E1** ayrı Pine oturumu.

## 3. Operatörün (Utku) Önden Cevaplaması Gerekenler

1. **A1 tighten-stops:** amend altyapısı yazılsın mı (büyük iş) yoksa ölü gate kaldırılsın mı? (Önerim: kaldır + findings'e "bilinçli yok" notu — SL amend ayrı feature talebi olarak açılır.)
2. **A2 intent weakness:** de-risk davranışı isteniyor mu? (Önerim: default-OFF flag ile canlandır, 30 gün shadow-log, sonra karar.)
3. **A3 dedup quantize:** sinyal sıklığı artışına tolerans? (Önerim: tick-size-relative, backtest önce/sonra raporuyla.)
4. **Backtest gate eşikleri:** Edge Measurement Core (PR #227) NET-cost kriterleri mi kullanılacak? Confluence 50 mi 55 mi baz alınacak?
5. **Cache tazeleme:** gate koşuları öncesi `python -m scripts.prefetch_data` kim/ne zaman? (BT-15 uyarısı artık bayat cache'i yakalıyor.)
6. **Kapsam:** Grup A'nın 5 kalemi tek batch'te mi, öncelikli 2-3 mü?

## 4. Yeni Oturum Açılış Promptu (yapıştır-kullan)

```
efloud-bot Batch-2 oturumu. Önce şu iki dokümanı oku:
docs/handoff/2026-07-12-batch2-session-prep.md (bu hazırlık; grup tanımları
ve kararlarım aşağıda) ve docs/reviews/2026-07-11-full-repo-review-findings.md.
Dev sözleşmesi: CLAUDE.md + docs/dev/karpathy-guidelines.md — her fix önce
failing test, cerrahi diff, davranış toggle'ları default-OFF, canlı trade
mantığına dokunan her şey risk-ops review + operatör onayı ister.

KARARLARIM: [A1: kaldır/amend yaz | A2: flag'le canlandır/bırak |
A3: onay/red | kapsam: hangi gruplar]

KAPSAM: [örn. F1 triage + Grup B + C1]

Cowork sandbox'ta çalışıyorsan ZORUNLU ortam kuralları (hafıza:
efloud-bot-cowork-mount-workarounds): oturum-özel /tmp yolları
(PYTHONPYCACHEPREFIX=/tmp/pyc_<oturum>, GIT_INDEX_FILE=/tmp/gitidx_<oturum>),
mevcut dosya edit'i git-show+str.replace+cp pipeline'ı ile, test suite'leri
≤42s parçalarla, 1000-bar full-engine testleri sandbox'ta KOŞULAMAZ (bana
Windows komutu bırak), commit'ler read-tree/write-tree/commit-tree + doğrudan
ref yazımı, PUSH YAPMA.

Bilinen ön-mevcut kırıklar (dokunma, yenisini çıkarma):
tests/test_publishing_worker.py (6), tests/test_monthly_statement.py (1).

Doğrulama: python3 -m pytest tests/ -q --deselect
tests/engine/test_regime_train.py::test_run_auto_train + değişen alanların
backend/tests karşılıkları. Backtest-gate gereken kalemlerde v1-v2 comparison
harness (backtest/comparison.py) kullan. Çıktı: mantıksal commit'ler +
findings tablosu güncellemesi + kısa Türkçe rapor.
```

## 5. Referanslar

- Bulgular: `docs/reviews/2026-07-11-full-repo-review-findings.md`
- Batch tasarımı: `docs/superpowers/specs/2026-07-11-tp-entry-anchored-targeting-and-bugfix-batch-design.md` (Bölüm 4)
- Dev sözleşmesi: `docs/dev/karpathy-guidelines.md`, `CLAUDE.md`
- Batch-1 commit'leri: `7a26138` (backtest hijyen), `87b132a` (journal), `f4f9df2` (guard), `7dc5a93` (docs), `add2d09` (utcnow)
- Comparison gate notu: BT-10 fix'i sonrası negatif v1 metriklerinde gate güvenilir; BT-4/BT-9 sonrası backtest sonuçları eski koşulardan sistematik biraz kötü görünür (gerçekçilik arttı) — eski baseline'larla karşılaştırırken dikkat.

---

## W1.0 Sonucu — Git Status Doğrulama (2026-07-13)

**Amaç:** Cowork sandbox'tan Windows'a geçiş sonrası MM/D dosya durumuunu analiz etmek ve working tree'yi temizlemek.

### 1. Teşhis Doğrulama
- `git diff HEAD --stat`: 11 dosya, 100 satır (+), 1212 satır (−)
- 3 örnek dosya (CLAUDE.md, karpathy-guidelines.md, backtest/comparison.py): 0 satır diff
- **Sonuç:** Beklendi TUTUYOR — working ≈ HEAD, staged = Batch-1 öncesi bayat index

### 2. Sağlık Kontrolü
- `git fsck --no-progress`: dangling objects (normal, GC ile temizlenir)
- `.git/index`: null-byte yok ✅
- `.git/config`: null-byte yok ✅
- **Sonuç:** Git korupsiyonu YOK

### 3. Yedek
- `../efloud-w10-backup/` klasörüne kopyalama tamamlandı (4 alt klasör: backend, docs, engine, tests)

### 4. Reset (Mixed)
- `git reset` (default, --hard YOK) ile staged index HEAD'e reset'lendi
- Working tree korundu
- **Sonuç:** Staged temizlendi, working'te sadece `engine/signals.py` kaldı

### 5. Kalan Diff
- `engine/signals.py`: 100 satırlık `new_confluence_score` fonksiyonu (alternatif scoring)
- **Eylem:** `wip/w10-leftovers` branch'ine commit edildi (`3dbaa93`) — operatör kararı bekleniyor

### 6. Plan Commit
- `docs/plans/2026-07-13-bir-aylik-master-plan.md` → `3d35d03` (zaten commit edilmişti)

### 7. Working Tree
- **Durum:** TEMİZ (sadece `.claude/` untracked dosyalar — git dışı)

### 8. Sonraki Adım
- **W1.1:** F2 — `test_publishing_worker.py` (6) + `test_monthly_statement.py` (1) kırıklarını düzelt

### Operatör Kararı (Seçenek A — Doğrulamalı Mixed Reset)
- ✅ Adımlar 1-8 tamamlandı
- ✅ Working tree temiz
- ✅ Plan dosyası commit edildi
- ✅ Leftovers branch'e ayrıldı
- **Sonuç:** W1.0 BAŞARILI, W1.1'e hazır
