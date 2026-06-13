# Wave-1 Round-6 — Faithful SMC: Zone-Pullback Entry + Engine TP + Breaker Block

**Tarih:** 2026-06-13 · **Yazar:** @claude (brainstorming, operatör ile) · **Epic:** P-001 / T-003
**Branch:** `feat/p001-t003-strategy` (PR #194, DRAFT) · **Durum:** DESIGN (onay bekliyor)
**Dosyalar:** `pine/u2algo/wave1_strategy.pine` + `wave1_signals.pine` + `WAVE1_SPEC.md`

---

## 1. Bağlam & Motivasyon

Wave-1 STRATEGY iki gate turunu da geçemedi — **zıt sebeplerle:**

| Tur | Giriş | Sonuç |
|---|---|---|
| GATE_RUN_2 (round-4) | OB-dibine pasif limit | iyi edge (agg **PF 1.44**) AMA fill **~%41** (sinyallerin >%59'u expire) |
| GATE_RUN_3 (round-5) | sinyal barı close'unda market | fill **~%100** AMA edge yok (agg **PF 0.71**, 4/5 kaybeden) |

**Kök bulgu:** Stratejinin edge'i **OB-retrace limit girişine bağlı** — round-4'te limit YANLIŞ kenara (zone'un uzak/dip kenarı) konmuş, bu yüzden az dolmuş; round-5 market-at-close ise retrace'i bekleyemediğinden kötü fiyat. Canlı Python engine ise **zone-pullback** yapar: fiyatın zone'a geri çekilmesini bekler, **yakın (ilk-dokunuş) kenardan** girer (`clamp(price, zone.low, zone.high)`, `safe_orchestrator.py:1648-1697`).

**Fidelity ilkesi (CLAUDE.md):** Pine port'unun amacı canlı engine'i sadık yansıtmak. Engine'in gerçek SMC modeli Pine Wave-1'inkinden zengin:
- **Entry zone:** zone-pullback, yakın-kenar (Mode B confirmation'sız: `require_confirmation=false`).
- **TP:** likidite (EQH/EQL) + FVG hedefleri, `min_rr`-gate'li, **single-target fallback** (`tp_calc.py:38-127`).
- **Breaker Block:** mitigated OB'nin polarite-flip'i (`smc.py:250-255`, `OrderBlock.became_breaker`).

**Brainstorming kararları (2026-06-13, operatör):**
1. Karar kriteri = **sadık engine port** (sistem tutarlılığı).
2. Fidelity derinliği = **Mode B** (zone-touch, confirmation'sız; Wave-1 sadeleştirme).
3. Kapsam = **TP + BB** (engine-sadık TP + Breaker Block setup zone'u; entry OB|BB near-edge).

---

## 2. Hedef & Başarı Kriterleri

**Hedef:** Round-4'ün iyi edge'ini KORU, fill problemini near-edge zone-pullback ile çöz, TP'yi engine-sadık algoritmaya çevir, BB setup zone'u ekle.

**Başarı kriterleri (GATE_RUN_4'te doğrulanacak — validation-first):**
- Near-edge giriş → fill round-4'ten (%41) belirgin yüksek.
- Engine-TP → TP1/TP2 yapışıklığı yok (single-target), hedefler gerçek likidite/FVG.
- Agg PF > 1.0 (hedef ~1.15-1.4, round-3'ün 0.71'inden iyi), yeterli frekans (5 sembol ~4 ay).
- inverted=0, sub-RR=0 (yapısal, korunur).
- **Not:** WR≥%50 eşiği SMC-runner profili için gerçekçi DEĞİL (düşük WR + nadir büyük winner normal) → bu eşik validation sonrası operatör/konsensüsle revize edilir.

---

## 3. Mimari & Bileşenler

### 3.1 Setup Zone'ları: OB + Breaker Block

**OB tespiti (mevcut, korunur):** 5-ardışık ters mum + breakout body > 1.5×ATR(14) → zone `[ob_bot, ob_top]`, yön (BULL=demand / BEAR=supply), `near_swing`.

**Breaker Block (YENİ, `smc.py:250-255` portu):** Bir OB **mitigated** olunca (fiyat içinden close ile geçer) **polarite flip** eder ve breaker olur:

| Olay | Flip | Yeni rol | Entry yönü |
|---|---|---|---|
| BULL OB (demand), `close < ob_bot` | → BEAR breaker | direnç | fiyat ↑ dönerse **SHORT** @ zone alt-kenar |
| BEAR OB (supply), `close > ob_top` | → BULL breaker | destek | fiyat ↓ dönerse **LONG** @ zone üst-kenar |

**Zone evreni:** aktif (unmitigated) OB'ler + breaker'lar (mitigated, flip'li). Bir yön için **en yakın** geçerli zone seçilir.

**Confluence:** OB/BB aktif → +30 (mevcut skorlama korunur; breaker da bu faktöre katkı verir).

### 3.2 Entry: Near-Edge Zone-Pullback (Mode B) + Timeout

Birleşik kural (zone yönü long/short'u belirler; breaker OB yönünü flip'ler):
- **LONG zone** (demand: bullish OB veya bullish breaker): fiyat yukarıdan geri çekilir → **near edge = zone üstü** → `strategy.entry("LONG", limit=zone_high)`.
- **SHORT zone** (supply: bearish OB veya bearish breaker): fiyat aşağıdan geri çekilir → **near edge = zone altı** → `strategy.entry("SHORT", limit=zone_low)`.
- **Pullback timeout:** `pullback_timeout_bars` (input, default 40 — round-4 `limit_expiry` ile aynı) içinde dolmazsa `strategy.cancel` (engine `pullback_timeout_bars` karşılığı).
- Round-4'ten tek fark: limit YAKIN kenarda (uzak değil) + SL/TP entry'den (close değil).

### 3.3 SL (mevcut, korunur)

`f_calc_sl`: son `sl_lb` mum ekstremi ± `sl_atr_m`×ATR buffer, `[0.5×ATR, 0.001×entry]` min — `[5×ATR]` max clamp. **Kapsam dışı:** engine `sl_calc.py` tam paritesi (mevcut SL makul; sonraki tura).

### 3.4 TP Algoritması (engine-sadık, `tp_calc.py:38-127` portu)

`risk = |entry − SL|`, `min_dist = min_rr × risk`.

**TP1** — doğru taraftaki adaylardan mesafe ≥ `min_dist` olan **en yakın**:
1. **LIQUIDITY** (öncelik 0): EQH/EQL kümeleri + HTF swing ekstremleri (LONG: entry üstü EQH/swing-high; SHORT: entry altı EQL/swing-low)
2. **FVG_NEAR** (öncelik 1): karşı-yön FVG near-edge (LONG: BEAR FVG `bot` > entry; SHORT: BULL FVG `top` < entry)
- Fiyat-eşitliğinde precedence: LIQUIDITY > FVG_NEAR (engine `_SOURCE_PRIORITY`).
- Aday var ama hiçbiri ≥min_dist → **trade REDDEDİLİR** (`InsufficientTPDistance`; kötü TP'ye zorlama yok).
- Hiç aday yok → **RR_PROJECTION** (entry ± min_dist).

**TP2** — TP1'in ötesinde:
1. **FVG_FAR**: TP1-ötesi karşı-yön FVG far-edge (LONG: BEAR FVG `top` > TP1 en yakını; SHORT: BULL FVG `bot` < TP1)
2. yoksa **FIB_EXT**: `entry ± fib_tp2 × risk` (sadece TP1'in ötesindeyse)
3. yoksa **NONE → single-target** (TP1 kalanı TAMAMEN kapatır; **`tp1*1.02` hack'i KALDIRILIR**)

**Kaynak etiketleri:** `tp1_source ∈ {LIQUIDITY, FVG_NEAR, RR_PROJECTION}`, `tp2_source ∈ {FVG_FAR, FIB_EXT, NONE}` — alert mesajı + görselde gösterilir (şeffaflık + debug).

**Exit yapısı (mevcut korunur, single-target'a uyarlanır):**
- TP2 varsa: TP1 %50 kısmi (stop korunur) + TP2 kalanı (kendi stop'u).
- TP2 NONE (single-target): TP1 %100 kapatır (tek `strategy.exit`, stop korunur).

### 3.5 Yeni Pine Detektörleri

| Detektör | Engine ref | Pine yaklaşımı |
|---|---|---|
| **FVG** | `smc.py:38-44` | BULL: `low > high[2]`; BEAR: `high < low[2]`. `array<float>` top/bot/dir/idx. Mitigation: fiyat gap'i doldurunca işaretle. |
| **EQH/EQL** | `smc.py:91-101, 318-364` | Son N swing'i `array`'de tut; eq_thr(%0.1) içindeki çiftleri kümele → EQH/EQL @ ortalama, touches≥2. |
| **Breaker** | `smc.py:250-255` | OB `array`'i; her bar close OB içinden geçti mi → flip + breaker işaretle. |

### 3.6 Backtest Altyapısı (round-5'ten korunur)

- `bt_date_start/end` default **2020/2035** (latent bug fix: 2025 default → 2026 verisinde 0 trade).
- `bt_segment` (Full/IS/OOS) + `oos_start_idx = last_bar_index − int(last_bar_index×bt_oos_pct/100)` → G-T4b OOS-Sharpe ölçülebilir.

---

## 4. Veri Akışı

```
Her confirmed bar (15m):
 1. Swing tespiti → swing array güncelle → EQH/EQL kümeleri güncelle
 2. OB tespiti → OB array'e push; mevcut OB'leri mitigation için kontrol → breaker flip
 3. FVG tespiti → FVG array'e push; mitigation kontrol
 4. 1h bias (request.security EMA20) + confluence skoru
 5. Sinyal: en yakın geçerli zone (OB|BB) + conf≥thresh + 1h bias hizası
    → pending entry: limit @ zone near-edge, SL=f_calc_sl(near_edge), TP=engine_tp(near_edge, SL)
    → TP candidate yok/yetersiz ise REDDET (InsufficientTPDistance)
 6. Pending limit: fiyat near-edge'e değerse fill (TV limit); timeout'ta cancel
 7. Fill → exit emirleri (TP1 [+ TP2 / single-target] + stop)
 8. bt_date + bt_segment gate: pencere/segment dışı entry yok
```

---

## 5. Pine v6 Fizibilite + Wave-1 Sadeleştirmeleri

Hepsi `array` ile yapılabilir; **strateji dosyası ~2× büyür (~1000+ satır)**.

| Engine | Wave-1 sadeleştirme | Gerekçe |
|---|---|---|
| EQH/EQL greedy linear cluster | **pairwise** (çiftleri kümele) | Likiditenin çoğunu yakalar; Pine'da basit |
| HTF (1h/4h) FVG hedefleri | FVG'leri **15m entry TF**'de hesapla | request.security + array karmaşık → HTF-FVG hedefleri **Wave-2** |
| Çok-zone tracking | Array cap = son ~20-50 zone | Pine performans/bellek |
| 1h swing TP hedefi | Mevcut `request.security` 1h pivot KORUNUR | Zaten var, HTF likidite sağlar |
| confirmation candle (Mode A) | YOK (Mode B) | Karar #2; Wave-2'ye |

---

## 6. Korunan / Kaldırılan / Kapsam-dışı

**Korunan:** swing tespiti, 1h bias (EMA20), confluence scoring (7-faktör), SL (structural+ATR), bt_date fix, bt_segment OOS-split, risk-bazlı sizing (risk_pct), exit yapısı (TP1 kısmi + stop).

**Kaldırılan:** round-5 market entry, `allow_ob_less`, `process_orders_on_close`, eski swing-tabanlı TP + **`tp1*1.02` fallback**.

**Kapsam dışı (sonraki turlar / Wave-2):** engine `sl_calc.py` paritesi, HTF-FVG hedefleri, FVG/OTE entry zone'u, CHoCH/BOS trigger, confirmation candle (Mode A), SFP/range-deviation.

---

## 7. Validation-First Plan + Gate Eşik Notu

**Plan'ın İLK adımı = backtest doğrulaması** (implementasyondan önce edge'i kanıtla):
1. OB+BB entry + engine-TP modelini diagnostik build'le 5 sembolde (BTC/ETH/SOL/BNB/XRP perp 15m) koş.
2. Ölç: agg PF, fill oranı, frekans, WR, MaxDD, Sharpe (IS/OOS), inverted/subRR.
3. **Karar gate'i:** agg PF > 1.0 + fill round-4'ten iyi + frekans makul ise → finalize + G-T3 + tam GATE_RUN_4.
4. **Kontenjans:** frekans hâlâ düşükse (OB+BB seyrek) → (a) FVG/OTE entry zone'u ekle (Wave-2), veya (b) gate "min 100 trade" eşiğini düşük-frekans gerçeğine göre revize.

**Gate eşik notu:** **WR≥%50 SMC-runner için gerçekçi değil** — likidite-hedefli, nadir-büyük-winner profili düşük WR (%25-45) + PF>1 ile kârlı olabilir (round-4 ETH: WR %66 ama BNB PF 2.59 / WR %15). Bu eşik validation verisiyle operatör/konsensüse revize edilmeli.

---

## 8. SENKRON (indicator)

`wave1_signals.pine` (ücretsiz indicator) aynı zone (OB+BB) + TP (likidite/FVG) mantığını **görsel olarak** yansıtmalı — input isimleri + default'lar + detektörler SENKRON. Indicator emir vermez ama gösterdiği entry/SL/TP, strategy'nin fiili davranışıyla örtüşmeli. İki dosya da büyür.

---

## 9. Riskler & Açık Sorular

| # | Risk | Azaltma |
|---|---|---|
| R1 | Frekans hâlâ düşük olabilir (OB+BB seyrek) | Validation-first + kontenjans (§7) |
| R2 | Pine array performansı (çok zone/detektör) | Array cap (§5); G-T3'te compile/runtime kontrol |
| R3 | EQH/EQL pairwise sadeleştirme engine'den sapar | Wave-1 kabul; validation edge'i gösterir |
| R4 | Dosya ~2× → unused-var/marker riski | G-T3 0-marker gate; OB seq/top/bot bu kez KULLANILIYOR (zone+breaker) |
| R5 | 0-marker: yeni `array` API'leri | Defansif Pine (Hermes derleyemiyor); G-T3 doğrular |

**Açık sorular (validation sonrası):**
- Frekans düşükse FVG/OTE-entry'yi bu spec'e mi alalım yoksa Wave-2'ye mi?
- WR/PF/trade-count gate eşikleri ne olmalı (SMC-runner gerçeğine göre)?

---

## 10. Referanslar

**Engine (fidelity kaynağı, repo kökü `engine/`):**
- Zone-pullback entry + clamp: `safe_orchestrator.py:1648-1697`
- TP algoritması: `smc_v2/tp_calc.py:38-127`
- Pullback zone (FVG/OTE): `smc_v2/zones.py:26-69`
- OB + breaker: `smc.py:200-256` (`became_breaker`:250-255)
- FVG: `smc.py:38-44` · EqLevel + liquidity_pools: `smc.py:91-101, 318-364`

**Gate raporları:** `LLTODO/reports/REPORT-T-003-gate-run-{1,2,3}.md`
**Round-5 prompt (önceki tur):** `docs/handoff/2026-06-13-hermes-t003-round5-prompt.md`
**Plan:** `LLTODO/plans/P-001-*.md` (v1.4 §8a; round-6 §6 eskalasyonu — bu spec konsensüse açılır)
