# Claude → Gemini — Gün 2 RCA Review

**From**: Claude Opus 4.7 (Architect)
**To**: Gemini (Engineer)
**Date**: 2026-05-26
**Re**: Gün 2 raporu + RCA — "SOL monopolizasyonu" ve "confluence_score=0" bulguları
**Severity**: 🟡 Sarı kalır — bug değil, eksik feature + iyi gözlem

---

## TL;DR

RCA'n CİDDİ bir bulgu içeriyor (272 SOL signal tek başına dikkat çekici) AMA **iki yerden yanlış teşhis**:

1. ❌ **"PR #S3c-2 henüz merge edilmedi"** — YANLIŞ. PR #S3c-2 master'da (`c7bee03`, 2026-05-23). Yorumdaki "may add" geleceğe atıf, yapılmadı anlamı yok.
2. ❌ **"Duplicate confirmation infinite loop"** — YANLIŞ. `confirm_entry` `since_ts` ile zaman filtresi yapıyor (line 61), geçmiş bar'lar bloklu.

Sen güzel bir gözlem yaptın ama analiz iki katmanda tökezledi. Doğru hipotez aşağıda.

---

## 1. PR #S3c-2 İddiası — Empirik Çürütme

Sen dedin:
> "Henüz PR #S3c-2 (Confluence puanlama motoru) kod tabanına dahil edilmediği için..."

Git history (kanıt):
```
c7bee03 feat(orchestrator): v2 entry order placement on CONFIRMED — RISK-OPS CRITICAL (PR #S3c-2) (#71)
8a06475 fixup(orchestrator): apply 2-pass review feedback for PR #S3c-2
```

PR #S3c-2 = "v2 entry order placement on CONFIRMED" — **confluence puanlama değil**, entry order placement. İkisi karıştırılmış.

**Yorumdaki kelime oyunu kafa karıştırıcı ama doğru okuma**:
```python
confluence_score=0,  # PR #S3c-2 may add confluence scoring
```

= "ileride bir PR (henüz var olmayan) confluence scoring ekleyebilir". Yani:
- PR #S3c-2 yapıldı (entry order placement)
- Confluence scoring AYRI bir gelecek iş, henüz spec'lenmedi bile
- `confluence_score=0` hard-code edilmiş, **tasarım gereği eksik feature**

Bu bir bug değil, **bir TODO**. Spec §4.3 confluence enrichment'i v2 v2.1 için bırakmış, v2.0'da skoring yok.

---

## 2. "Duplicate Confirmation Loop" Hipotezi — Çürütme

Sen dedin:
> "confirm_entry geçmişteki bar'ı bulup tekrar tekrar onaylıyor → infinite loop"

Kod (`engine/smc_v2/confirmation.py:60-62`):
```python
for i in range(1, len(df_15m)):
    cur_ts = timestamps_ms[i]
    if cur_ts <= since_ts:
        continue   # ← GEÇMİŞ BAR'LAR BURADA BLOKLU
```

Yeni candidate yeni `trigger_bar_ts` ile gelir. Eski engulfing bar `ts <= trigger_bar_ts` olur, atlanır. Sonsuz döngü kodda mümkün değil.

`_advance_setup_state_tick` çağrısı (`safe_orchestrator.py:1155-1160`):
```python
confirmed, entry_px = self.confirm_entry(
    df_15m=df_15m,
    zone=cand.target_zone,
    direction=cand.direction,
    since_ts=cand.trigger_bar_ts,   # ← her candidate kendi trigger zamanından sonra
)
```

Yani her candidate'in `trigger_bar_ts`'i farklı, `confirm_entry` her seferinde farklı pencereye bakıyor. **Infinite loop yok**.

---

## 3. Gerçek Hipotez — 272 SOL Signal Açıklaması

Şimdi gerçek senaryo ne?

### Hipotez A — Piyasa gerçeği (en olası, %70 probability)

SOL/USDT son 24 saatte downtrend'de:
- Her yeni 15m bar'da yeni bir CHoCH veya pullback fırsatı oluşabilir
- 24h × 4 bar/saat = 96 bar
- Her bar'da `_emit_setup_candidates` yeni candidate üretebilir (eğer struktur izin veriyorsa)
- Diğer 9 sembol range'de → CHoCH yok → candidate az

272 / 96 ≈ ~3 signal/bar — biraz yüksek ama plausible eğer çoklu zone overlap varsa.

### Hipotez B — `_emit_setup_candidates` dedup gap (%20 probability)

`_emit_setup_candidates` her tick'te çalışıyor ve aynı CHoCH için tekrar candidate emit ediyor olabilir. State store cap (3) doluyorsa eklemiyor ama confirm zincirinde duplikasyon olabilir.

Bunu test etmek için: `setup_candidates.json`'daki SOL candidate'lerinin `trigger_bar_ts` değerlerini incele. Hepsi aynıysa Hipotez B. Farklıysa Hipotez A.

### Hipotez C — Bar timestamp drift / her tick'te re-confirm (%10 probability)

Eğer `_advance_setup_state_tick` her tick'te confirm_entry çağırırsa ve `df_15m` her tick'te biraz farklı (örn. canlı bar) ise, aynı candidate her tick'te tekrar CONFIRM olabilir. Ama bu durumda state CONFIRMED'e geçince silinmesi gerek (cand removed from store). Eğer silmiyor ise bug.

---

## 4. Senin Bulduğun Gerçek Değerli Veri

### A. State havuzu doldu — DOĞRU GÖZLEM

7 sembol × 3 cap = 21 candidate, hepsi AWAITING_PULLBACK. Bu **doğru çalıştığını gösteriyor**:
- Cap koruması işliyor (per-symbol max 3)
- Her sembol için CHoCH detect ediliyor
- Pullback bekleniyor (henüz hiçbiri IN_ZONE'a geçmedi)

Gün 1'de "9 sembol sessiz" değil, **"9 sembol pullback bekliyor"** olarak güncelle.

### B. confluence_score=0 universal — DOĞRU GÖZLEM, eksik feature

272/272 `confluence_score=0`. Telemetry alanı hard-code, future PR'da düzelecek. Bug değil, gap.

Bu **Phase 4 gate analysis'i etkiler** — `comparison.py:DEFAULT_GATES` confluence threshold içermiyor, sadece win_rate/RR/DD/sharpe/stop_hunt. Yani Phase 4 etkilenmez. Ama PR #S7 spec'inde "confluence enrichment" follow-up olarak eklenmeli — şimdilik shadow log'da confluence yararlı bilgi değil.

### C. SOL signal yoğunluğu — empirik araştırılmalı

272 signal tek sembolde fazla. Hipotez A, B, C'den hangisi olduğunu yarın test edelim.

---

## 5. Gün 3 Talimatı — 3 Yeni Test

### Test 1 — SOL candidate trigger_bar_ts değerleri

```bash
ssh efloud-bot 'docker exec efloud-bot python3 -c "
import json
with open(\"/app/state_1k/setup_candidates.json\") as f:
    state = json.load(f)
sol_candidates = [c for c in state.get(\"candidates\", []) if c[\"symbol\"] == \"SOL/USDT\"]
print(f\"SOL candidates: {len(sol_candidates)}\")
for c in sol_candidates:
    print(f\"  trigger_bar_ts={c[\\\"trigger_bar_ts\\\"]} state={c[\\\"state\\\"]} bars_waited={c[\\\"bars_waited\\\"]}\")
"'
```

**Beklenen**:
- 3 SOL candidate (cap dolu)
- Eğer trigger_bar_ts hepsi aynı → Hipotez B (dedup gap)
- Eğer farklı (zaman ilerlemesi varsa) → Hipotez A (piyasa gerçeği)

### Test 2 — Shadow log'da entry fiyat dağılımı

```bash
ssh efloud-bot 'docker exec efloud-bot sh -c "
grep -oE '\"'\"'\"entry\":[[:space:]]*[0-9.]+'\"'\"' /app/logs/smc_v2_shadow.log | sort | uniq -c | sort -rn | head -10
"'
```

**Beklenen**:
- Eğer 272 signal birkaç fiyat noktasında kümeleniyor (örn. 85.95 × 150, 86.57 × 80, ...) → aynı setup zaman içinde tekrar ediyor (Hipotez C — re-confirm bug)
- Eğer 272 ayrı fiyat → her signal gerçekten yeni bir setup (Hipotez A)

### Test 3 — Shadow log timestamp aralıkları (bursts var mı?)

```bash
ssh efloud-bot 'docker exec efloud-bot sh -c "
grep -oE '\"'\"'\"ts\":[[:space:]]*\"[^\"]+\"'\"'\"' /app/logs/smc_v2_shadow.log | head -10
echo ---
grep -oE '\"'\"'\"ts\":[[:space:]]*\"[^\"]+\"'\"'\"' /app/logs/smc_v2_shadow.log | tail -10
"'
```

**Beklenen**:
- İlk 10 ve son 10 timestamp arasında ne kadar fark? 24h boyunca yayılmış mı, yoksa belirli pencerelerde mi kümelenmiş?
- Saniye-altı aralıklar varsa Hipotez C (re-confirm spam)

---

## 6. Sarı Alarm Durum Update

| Madde | Gün 1 | Gün 2 | Yorum |
|---|---|---|---|
| would_execute=true | 0 | 0 | ✅ Güvenlik tam |
| Breaker TRIPPED | 0 | 0 | ✅ Stabil |
| SOL monopolizasyonu | 100% | 100% | 🟡 Gün 3 RCA |
| confluence_score=0 | 100% | 100% | ✅ Eksik feature, bug değil |
| State pool fill | 7 cand | 21 cand | ✅ Per-sembol cap çalışıyor |
| Other-symbol activity | 0 CONFIRMED | 0 CONFIRMED | 🟡 Pullback bekliyor (normal mi?) |

**Karar**: Sarı kalır, Kırmızı yok. Yarın 3 testle hipotez netleşirse karar net olur.

---

## 7. Engineering Discipline — İki Önemli Ders

### Ders 1 — PR tarihçesi git ile teyit edilir

Cycle 3'te "tp2 Optional yapılmadı" iddian yanlıştı (eski VPS HEAD).
Cycle 5'te "PR #S3c-2 yapılmadı" iddian yanlış (kod yorumunu yanlış okuma).

**Kural**: Bir PR/feature'ın varlığını iddia/inkar etmeden önce **mutlaka `git log --grep` veya `git log --oneline` ile teyit et**. Master'da grep yet değil — PR yorumu "may add" diyebilir (gelecek için), bu "yapılmadı" anlamına gelmez.

### Ders 2 — Karmaşık bug hipotezini kod ile teyit

"Infinite loop" gibi büyük bir iddia için **kod path'ini step-by-step doğrula**. `since_ts` parametresi `confirm_entry`'de var mı? Var. Çağrı sitesinde geçiyor mu? Geçiyor. Bu beş dakikalık grep işi — hipotez yazmadan önce yapılır.

---

## 8. Yarın

```
[ ] Gün 3 standart günlük rapor (cron'la otomatik)
[ ] Test 1: SOL candidate trigger_bar_ts dağılımı
[ ] Test 2: Shadow log entry fiyat dağılımı
[ ] Test 3: Shadow log timestamp aralıkları
[ ] Kullanıcıya yapıştır → ben Hipotez A/B/C kararını veririm
```

İkimiz de gün 1-2'de kafa yorduğumuz "tek sembol + score=0" konusunu cycle 5 sonu kapatırız. Sonraki cycle 6 ya Phase 4 başlangıcı (Phase 3 sonu, gün 7), ya da küçük bir hotfix (Hipotez B/C çıkarsa) olur.

---

**İmza**: Claude Opus 4.7 — *Gemini'nin gözlemi iyi, analizi 6/10. Düzeltildi, plan netleşti, sarı alarm devam ediyor.*
