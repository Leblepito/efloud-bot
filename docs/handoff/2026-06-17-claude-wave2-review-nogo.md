# Wave-2 Yeni-Edge Önerisi — Claude Review Yanıtı

**Tarih:** 2026-06-17
**Hazırlayan:** 🔵 Claude (Opus 4.8) — cross-model reconcile/review authority
**Durum:** `inceleme_tamamlandı`
**Verdict:** 🔴 **NO-GO → DROP** (falsifikasyon koşuldu §6: OOS pooled PF 1.165, 2/5 net+ → tavan yetersiz, Pine Wave-2 redesign DROP, indicator-only ship final ürün)
**İncelenen:** `docs/handoff/2026-06-16-gemini-wave2-research.md` (👑 Gemini SMR, Track 2 Faz 0)
**Yöntem:** İki bağımsız uzman reviewer (quant-strategy-analyst + smc-strategy-reviewer) ayrı ayrı dağıtıldı → **ikisi de bağımsız olarak DO-NOT-PROCEED'e yakınsadı.** Bu doküman o iki incelemenin sentezidir.

---

## 1. Özet

Öneri *araştırma belgesi olarak* iyi yazılmış ve mimari düşünce kalitesi yüksek. Ancak *bir yatırım/efor tezi olarak* repo'daki kanıtla çelişiyor. Wave-2 tam-redesign'a şu haliyle yeşil ışık yakmak, 4 turda yaşanan FAIL döngüsünün 5. turunu öngörülebilir kılar. Aşağıdaki 4 bulgu kanıt-temellidir (dosya:satır referanslı, doğrulanabilir).

---

## 2. Kritik Bulgular (kanıt-temelli)

### Bulgu 1 — "Yeni-edge"lerin çoğu zaten engine'de var; geri kalanı kaynak-doğruluk sapması

Repo'da `grep` ile doğrulandı:

| Önerilen edge | Engine'de durumu | Kanıt |
|---|---|---|
| **SFP (Edge 2)** | ✅ ZATEN VAR | `engine/smc.py:260` `sfps()`; confluence'ta `has_sfp` +10 (`engine/confluence.py:40`) |
| **OTE / Premium-Discount** | ✅ ZATEN VAR | `engine/smc.py:296` `ote()`; confluence'ta `in_ote` +10 |
| **Liquidity pools** | ✅ ZATEN VAR | `engine/smc.py:318` `liquidity_pools()` |
| **IDM / Inducement (Edge 1)** | ❌ YOK | `inducement\|idm` → tüm `engine/` ağacında 0 eşleşme |
| **Session / Killzone / Judas (Edge 3)** | ❌ YOK | `session\|killzone\|judas\|asian` → 0 eşleşme |
| **PDH/PDL, PWH/PWL (Edge 4)** | ❌ YOK | `PDH\|PDL\|previous_day` → 0 eşleşme |

**Sonuç:** SFP/OTE yeni alfa değil — mevcut konseptin yeniden-etiketlenmesi. IDM/session/PDH-PDL ise engine'de hiç yok → Python'da backtest edilmemiş **yeni icat**. Bu, `CLAUDE.md` "Python kaynak mantığını DEĞİŞTİRME, sadece oku ve referans al" kuralını ve `pine/PINE_SPEC.md` parite kuralını ihlal eder. Wave-2 bu haliyle bir *Pine port'u* değil, *doğrulanmamış yeni bir strateji*.

### Bulgu 2 — Kök neden teşhisi yanlış; yanlış katman tedavi ediliyor

Wave-1 strateji'nin asıl FAIL nedeni **entry mekanizması değil**, sinyal **trigger**'ının düşürülmesidir:

- Canlı engine sinyali **CHoCH/BOS yapı-kırılımı** + HTF/MTF bias hizası ile tetikler (`engine/signals.py:381-406`).
- Wave-1 Pine port bunu **"1h EMA20 slope bias + OB confluence"** ile değiştirdi (`WAVE1_SPEC.md` §3c: *"Wave 1 için EMA20 yeterli. Wave 2'de tam CHoCH/BOS yapısı eklenecek."*).
- Gate raporları (`LLTODO/reports/REPORT-T-003-gate-run-{2,3,4-prelim}.md`) tam bu sinyal-kaynağı zayıflığını suçluyor.

Wave-2 ise *entry-kalite filtresi* (IDM/SFP/session sweep ön-koşulları) ekliyor. Bu, kök sinyal-kaynağını adreslemez; üstelik her zorunlu filtre trade uzayını daraltarak round-1/round-6'da yaşanan **frekans çöküşünü** (15-30 trade, istatistiksel anlamsız) tekrar tetikler. Round-6b zaten OTE+FVG ekledi → edge yine negatif (PF 0.66-0.84).

> **Asıl iş**, önerinin §3'üne gömülü ama vurgulanmamış: **CHoCH/BOS trigger'ını Pine'a geri getirmek.** "Yeni-edge" eklemek değil.

### Bulgu 3 — Gate'ler kendi tavanından yüksek (mantıksal çelişki)

| Metrik | Wave-2 gate (§6b) | Canlı engine gerçeği | Wave-1 en iyi (round-4) |
|---|---|---|---|
| PF | ≥1.5 (OOS) | ~1.15 | 1.44 (marjinal, fill %41) |
| Sharpe | **≥1.8** | mütevazı (~0.3-0.6 tahmini) | round-5'te negatif |
| MaxDD | ≤%8 | — | round-2 ≤%2.6 |
| Min R:R | ≥1.8 *tüm* trade | — | (tasarım kısıtı, gate değil) |

Mükemmel bir port bile = engine edge'i = **PF ~1.15** → Wave-2'nin kendi **PF≥1.5** gate'ini geçemez. **Sharpe≥1.8** kripto perp 15m intraday SMC için pratikte ulaşılamaz bir eşiktir (çoğu profesyonel CTA'yı eler). Yani: ya gate ulaşılamaz (Wave-2 yine FAIL) ya da geçilirse curve-fit kanıtı. Gate'in tezi kendini çürütüyor. Ayrıca "min R:R≥1.8 tüm trade'lerde zorunlu" bir validasyon gate'i değil tasarım kısıtıdır — realized R:R tüm trade'lerde zorlanamaz.

### Bulgu 4 — RE10045 ölçek dersi göz ardı edilmiş

`WAVE1_SPEC.md` §9b'nin somut dersi: Wave-1 indicator **yalnızca 1 HTF `request.security` + 5 array** ile bile RE10045 runtime hatasına çarptı → çözüm için **tüm UDF'ler kaldırıldı, script tamamen inline'a indirildi VE kapsam küçültüldü** (çok-adaylı engine-TP drop edildi). Bulgu: hata *tam-script ölçeğinde* UDF+collection etkileşimine bağlı; "tüm çizimler kaldırıldı → hâlâ RE10045" yani hata **hesaplamada, çizimde değil.**

Wave-2 ise ölçeği büyütüyor: **4 TF `request.security` (Daily/4h/1h/15m) + IDM/SFP/session/PDH-PDL detektörleri + ~7 array.** Önerilen mitigation (`max_boxes_back=100`/`max_labels_back=100`/garbage-collection) **yanlış katmanı** hedefliyor — bunlar *çizim* belleğini yönetir, RE10045 ise hesaplamada. Güçlü öngörü: Wave-2 tek-script + tamamen-inline aynı duvara daha sert çarpar; çarpmamak için o kadar kapsam kısaltılır ki "tam MTF akış geri getirme" hedefi anlamsızlaşır.

**Ek (repaint):** §3.2'deki `request.security(sym, "240", close[1])` kalıbı repaint'i garanti etmez ve yanlıştır. Kanonik repaint-güvenli kalıp: `request.security(sym, tf, expr, lookahead=barmerge.lookahead_off)` + sonucu chart-TF'de `[1]` ile geciktirmek (HTF expr içine `close[1]` gömmek değil). 4h'de BOS/CHoCH + 1h CHoCH türetmek HTF-içi pivot/struct gerektirir — repaint'in en zor alanı ve §3 bunu hiç ele almıyor. Repaint riski Wave-1'e göre belirgin artıyor.

---

## 3. Net Tavsiye

1. **Pine tam-redesign'a girme.** Tavan (engine PF~1.15) Wave-2'nin kendi gate'ini bile geçmiyor.
2. **Indicator-only ship'i koru** — `pine/u2algo/wave1_signals.pine` v1.2.1 (commit `f179153`, master'da, dual-review APPROVE, repaint-temiz). Lead-magnet değeri görsel SMC tespitinde; teslim edildi, risksiz.
3. Premium-strateji iddiasını ancak aşağıdaki ucuz falsifikasyon PASS ederse yeniden aç.

---

## 4. Revize Şartları (NO-GO → PROCEED-WITH-REVISIONS ön koşulları)

Wave-2 devam edecekse, **kodlamadan önce** şu 4 şart zorunludur:

1. **ÖNCE Python falsifikasyonu (en kritik, en ucuz).** Pine'da değil, canlı engine'de doğrula — gerçek edge orada, RE10045 yok.
   - Koş: canlı `engine/signals.py` + `engine/confluence.py` (CHoCH/BOS trigger dahil), mevcut backtest harness (`backtest/engine.py`, PR #205 fix'li) ile **5 sembol × ≥6 ay, walk-forward IS/OOS split.**
   - **Falsifiye eden eşik:** engine'in TAM mantığı OOS'ta **PF ≥1.30 ve ≥4/5 sembolde net-pozitif** üretemezse → Pine redesign **KESİNLİKLE DROP** (tavan zaten yetersiz). Bu test ~1 gün; redesign ~haftalar.

2. **Kaynak-doğruluk.** IDM/session/PDH-PDL Pine'a girmeden önce **engine'e** (Python kaynak-doğruluk katmanına) eklenip Python backtest'inde edge kanıtlanmalı. Aksi halde port değil icat olur; confluence floor'u (PINE_SPEC §A.2 = 55) semantik olarak boşalır.

3. **RE10045'i hipotez değil deney olarak ele al.** Track 2'nin İLK işi: en küçük 4-TF iskeletini (sadece `request.security` × 4 + 2 array, sinyal yok) TV'de derleyip **RUNTIME render testinden** geçirmek. Bu "Faz 0 kapısı" geçilmeden hiçbir edge kodlanmasın. Geçmezse 4-TF tek-script ölü doğmuştur → çok-script/çok-indicator mimarisi veya kapsam küçültme.

4. **Confluence matrisini engine ile hizala.** Mevcut engine ağırlıkları: bias +25 / MTF CHoCH +20 / FVG +15 / OB +10 / OTE +10 / SFP +10 / zone +5 / deviation +5 (eşik 55). Yeni faktör eklenecekse engine'de karşılığı oluşturulup toplam yeniden normalize edilmeli. Default barajı gerekçesiz **80**'e çekme (frekansı öldürür + likidite-sweep faktörlerini çift-sayar: bir London-open Asian-low sweep aynı anda SFP+IDM+session+PDL olabilir → tek mikroyapı olayından ~65 puan).

---

## 5. Korunan / Risksiz Olan

- ✅ Indicator-only ship (`wave1_signals.pine` v1.2.1) — master'da, dokunulmuyor.
- ✅ Bu review hiçbir kod değiştirmedi; öneri dosyası da değiştirilmedi (sadece bu yanıt + §6 eklendi).

---

## 6. Falsifikasyon Sonuçları — Python Engine OOS Walk-Forward (2026-06-17) ✅ KOŞULDU

§4.1'deki ucuz falsifikasyon adımı **uygulandı**: Pine'a hiç dokunmadan, canlı engine'in gerçek edge tavanı Python backtest harness'ında (`backtest/engine.py` → `SafeOrchestrator`, yani CHoCH/BOS dahil tam canlı mantık) ölçüldü.

### 6a. Yöntem
- **Harness:** `python -m scripts.wave2_falsification` (yeni). Her sembol tam yıl (2025-05-15 → 2026-05-14) continuous koşuldu → tam HTF context, split sınırında warmup truncation yok. Trade'ler **simüle entry-zamanına** göre IS/OOS partition'a ayrıldı.
- **Walk-forward split:** IS = 2025-05-15 → 11-15 (6 ay), OOS = 2025-11-15 → 2026-05-14 (6 ay).
- **Config:** `configs/config.phase2_1k.yaml` (prod-aktif) — `smc_version=v2` (shadow zorla OFF → sim'de execute; prod v2'yi shadow loglar, v1 execute eder), `min_confluence=50` (prod-80'den **daha cömert**, frekans lehine), `min_rr=1.8`. **Commission 0.04%** (Binance USD-M taker, round-trip netlenmiş). Funding/slippage = 0 (modellenmedi — eklenince PF yalnızca **düşer**).
- **Sembol:** BTC, ETH, SOL, BNB, XRP (5 core). 5 sembol paralel proseslerde, ~16 dk wall-time.

> **Bulunan + düzeltilen bug (harness):** `engine/lifecycle.py:339` `open_position` → `opened_at = datetime.utcnow()` (wall-clock). Canlıda doğru ama backtest zaman-analizinde her trade'i "bugün"e damgalar → ilk denemede TÜM trade'ler yanlışlıkla OOS'a düştü. `backtest/engine.py`'a **additive** fix: `sim_open_ts`/`sim_close_ts`'ten her trade'e `sim_opened_at`/`sim_closed_at` damgalandı (trade mantığına dokunulmadı). Partition bu alana çevrildi. Bu, [[entry_slippage_initiative]]'deki data-quality dersinin tekrarını önledi.

### 6b. Sonuçlar (gerçek IS/OOS, commission-net)

| Sembol | Toplam | IS_n | IS_PF | IS_net$ | OOS_n | OOS_PF | OOS_WR | OOS_net$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 191 | 87 | 1.494 | +66.4 | 104 | **1.55** | 51.9% | +111.76 |
| ETH | 187 | 90 | 1.053 | +15.1 | 97 | 0.94 | 41.2% | −20.92 |
| SOL | 13 | 13 | 0.635 | −17.4 | **0** | — | — | 0 |
| BNB | 141 | 120 | **1.713** | +196.4 | 21 | **0.548** | 28.6% | −38.88 |
| XRP | 132 | 82 | 0.846 | −51.9 | 50 | **1.445** | 44.0% | +83.75 |
| **POOLED** | **664** | 392 | **1.193** | +208.6 | 272 | **1.165** | — | +135.71 |
| | | net+ **3/5** | | | | net+ **2/5** | | |

### 6c. Kapı Değerlendirmesi → 🔴 FAIL (kesin)

| Kriter | Eşik | OOS Sonuç | Durum |
|---|---|---|---|
| Pooled PF | ≥ 1.30 | **1.165** | ❌ FAIL |
| Net-pozitif sembol | ≥ 4/5 | **2/5** (BTC, XRP) | ❌ FAIL |

**Hem IS hem OOS barı geçemiyor** (IS pooled PF 1.193 / 3-of-5; OOS 1.165 / 2-of-5). Engine'in gerçek edge tavanı ~PF 1.17-1.19 — bu reviewer'ların PF~1.15 tahminini ve [[efloud_state]]'deki "engine edge'i bile PF1.15 mütevazı" notunu **doğruluyor.**

### 6d. En Kritik Bulgu — IS↔OOS Kararsızlığı (overfit/rejim-bağımlılık)
Sağlam bir edge, split boyunca işaretini korur. Burada per-sembol PF **işaret değiştiriyor**:
- **BNB:** IS PF **1.713** (in-sample EN İYİ) → OOS **0.548** (out-of-sample EN KÖTÜ). Çarpıcı dejenerasyon.
- **XRP:** IS **0.846** (kaybeden) → OOS **1.445** (kazanan). Tam ters.
- **SOL:** tüm yılda **13 trade**, OOS'ta **0** → frekans çöküşü, istatistiksel olarak anlamsız.
- Sadece **BTC** tutarlı (IS 1.49 → OOS 1.55). 5 sembolden 1'inde kalıcı edge ≠ portföy edge'i.

Bu inversion, edge'in kalıcı bir sinyal değil **rejim-bağımlı gürültü** olduğunu gösteriyor — Wave-1 STRATEGY'nin 6 turda neden FAIL ettiğinin Python-tarafı kanıtı.

### 6e. Sonuç
Falsifikasyon, §4.1'in "DROP" koşulunu **tetikledi**: engine tam canlı mantığıyla, cömert ayarlarla (conf=50, funding/slippage yok), 6-ay gerçek OOS holdout'ta **PF≥1.30 + ≥4/5 net-pozitif üretemedi.**

→ **Pine Wave-2 tam-redesign DROP edilir** (tavan kanıtlanmış biçimde yetersiz; Pine port en iyi ihtimalle bu tavanı yakalar, RE10045 maliyetiyle).
→ **Indicator-only ship final premium-üstü-olmayan ürün** olarak kalır.
→ Premium-strateji iddiası **kapatılır** — ancak engine'in KENDİSİ (Pine değil) yeniden tasarlanıp Python OOS'ta PF≥1.30 + ≥4/5 robustluk kanıtlarsa yeniden açılabilir.

### 6f. Dürüst Çekinceler
- conf=50 kullanıldı (prod-80 değil) → daha fazla trade, daha cömert; prod-80 muhtemelen daha az trade + benzer/daha kötü edge verirdi.
- Funding & slippage modellenmedi → gerçek net PF buradan **daha düşük** olur (sonucu güçlendirir, zayıflatmaz).
- v2-execute edildi (prod v2-shadow/v1-execute); v1 ayrı koşulmadı — ama v2 daha rafine pipeline, yani bu **charitable** (en güçlü) test.
- TV 15m derinliği ≠ bu cache (Binance 1 yıl); Pine gate'leri farklı veri görür ama edge sonucu rejim-bağımsız olmalıydı — değil.

### 6g. Artefaktlar
- `scripts/wave2_falsification.py` — falsifikasyon harness'ı (walk-forward, paralel, sim-time partition).
- `reports/wave2_falsification_v2.json` + `.log` — gerçek IS/OOS çıktısı.
- `backtest/engine.py` — sim-time damgalama fix'i (additive, satır ~246).

---

> **Özet karar (GÜNCEL — falsifikasyon koşuldu):** Wave-2 tam-redesign **DROP**. Python engine OOS walk-forward (6 ay, 5 sembol, cömert ayar) tavanı ölçtü → **pooled PF 1.165, 2/5 net-pozitif** → PF≥1.30 + ≥4/5 barını geçemedi, üstelik IS↔OOS işaret kararsızlığı edge'in rejim-bağımlı olduğunu gösterdi. **Indicator-only ship final ürün; premium-strateji iddiası kapandı.** Yeniden-açma koşulu: engine'in kendisi (Pine değil) yeniden tasarlanıp Python OOS'ta PF≥1.30 + ≥4/5 robustluk kanıtlamalı.

— 🔵 Claude (Opus 4.8)
