# Cycle 4 Errata & Phase 2 Complete

**Date**: 2026-05-25
**From**: Claude Opus 4.7 (Architect)
**To**: Hermes (gelecek operatörler) + Gemini (engineer)
**Status**: 🟢 Phase 2 shadow activation **SUCCESSFUL**

---

## TL;DR

Phase 2 shadow mode aktif. 151 shadow signal first 10 minutes, 0 order leak, v1 paralel çalışıyor, breaker temiz. **Phase 3 (7 günlük gözlem) başladı.**

Önceki handoff dökümanlarında **iki kritik hata** vardı, bu döküman bunları düzeltiyor.

---

## 1. Errata — Önceki Handoff Doc'larındaki Hatalar

### Hata 1 — `config.yaml` vs `configs/config.phase2_1k.yaml`

**Yanlış (önceki handoff doc'larında)**:
> "config.yaml engine bloğunu güncelle..."
> "ssh efloud-bot 'grep -A5 \"^engine:\" /opt/efloud-bot/config.yaml'"

**Doğru**:
Production bot (`backend/bot_runner.py`, FastAPI mode) `EFLOUD_CONFIG_PATH` env değişkenini okur. `.env.production` bunu `configs/config.phase2_1k.yaml`'a ayarlar. Yani:

- ✅ **Production config**: `configs/config.phase2_1k.yaml`
- ❌ **CLI-only default**: `config.yaml` (root) — `main.py` çağrılırsa kullanılır, FastAPI mode okumaz

Gelecek tüm production config değişikliklerinde `configs/config.phase2_1k.yaml` editlenecek.

**Etkilenen handoff dosyaları** (audit trail için referans, içerikleri historicaldır, edit edilmedi):
- `docs/handoff/claude_to_hermes_v2_shadow_readiness.md` Bölüm 5
- `docs/handoff/v2_runtime_inventory.md` (config tablosu)
- `HERMES.md` Bölüm 6 (Deploy Senaryosu Adım 2)

Bu errata söz konusu satırların override'ıdır.

### Hata 2 — PR #S6 wiring gap (cycle 4'te bulundu + düzeltildi)

PR #S6 (`cdd01c5`) `_build_setup_state_store`'u `main.py`'a ekledi ama `backend/bot_runner.py`'a wiring atlandı. FastAPI production mode v2'yi **hiç aktive edemiyordu**.

**Hotfix**: PR #81 (`5dbcff9`) — `backend/bot_runner.py`'a wiring + regression test eklendi.

Sonuç: Cycle 4'ten önce v2'yi config ile aktive etmenin **hiçbir yolu yoktu**. Şimdi var.

---

## 2. Phase 2 Activation — Final Confirmation

**Activation log (timestamp UTC)**:
```
2026-05-25 08:28:13 | efloud.runner | 🟢 SMC v2 active: SetupStateStore initialized (max_pending_per_symbol=3)
```

**10 dk sonra empirik metrikler**:

| Metric | Beklenen | Gerçekleşen | Verdict |
|---|---|---|---|
| Shadow log dosyası | Var olmalı | `/app/logs/smc_v2_shadow.log` (151 satır) | ✅ |
| `would_execute=true` count | **0 (KRİTİK)** | 0 | ✅ |
| `AWAITING_PULLBACK` setup count | 5+ | 7 (TRX/USDT, BCH/USDT, SOL/USDT) | ✅ |
| `IN_ZONE` count | 0+ | 0 (henüz pullback olmadı) | ✅ |
| `CONFIRMED` count | 0+ | 0 | ✅ |
| v1 paralel sinyal | 1+ | 104 | ✅ |
| Breaker TRIPPED count | 0 | 0 | ✅ |
| ERROR / Traceback | 0 | 0 | ✅ |

**Örnek shadow signal** (SOL/USDT SHORT, OTE_RETRACE):
```json
{
  "ts": "2026-05-25T08:35:12.482Z",
  "symbol": "SOL/USDT",
  "direction": "SHORT",
  "entry": 86.57,
  "sl": 88.45285,
  "tp1": 83.18086999999998,
  "entry_setup_source": "OTE_RETRACE",
  "would_execute": false,
  "reason": "SHADOW_MODE"
}
```

---

## 3. Phase 3 — 7-Day Observation Protocol

Phase 3 başladı (2026-05-25 08:28 UTC). 7 calendar gün VE en az 5,000 toplam satır birikene kadar gözlem.

### Günlük rapor (Gemini → kullanıcı → Claude)

Her gün TR saatiyle 09:00-10:00 arası şu komutu koş, çıktıyı kullanıcıya yapıştır:

```bash
ssh efloud-bot 'docker exec efloud-bot sh -c "
TODAY=\$(date -u +%Y-%m-%d)
echo === TOTAL ===
wc -l /app/logs/smc_v2_shadow.log
echo === TODAY ===
grep -c \"\\\"ts\\\":[[:space:]]*\\\"\$TODAY\" /app/logs/smc_v2_shadow.log || echo 0
echo === SYMBOLS TODAY ===
grep \"\\\"ts\\\":[[:space:]]*\\\"\$TODAY\" /app/logs/smc_v2_shadow.log | grep -oE '\"symbol\":[[:space:]]*\"[^\"]+\"' | sort | uniq -c | sort -rn
echo === DIRECTION TODAY ===
grep \"\\\"ts\\\":[[:space:]]*\\\"\$TODAY\" /app/logs/smc_v2_shadow.log | grep -oE '\"direction\":[[:space:]]*\"[^\"]+\"' | sort | uniq -c
echo === SETUP SOURCE TODAY ===
grep \"\\\"ts\\\":[[:space:]]*\\\"\$TODAY\" /app/logs/smc_v2_shadow.log | grep -oE '\"entry_setup_source\":[[:space:]]*\"[^\"]+\"' | sort | uniq -c
echo === DISK ===
du -sh /app/logs/
echo === KRITIK would_execute true ===
grep -c '\"would_execute\":[[:space:]]*true' /app/logs/smc_v2_shadow.log || echo 0
"'
```

### Anomali tetikleri (varsa hemen kullanıcı → Claude)

| Metric | Eşik | Aksiyon |
|---|---|---|
| `would_execute=true` count | **>0** | `docker compose stop` HEMEN → Claude RCA |
| Günlük toplam satır | <50 veya >5000 | Claude'a raporla, threshold tuning |
| Disk usage `/app/logs/` | >20 MB | logrotate PR spec iste |
| Long/Short bias | >85% tek yöne | Trend bias problem, Claude analizi |
| Bilinmeyen `entry_setup_source` enum | enum dışı değer | Claude'a hex dump yolla |
| `bars_to_pullback > 8` | >0 | Timeout enforcement bug, Claude RCA |

### Cycle ritmi (Phase 3 boyunca)

- **Günlük**: Gemini sağlık özetini kullanıcıya verir, sorun yoksa kısa "OK" — Claude'a paslamaya gerek yok
- **3 günde bir**: Tam özet + 10 örnek shadow signal → Claude analiz (sinyal kalitesi, dağılım)
- **Phase 3 sonu (gün 7)**: Tam shadow log dump + Phase 4 baseline backtest hazırlığı

---

## 4. Phase 4 Pre-Reqs (gelecek 7 gün boyunca paralel)

Phase 3 ile paralel hazırlanabilir:

### 4a. OHLCV cache prefetch (lokal veya VPS)

```bash
# 200 günlük cache (Phase 4 için 180 gün backtest periyodu)
python -m scripts.prefetch_data \
  --symbols BTC/USDT,ETH/USDT \
  --timeframes 5m,15m,1h,4h,1d \
  --days 200
```

### 4b. Binance trade history (kullanıcı, hâlâ açık istek)

16.05.2026 → bugüne kadar:
- Order History: filled order sayısı + sembol dağılımı
- Position History: kapalı pozisyon sayısı + win/loss
- Income History: net realized PnL

Bunu kullanıcı UI'dan çıkarıp paylaşır — Claude bot iç state ile cross-check eder.

### 4c. NotebookLM auth (Gemini, opsiyonel)

`& "$env:USERPROFILE\.notebooklm_venv\Scripts\notebooklm.exe" login` — Phase 3 sonu wrap-up için lazım.

---

## 5. Phase 4 — Baseline Backtest (Phase 3 sonu)

Phase 3'ten sonra koşulur, **şimdi değil**.

```bash
python -m backtest.cli compare \
  --symbols BTC/USDT,ETH/USDT \
  --period-days 180 \
  --config configs/config.phase2_1k.yaml \
  --balance 2000
```

Çıktı: `reports/backtests/2026-06-01_compare_2sym_180d_<hash>/comparison.json` (yaklaşık)

Karar kuralı (PR #S7 spec'i tetikleme):
- TÜM 5 gate `pass` veya `warn` → PR #S7 hazırlanır
- HERHANGİ 1 gate `hard_reject` → PR #S7 bloklu, RCA gerek
- 3+ gate `warn` → PR #S7 Phase 1 sembol sayısı 2'den 1'e indirilir (sadece BTC)

---

## 6. Gemini Engineering Protocol (Cycle 3 + 4 dersleri)

Cycle 3'te transkripsiyon hatası, cycle 4'te "boş çıktı = normal" rasyonalleştirmesi, ayrıca otomatize kullanıcı aksiyonu — bunlardan çıkan kalıcı kurallar:

### Kural 1 — Empirik doğrulama
Beklenen string YOKSA "muhtemelen normal" deme. `grep -c` ile rakamsal teyit yap, alternatif hipotezi test et (kod source, container içi config, vs.).

### Kural 2 — Kritik string'ler için çift doğrulama
Sembol, breaker reason, exception, would_execute → her birinde `wc -l + grep -c` ile rakamsal sayım ekle. Transkripsiyon hatası riskini sıfırla.

### Kural 3 — Kullanıcı aksiyonu otomatize etmek
Bir aksiyonun "kullanıcı yapacak" diye işaretlendiyse, otomatize etmek istesen bile ÖNCE sor. Sebep + öneri formatında: "X sebebi ile API çağrısı ben yapabilirim, ister misiniz?"

### Kural 4 — Config dosyası referansları
`config.yaml` (root) ≠ `configs/config.phase2_1k.yaml` (production). Daima `EFLOUD_CONFIG_PATH` env değişkenini kontrol et, doğru dosyayı edit et.

### Kural 5 — Wiring tamamlama
Yeni feature için `main.py` (CLI) + `backend/bot_runner.py` (FastAPI) **iki entry point** kontrol edilir. Eksik wiring regression test ile yakalanır.

---

## 7. PR'lar

Bu cycle 4 wrap-up için tek atomik PR (bu döküman + config kalıcılaştırma):

```
docs(handoff): cycle 4 errata + configs/config.phase2_1k.yaml engine block
```

İçerik:
1. `docs/handoff/cycle4_errata_and_phase2_complete.md` (yeni — bu doc)
2. `configs/config.phase2_1k.yaml` (engine block kalıcı eklendi)

Sonra: Hermes deploy etmeden bu config edit production'a YANSIMAZ (VPS'te zaten manuel edit edildi, repo ile sync için ileride bir recreate gerekiyor — şimdilik fonksiyonel sonuç eşit, repo ile VPS arasında drift var ama davranış aynı).

---

**İmza**: Claude Opus 4.7 (Architect) — *Phase 2 başarısı kayıt altında. Phase 3 başladı (7 gün gözlem). Top sende — Gemini günlük raporları üretmeye başlayabilir.*
