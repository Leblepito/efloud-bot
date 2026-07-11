# PINE_SPEC.md — efloud-bot **SMC v2** → TradingView Pine Script v6

> **Kaynak motor:** `engine/smc_v2/` (V2 rework, shadow mode).
> **Karar:** V2 seçildi çünkü çevrilemeyen harici bağımlılığı (Gemini AI gate) YOK
> → Pine portu davranışsal olarak sadık olabilir.
> **Bu dosya onaylanmadan Pine koduna (`pine/efloud_signals.pine`,
> `pine/efloud_strategy.pine`) geçilmeyecek.**

Tüm satır referansları doğrulanmıştır (`engine/smc_v2/*.py`, `engine/smc.py`,
`configs/config.phase2_1k.yaml` — üretimde çalışan config).

---

## 0. V1 vs V2 — neden bu spec V1'den farklı

| Konu | V1 (`engine/smc.py`+`signals.py`) | **V2 (bu spec)** |
|---|---|---|
| Yapı | Tek-geçiş, her bar bağımsız taranır | **Durum makinesi** — setup'lar barlar arası YAŞAR |
| Giriş | CHoCH **veya** BOS, anlık snap | Sadece **CHoCH** → pullback bekle → **engulfing** teyidi |
| Confluence | 100 puanlık skor + 55 eşik | **YOK** (`confluence_score=0` placeholder) |
| AI gate | Gemini doğrulama (≥0.70) — **çevrilemez** | **Yok** — tam çevrilebilir |
| SL aşırı | clamp'lenir | **>5×ATR ise setup REDDEDİLİR** (clamp yok) |

**Pine'a etkisi:** V2 bir *bekleme-onay* makinesi. Her CHoCH anında işlem
açılmaz; bir aday (`SetupCandidate`) oluşur, fiyat hedef zone'a gelene ve orada
engulfing teyidi oluşana kadar bekler. Bu yüzden Pine'da **kalıcı durum**
(`var`) ve **bar-bar ilerleyen mantık** gerekir — tek satırlık `plotshape`
yetmez.

---

## 1. Timeframe zinciri (`config.timeframes`)

| TF | Pine `request.security` | Rol |
|---|---|---|
| **4h** (HTF) | `"240"` | Bias yönü + yapısal SL anchor + TP likidite/FVG kaynakları |
| **1h** (MTF) | `"60"` | (V2'de opsiyonel; TP likiditesi çoğunlukla 4h'tan) |
| **15m** (Entry/LTF) | grafik TF'i (chart) | CHoCH tetik + pullback zone + engulfing teyit |
| **1d** (Daily) | `"1D"` | Makro filtre (V1'de ±5 puan; V2'de sert/soft filtre olarak opsiyonel) |

> **Profil notu (2026-07-06):** Yukarıdaki tablo TARİHSEL tek-chain (eski mid)
> düzenidir. Chain artık profil bazlıdır — tek kaynak `data/timeframes.py`
> `PROFILES`; güncel eşleme için §17'ye bak. Pine'da `profileMode` input'u bu
> merdiveni seçer.

> **Repaint kuralı (ZORUNLU):** Tüm `request.security()` çağrıları
> `lookahead=barmerge.lookahead_off`, `gaps=barmerge.gaps_off` ile ve **HTF için
> kapanmış bar** (`[1]` veya `barstate.isconfirmed`) kullanılarak yapılır.
> Aksi halde backtest ileriye-bakar ve sahte sonuç üretir.

---

## 2. Paylaşılan SMC primitifleri (V2, bunları v1 `engine/smc.py`'den tüketir)

V2 modülleri kendi swing/FVG/yapı tespitini YAPMAZ; `SMCEngine`'in çıktısını
girdi alır. Dolayısıyla Pine'da bu primitifleri **bir kez** uygulayıp her TF'de
çağırırız.

### 2.1 Swing tespiti — `smc.py:130-140` (`swing_lb=5`)
```
swingHigh[i]  = high[i] tüm high[i±1..5]'ten kesin büyük   (sol+sağ 5 bar)
swingLow[i]   = low[i]  tüm low[i±1..5]'ten kesin küçük
```
Pine: `ta.pivothigh(5,5)` / `ta.pivotlow(5,5)`. **Not:** pivot 5 bar sağ teyit
gerektirir → swing 5 bar gecikmeyle kesinleşir (repaint-safe, kabul edilebilir).

### 2.2 Yapı kırılımı CHoCH/BOS — `smc.py:144-165`
```
trend takip et (BULL/BEAR/UNDEF), son swingHigh (last_sh) ve swingLow (last_sl) tut.
close > last_sh.price  →  yön=BULL,  kind = (trend∈{BEAR,UNDEF}) ? CHoCH : BOS,  trend=BULL, last_sh temizle
close < last_sl.price  →  yön=BEAR,  kind = (trend∈{BULL,UNDEF}) ? CHoCH : BOS,  trend=BEAR, last_sl temizle
```
**V2 SADECE CHoCH kullanır** (`triggers.py:74`). BOS göz ardı edilir.

### 2.3 FVG tespiti — `smc.py:169-187`
```
Bullish FVG (bar i): low[i] > high[i-2]   → {top=low[i], bot=high[i-2], dir=BULL}
Bearish FVG (bar i): high[i] < low[i-2]   → {top=low[i-2], bot=high[i], dir=BEAR}
Mitigasyon: BULL → sonraki bir bar low <= bot; BEAR → sonraki bar high >= top
```
V2 zone/TP için **mitige OLMAMIŞ HTF FVG** ister (`zones.py`, `tp_calc.py`).
Pine: FVG'leri `array<box>`/paralel dizilerde tut, mitige olunca işaretle.

### 2.4 OTE bandı — `smc.py:286-294` (`ote_lo=0.618`, `ote_hi=0.786`)
```
d = lastSwingHigh - lastSwingLow
BULL: top = SH - d*0.618 ; bot = SH - d*0.786
BEAR: top = SL + d*0.786 ; bot = SL + d*0.618
```
V2'de zone fallback'i (FVG yoksa). HTF leg üzerinden hesaplanır.

### 2.5 Equal-levels / likidite havuzları — `smc.py:298-354` (`eq_thr=0.1%`)
Swing'leri 0.1% içinde kümeler → `EqLevel{price, kind=EQH/EQL}`. V2 TP1
likidite adaylarında kullanılır.

---

## 3. HTF bias çözümü (V2 girdisi `htf_bias`)

`triggers.py:66` — `htf_bias == "UNDEF"` ise **hiç setup üretilmez**. Bias şu
sırayla çözülür (v1 `signals.py:251-274` ile aynı):
```
1. 4h yapı trendi (structure() son trend durumu)
2. UNDEF ise: 40-bar % değişim slope → > +2% BULL, < -2% BEAR
3. Hâlâ UNDEF ise: range aktifse range yönü (discount→BULL, premium→BEAR)
4. Aksi halde: setup yok
```
Pine: 4h trendi yoksa `(close[1]/close[40] - 1)*100` ile fallback. Eşik input.

---

## 4. V2 SETUP DURUM MAKİNESİ (çekirdek) — `setup_state.py`

```
                  CHoCH tetik (§5)
                        │
                        ▼
              ┌──────────────────┐  bars_waited > timeout
              │ AWAITING_PULLBACK │ ─────────────────────────► EXPIRED
              └──────────────────┘
                        │  fiyat zone'a girdi (is_price_in_zone)
                        ▼
              ┌──────────────────┐  bars_waited > timeout
              │      IN_ZONE      │ ─────────────────────────► EXPIRED
              │  (sticky — zone'  │
              │   dan çıksa da    │  engulfing teyidi (§6)
              │   geri dönmez)    │ ─────────────────────────► CONFIRMED → [ENTRY]
              └──────────────────┘
```

**Durum kuralları** (`setup_state.py`, agent-map + spec §4.3):
- `AWAITING_PULLBACK`: her bar `bars_waited++`. `is_price_in_zone(price,zone)`
  true olunca → `IN_ZONE`.
- `IN_ZONE`: **yapışkan** — fiyat zone'dan çıksa bile geri DÖNMEZ. `bars_waited`
  artmaya devam eder. Sadece timeout ile düşer.
- Timeout: `bars_waited > pullback_timeout_bars` (**8** × 15m ≈ 2 saat) → `EXPIRED`.
- `IN_ZONE` + engulfing teyit → `CONFIRMED` → giriş emri.
- Sembol başına cap: `max_pending_per_symbol = 3` aktif aday (`AWAITING_PULLBACK`
  + `IN_ZONE`). Cap doluysa yeni CHoCH reddedilir (`setup_state.py:37`).

> **Pine port stratejisi:** Pine'da `SetupCandidate`'i paralel `var` dizilerinde
> tut (`var float[] pendDir`, `pendZoneLow`, `pendZoneHigh`, `pendAnchor`,
> `pendTriggerPx`, `pendState`, `pendBarsWaited`, `pendTriggerBarIdx`). Her bar
> kapanışında (`barstate.isconfirmed`): (1) yeni CHoCH adayları ekle (cap kontrol),
> (2) mevcut adayları ilerlet/expire et, (3) CONFIRMED olanı entry'e çevir ve
> diziden çıkar. **Indikatörde** `label`/`line` ile çiz; **stratejide**
> `strategy.entry`/`strategy.exit`. Tek-sembol grafik olduğu için cap pratikte
> grafikteki aktif aday sayısıdır.

---

## 5. TETİK (CHoCH → SetupCandidate) — `triggers.py:36-128`

Her **15m** yapı kırılımı için:
```
1. brk.kind == "CHoCH" değilse        → atla         (BOS göz ardı)
2. brk.direction != htf_bias          → atla         (bias hizası şart)
3. brk.idx < recency_cutoff           → atla         (recency filtresi)
4. yön = BULL?LONG : SHORT
5. anchor = select_htf_swing_anchor(...) ; None ise → atla   (§7)
6. zone = build_pullback_zones(...)                          (§8)
7. zone.source=="OTE" ve zone.low==zone.high → atla (dejenere sıfır-genişlik)
8. SetupCandidate(state=AWAITING_PULLBACK, bars_waited=0, trigger_bar_ts=brk.idx,
                  trigger_price=brk.price, htf_swing_anchor=anchor, target_zone=zone)
```

---

## 6. ZONE seçimi — `zones.py:26-69` (`fvg_priority: true`)

```
SHORT (yukarı pullback bekle):
  adaylar = trigger_price ÜSTÜNDEKİ BULL FVG'ler (f.bot > trigger_price)
  varsa: en yakın = min(f.bot - trigger_price)  →  zone=[f.bot, f.top], source=HTF_FVG
LONG (aşağı pullback bekle):
  adaylar = trigger_price ALTINDAKİ BEAR FVG'ler (f.top < trigger_price)
  varsa: en yakın = max(f.top)                  →  zone=[f.bot, f.top], source=HTF_FVG
FVG yoksa → fallback OTE bandı (§2.4), source=OTE
```
Üyelik: `zone.low <= price <= zone.high` (kapsayıcı, `zones.py:72-74`).

---

## 7. YAPISAL SL ANCHOR — `swing_anchor.py:30-87`

İşlemin **ters tarafındaki en son KIRILMAMIŞ HTF swing**:
```
SHORT: aday = swing_highs ; LONG: aday = swing_lows
sadece swing.idx < trigger_idx (gelecekteki yapıya anchor yok)
en yeni→eski sırala; her swing için:
  kırılmış mı? = trigger sonrası bir HTF barı swing'i delmiş mi
     SHORT: bar.high > swing.price  → kırık
     LONG:  bar.low  < swing.price  → kırık
  kırılmamış ilk swing'i döndür
hiç yoksa → None → setup reddedilir (SLTooFarError ile aynı sonuç)
```
> **Ordinal eksen uyarısı** (`swing_anchor.py:13-24`): `trigger_idx` ve
> `bar.ordinal` aynı bar-pozisyon ekseninden int olmalı (timestamp DEĞİL).
> Pine'da `bar_index` doğal olarak bunu sağlar.

---

## 8. STOP LOSS formülü — `sl_calc.py:23-64`

```
buffer = sl_atr_buffer * ATR(14, 15m)            # 0.5 * ATR
LONG:  structural_sl = min(zone.low,  anchor) - buffer
SHORT: structural_sl = max(zone.high, anchor) + buffer

stop_dist = |entry - structural_sl|
min_dist  = min_sl_atr * ATR    # 0.5 * ATR
max_dist  = max_sl_atr * ATR    # 5.0 * ATR

if stop_dist > max_dist:  SETUP REDDEDİLİR (clamp YOK — yapıyı bozar)
if stop_dist < min_dist:  SL'yi tabana genişlet:
        LONG  → entry - min_dist ;  SHORT → entry + min_dist
else:   structural_sl
```
> **ATR KRİTİK NOT (2026-07-06 düzeltme, bkz. §18):** Yukarıdaki formülde
> geçen "ATR", canlı `safe_orchestrator.py`'de **gerçek `ta.atr(14)` DEĞİL** —
> `atr_15m = max(entry_price * 0.01, |zone.high - zone.low|)` proxy'sidir
> (`safe_orchestrator.py:1900-1903/1960-1962`, dokümante "DELIBERATE
> SIMPLIFICATION"). `sl_calc.py` bu parametreyi TF-agnostik alır; hangi
> değerin geleceğine orkestratör karar verir. Pine bu proxy'yi birebir
> uygular (`calcSl`'de `atrProxy`) — gerçek `ta.atr(14)` kullanmak clamp'i
> canlıdan çok daha sıkı yapıp (HTF anchor uzakken, özellikle 12h/8h/4h)
> setup'ları sistematik reddediyordu.

---

## 9. TAKE PROFIT formülü — HİBRİT (`tp_calc.py:38-127` zinciri + `signals.py:519-585` Fibonacci ladder)

Pine `calcTp`: v2 aday zinciri (likidite/FVG) **+** yapı yokken v1 Fibonacci discovery ladder.

```
risk = |entry - sl|
min_dist = min_rr * risk        # min_rr = 1.8 (prod) / 1.5 (root)

── TP1 aday zinciri (öncelik: LIQUIDITY > FVG_NEAR; fiyat eşitliğinde LIQUIDITY) ──
LONG (entry ÜSTÜ):
   en-yakın EQH (htfEqh, price>entry)                      [LIQUIDITY]
 + en-yakın HTF swing high (htfSwingHigh, price>entry)     [LIQUIDITY]
 + BEAR FVG yakın-kenar (bearFvgBot > entry)               [FVG_NEAR]
SHORT (entry ALTI): ayna — htfEql + htfSwingLow + BULL FVG bullFvgTop  (hepsi <entry)

bestLiq = mesafesi >= min_dist olan en-yakın LIQUIDITY; bestFvg = aynısı FVG_NEAR.
tp1:
   ikisi de varsa → daha yakını (eşit/belirsiz yakınlıkta LIQUIDITY; FVG yalnız STRICTLY yakınsa)
   yalnız biri varsa → o
   aday VAR ama hiçbiri >= min_dist → tp1 = na  (InsufficientTPDistance → setup RED)
   HİÇ aday yoksa → Fibonacci price discovery: tp1 = entry ± max(min_rr, fibTp1)*risk
                    (fibTp1=1.272; min R:R'yi koruyacak şekilde clamp), isDiscovery=true

── TP2 ──
isDiscovery → tp2 = entry ± fibDiscTp2*risk   (2.618)
aksi halde:
  LONG: tp1 ötesindeki BEAR FVG far-kenar (bearFvgTop > tp1) varsa → o   [FVG_FAR]
        yoksa fib_tp2 = entry + fib_ext*risk ; (fib_tp2 > tp1) ise FIB_EXT, değilse na
  SHORT: ayna (bullFvgBot < tp1 ; entry - fib_ext*risk)
Değişmez kural: TP2 > TP1 (LONG) / TP2 < TP1 (SHORT) kesin, veya TP2 = na → TEK HEDEF modu.
```
- `fibTp1` ≈ **1.272** (price discovery TP1; `signals.py:521/563`); `min_rr` < 1.272 değilse `max()` clamp devreye girer.
- `fibDiscTp2` ≈ **2.618** (discovery TP2; `signals.py:583`).
- `fib_ext` ≈ **1.618** (yapısal TP2; v1 varsayılanı).
- **EQH/EQL** (`htfEqh`/`htfEql`): `htfBundle`'da ardışık iki pivot `eqThr` (%0.1) içindeyse oluşur — `smc.py:308-353 liquidity_pools` küme mantığının tek-skaler karşılığı.
- TP2 = na ise: lifecycle TP1'de **tam kapanış** yapar (50/50 ladder YOK).
- TP2 varsa: TP1'de %50, TP2'de kalan %50 (strateji versiyonunda).

---

## 10. RED nedenleri (`exceptions.py`) → Pine'da "setup düşür"

| Durum | Tetik | Pine karşılığı |
|---|---|---|
| `SLTooFarError` | stop_dist > 5×ATR | adayı oluşturma / düşür |
| anchor=None | kırılmamış HTF swing yok | adayı oluşturma |
| `InsufficientTPDistanceError` | yapısal TP adayları var ama hiçbiri min R:R'ye uzak değil | `calcTp` `tp1=na` döner → `tpOk` false → setup fire etmez |
| timeout | bars_waited > 8 | EXPIRED, diziden çıkar |
| cap | sembolde 3 aktif aday | yeni CHoCH'u reddet |
| TP2 invalid | fib_tp2 ≤ tp1 | TP2=None (tek hedef) |

---

## 11. Config → Pine `input.*` (AYNI isimler indikatör+strateji)

| Pine input | Default | Kaynak |
|---|---|---|
| `swingLb` | 5 | `smc.py:109` |
| `obSeq` | 5 | `smc.py:109` |
| `rangeLb` | 50 | `smc.py:111` |
| `oteLo` / `oteHi` | 0.618 / 0.786 | `smc.py:111-112`, `smc_v2.ote_band` |
| `pullbackTimeoutBars` | 8 | `config smc_v2` |
| `maxPendingPerSymbol` | 3 | `setup_state.py:37` |
| `requireConfirmation` | true | `config smc_v2` |
| `slAtrBuffer` | 0.5 | config `risk.sl_atr_buffer` |
| `minSlAtr` | 0.5 | config `safety.min_sl_atr` |
| `maxSlAtr` | 5.0 | config `safety.max_sl_atr` |
| `minRr` | 1.8 | `config.phase2_1k risk.min_rr` |
| `eqThrPct` | 0.1 | `smc.py` eq_thr (EQH/EQL kümeleme) |
| `fibTp1` | 1.272 | `signals.py:521/563` (price discovery TP1) |
| `fibDiscTp2` | 2.618 | `signals.py:583` (discovery TP2) |
| `fibExt` | 1.618 | v1 default |
| `atrLen` | 14 | `smc.py` |
| `htfSlopePct` | 2.0 | bias fallback |
| `dailyFilterStrict` | false | v1 davranışı |
| `riskPerTradePct` | 1.0 | strateji pozisyon boyutu |
| `moveSlToBe` | true | strateji: TP1 sonrası SL → break-even (entry) |

---

## 12. ÇEVRİLEMEYEN / SAPMA noktaları (dürüst liste)

1. **State persistence** (`setup_state.json`, atomik yazma): Pine'da kalıcı disk
   yok. Backtest'te `var` durumu oturum-içi yaşar; bot restart senaryosu Pine'da
   YOK → backtest'te bu fark görünmez (kabul edilebilir).
2. **Engulfing-only teyit:** Spec §4.1 CHoCH/OB-tap'tan bahsetse de
   `confirmation.py` sadece **engulfing** uygular. Pine de engulfing-only olacak
   (MVP sadakati).
3. **Çoklu-sembol cap:** V2 sembol başına 3 aday tutar; Pine tek grafik → cap
   o grafikteki adaylar. Portföy seviyesi risk (toplam pozisyon) Pine'da yok.
4. **`risk_per_trade_pct` pozisyon boyutu:** Pine `strategy`'de
   `strategy.entry qty` ile simüle edilir; gerçek borsa marj/leverage birebir değil.
5. **MTF(1h) rolü:** V2'de zayıf; spec'te 4h ağırlıklı. Pine'da 1h opsiyonel.
6. **TP1 likidite kümeleri:** Python tüm EQH/EQL kümelerini + tüm swing'leri tarar; Pine `htfBundle`
   skaler sınırı nedeniyle (request.security dizi döndüremez) yön başına **tek en-yakın** swing +
   **tek skaler** EQH/EQL + FVG_NEAR yakın-kenarını taşır (3 skaler aday). Tam küme dizileri yok.
   **EQH/EQL tespiti pencere-bazlı:** yeni pivot, son `eqWindow`(5) pivotun herhangi biriyle
   `eqThr` (%0.1) içindeyse eşit-seviye sayılır — ardışık-OLMAYAN eşitlikleri de yakalar
   (internal `var float[]` ring buffer; dönüş yine tek skaler `lastEqh`/`lastEql`).
7. **SL → break-even (strateji):** `moveSlToBe=true` iken TP1 hedefine ulaşıldığında kalan
   (runner) pozisyonun stop'u entry'e çekilir. V1 spec'inde yoktu; risk yönetimi iyileştirmesi.
   Sadece strateji versiyonunda (indikatör pozisyon yaşam döngüsü tutmaz).

---

## 13. İndikatör ↔ Strateji senkronu (ZORUNLU)

- İki dosya **aynı input isimleri** ve **aynı hesaplama fonksiyonlarını** kullanır.
- Mantık değişirse HER İKİ dosya güncellenir (CLAUDE.md kuralı).
- İndikatör: `plotshape` (CHoCH tetik), `box` (zone), `line`+`label` (entry/SL/TP1/TP2),
  `alertcondition` (her giriş/çıkış).
- Strateji: `strategy.entry` (CONFIRMED'da), `strategy.exit` (SL + TP1/TP2 ladder),
  `commission_value=0.04`, `slippage=1`.

---

## 14. Onay sonrası sıradaki adım

Bu spec onaylandıktan sonra **Faz B**: `pine/efloud_signals.pine` (indikatör)
üretilir → TradingView MCP ile enjekte/derle/sıfır-hata → `pine_save`.
Sonra **Faz C**: `pine/efloud_strategy.pine` (backtest).

> **Açık karar:** `minRr` default'u **1.8** (üretim `config.phase2_1k`) mı yoksa
> **1.5** (root `config.yaml`) mi olsun? Üretim davranışına sadık kalmak için
> 1.8 öneriyorum.

---
---

# EK A — V1 PORT (confluence makinesi)

> **Kaynak:** `engine/smc.py` + `engine/signals.py` + `engine/confluence.py`
> **Dosyalar:** `pine/efloud_signals_v1.pine` (indikatör) + `pine/efloud_strategy_v1.pine` (strateji)
> **Amaç:** V2 ile **yan yana karşılaştırma**. V1, üretimde V2'den ÖNCE çalışan
> tek-geçiş confluence mantığıdır. Bu ek, ana spec'in (§1-14) V2 odağını
> bozmadan V1 portunu belgeler.

## A.0 — V1 ↔ V2 özet (bkz. §0 tablosu)

| Konu | **V1 (bu ek)** | V2 (ana spec) |
|---|---|---|
| Çekirdek | Tek-geçiş, her bar bağımsız taranır | Durum makinesi (setup barlar arası yaşar) |
| Giriş tetiği | CHoCH **veya** BOS, anlık snap | Sadece CHoCH → pullback → engulfing |
| Skorlama | **Confluence 0-100, eşik 55** | YOK |
| AI gate | Gemini ≥0.70 (**çevrilemez**) | Yok |
| SL aşırı | **clamp** (güvenlik mesafesi) | >5×ATR → setup RED |
| minRr | **1.5** | 1.8 |

## A.1 — 4-TF akış (`signals.py:215-661`)

1. **Daily (1d)** — opsiyonel makro filtre. Soft: ±5 confluence; Strict: ters yön → reddet. Slope fallback: 30-bar %±5.
2. **HTF (4h)** — bias (yapısal trend + slope fallback %±2), aktif BULL/BEAR FVG, swing likidite.
3. **MTF (1h)** — CHoCH onayı (yön hizalı → +20 confluence).
4. **Entry (15m)** — aligned CHoCH/BOS tetik → confluence skoru → eşik → SL/TP/RR.

## A.2 — Confluence formülü (`confluence.py` BİREBİR)

```
score = 0
bias aligned (is_long ↔ BULL / short ↔ BEAR)   +25   ← filtre garantisi: daima
MTF CHoCH (yön hizalı)                          +20
Price in HTF FVG                                +15
Price at Order Block                            +10
   └ OB near swing (±%1.5)                       +5
   └ Price at OB EQ (±%0.3)                       +3
Price in OTE (0.618–0.786)                      +10
SFP likidite süpürmesi (±10 bar)                +10
Doğru zone (long+discount / short+premium)       +5
Range deviation                                  +5
─────────────────────────────────────────────
AI macro sentiment (manuel input ↔ Gemini)      ±5
Daily aligned / diverging                        ±5
score = clamp(0, 100)         eşik: min_confluence = 55
```

## A.3 — Order Block (`smc.py:191-252`)

- Breakout mumu body `> 1.5 × SMA(high-low, 14)` (true-range ATR DEĞİL — Python `(h-l).rolling(14)`).
- Ardışık ≤`obSeq`(5) ters mum; body_mode: BULL OB top=`open`, bot=`close` (bear mumlar); BEAR OB ayna.
- Mitigasyon → breaker: BULL OB `close < bot` ile; BEAR `close > top` ile. Pine'da mitige OB diziden çıkarılır.
- `near_swing`: OB kenarı son ters swing'e ±%1.5.

## A.4 — SL (`signals.py:452-535`)

```
buffer_mult = close_spread > 1.2 × hl_spread ? 0.75 : 0.5   # volatilite-hizalı
buffer = buffer_mult × ATR(14, true-range)
LONG:  local_lo = lowest(low,20)[break öncesi] − buffer
       sl = max(son_swing_low, local_lo)      # daha tight (yüksek) tarafı seç
       if deviation: sl = min(sl, range.lo − buffer)
       sl = min(sl, entry × 0.999)            # güvenlik clamp (≥%0.1 alt)
SHORT: ayna
```
> **V2 farkı:** V1 SL'yi **clamp**'ler (asla reddetmez). V2 `>5×ATR` ise setup'ı reddeder.

## A.5 — TP (`signals.py:498-585`)

```
risk = |entry − sl| ; min_tp = entry ± risk × min_rr (1.5)
TP1:
  deviation       → range.eq  (clamp: en az min_tp)
  ranging (HTF UNDEF) + likidite → en yakın HTF swing likiditesi
  trending        → en yakın {FVG kenarı, swing likidite} ≥ min_tp
  hiçbiri yok     → entry ± risk × 1.272   (price discovery)
TP2:
  deviation                       → range extreme (hi/lo)
  discovery VEYA ranging-likidite → entry ± risk × 2.618   (F1: Python is_discovery = htf_above_targets boş → ranging dalı da buraya girer)
  trending-yapısal-hedef          → entry ± risk × fib_ext (1.618)
Filtre: TP1 doğru tarafta + rr1 ≥ min_rr
```

## A.6 — Pullback refinement (`signals.py:372-383`)

OB içindeyse: LONG `entry = min(ob.top, trigPx)` / SHORT `max(ob.bot, trigPx)`.
Değilse OTE içindeyse: OTE kenarına çek. (Confluence skoru **orijinal** break fiyatında hesaplanır, refinement SONRA.)

## A.7 — ÇEVRİLEMEYEN / SAPMA (V1'e özel — dürüst liste)

1. **Gemini AI Structure Validation** (confidence ≥0.70 gate, `signals.py:120-212`) → ÇEVRİLEMEZ. Yerine kural-tabanlı confluence eşiği + manuel `aiSentiment` input'u (RISK_ON/OFF → ±5).
2. **Tüm-geçmiş tarama → bar-bar:** Python her çağrıda tüm break'leri tarar (recency penceresi gerekir); Pine break OLUŞTUĞU bar'da değerlendiriri → recency içkin, `recencyBars` input'u parite-amaçlı.
3. **HTF likidite TP:** Python tüm swing-high + eq-high tarar; Pine en-yakın tek HTF swing'e indirger (V2 §12 ile aynı sadeleştirme).
4. **MTF CHoCH:** Python son 5 CHoCH; Pine en-son MTF CHoCH yönü.
5. **Range deviation ÖLÜ KOD:** `smc.py:280-282` range-min'i CURRENT bar dahil hesaplar → `dev_bull/dev_bear` pratikte HİÇ tetiklenmez. Pine portu **niyeti** yansıtır (prior-range, current hariç penetrasyon+reclaim); `useIntendedDeviation=false` ile Python'a sadık (hep false) moda dönülür. **→ Bilinçli davranış farkı. (FIXED 2026-05-30: Default false yapılarak Python ölü-kod davranışı ile birebir hizalanmıştır - S4).**
6. **PA Level confluence** (Major Opening / Stacked Zone, `signals.py:422-436`, +5/+8) → inject edilen harici seviye gerektirir, ATLANDI.
7. **Target-Inversion Prevention (Y5):** Python `_enforce_tp2_beyond_tp1` ile TP2'yi daima TP1'den uzağa zorlar. Pine V1 signal ve strategy dosyalarına bu guard birebir eklenmiştir. **(FIXED 2026-05-30: Borsa immediate trigger rejects koruması - S3).**

## A.8 — V1 input'ları (indikatör ↔ strateji AYNI isim)

| Pine input | Default | Kaynak |
|---|---|---|
| `swingLb` | 5 | `smc.py:109` |
| `obSeq` | 5 | `smc.py:109` |
| `rangeLb` | 50 | `smc.py:111` |
| `oteLo` / `oteHi` | 0.618 / 0.786 | `smc.py:111-112` |
| `htfSlope` | 2.0 | bias fallback |
| `minConfluence` | **50** (FIXED 2026-05-30) | `config.phase2_1k.yaml:96` (production-active - S1) |
| `aiSentiment` | NONE | Gemini sentiment karşılığı (manuel) |
| `atrLen` | 14 | `smc.py` |
| `slAtrBuffer` / `volAtrBuffer` | 0.5 / 0.75 | `signals.py:472,477` |
| `minRr` | **1.8** (FIXED 2026-05-30) | `config.phase2_1k.yaml:95` (production-active - S2) |
| `fibExt` | 1.618 | `signals.py:223` |
| `recencyBars` | **40** (FIXED 2026-05-30) | `config.phase2_1k.yaml:97` (production-active - S2) |
| `useDaily` / `dailyStrict` | false / false | `signals.py` opsiyonel 4. TF |
| `useIntendedDeviation` | **false** (FIXED 2026-05-30) | Python ölü kod uyumu (S4) |
| `riskPerTradePct` (strateji) | 1.0 | pozisyon boyutu |
| `tp1ClosePct` (strateji) | 50.0 | TP1'de %50 kapanış |
| `moveSlToBe` (strateji) | true | TP1 sonrası SL → break-even (entry) |
| `showSmcCtx` (indikatör) | true | sinyalde eşleşen OB kutusu + OTE bandı + LIQ çizgisi |

## A.9 — İndikatör ↔ Strateji senkronu (V1)

V2 ile aynı kural (§13): aynı input isimleri + aynı hesap fonksiyonları (`htfBundle`,
`mtfBundle`, OB/SFP/OTE/range, `calcSl`/`calcTp` mantığı). Mantık değişirse her iki
V1 dosyası birlikte güncellenir. Strateji: `strategy.entry` (CONFIRMED'da, risk-bazlı
qty), `strategy.exit` (TP1 %50 + TP2 %50 ladder, ortak SL; `moveSlToBe`=true ise TP1 sonrası
SL break-even'a çekilir), `commission=0.04`, `slippage=1`. İndikatörde `showSmcCtx` ile sinyalde
eşleşen OB/OTE/LIQ görseli çizilir (strateji-only `moveSlToBe` ve indikatör-only `showSmcCtx`
pozisyon/görsel yaşam döngüsü farkı; senkron kuralı paylaşılan hesap mantığı için geçerli).


---

## 15. Değişiklik kaydı — 2026-07-03 repaint fix (5 dosya senkron)

Statik v6 denetimi (bkz. session handoff) `lookahead_off`'un canlıda OLUŞMAKTA
OLAN HTF/MTF/1D barını okuduğunu doğruladı → canlı sinyal ≠ backtest riski.
Uygulanan kanonik reçete: bundle dönüşleri `[1]`-shift + `lookahead_on` — her
iki rejimde de SON KAPANMIŞ üst-TF barı okunur (CLAUDE.md "sadece kapanmış bar"
kuralı). Etki: sinyaller üst-TF kapanışını bekler (daha muhafazakâr, motorla
uyumlu). Ayrıca: ölü `recencyBars` input'u V2 üçlüsünden silindi (AUDIT L1'in
fiilen uygulanmamış olduğu görüldü); V1 başlık metinleri prod default'larıyla
(minRr 1.8, minConfluence 50) eşitlendi; publish TF notundaki "1Dm" gösterimi
düzeltildi. Eski AUDIT'lerin "repaint temiz" hükmü bu reçeteyle geçersizdir.


---

## 16. Değişiklik kaydı — 2026-07-03 v2.1: V1 özellikleri V2'ye absorbe edildi

Operatör talebiyle V1'in TÜM özellikleri, V2 durum makinesi çekirdeği korunarak
`efloud_signals.pine` + `efloud_strategy.pine` (senkron) içine taşındı:
MTF CHoCH onayı (opsiyonel, `useMtf`), Order Block motoru (tespit+mitigasyon+
retest; zone zinciri artık **FVG > OB > OTE**), SFP, range premium/discount +
deviation (niyet modu, default OFF), volatilite-hizalı SL buffer (0.5x/0.75x),
0-100 **confluence skoru** — ONAY (engulfing) anında hesaplanır; `useConfluenceGate`
(default ON, eşik 50) düşük skorda adayı DÜŞÜRMEZ, timeout'a kadar bekletir —
AI macro sentiment (manuel), TF-adaptif çizim saklama havuzu, aktif OB kutuları,
SMC bağlam görselleri ve dashboard tablosu (V2 makine satırları eklenmiş).
Her iki dosya TradingView Pine Editor'da SIFIR HATA derlendi ve buluta
kaydedildi (EFloud Signals v2 rev.2 13:28 · EFloud Strategy v2 rev.1 13:33).
V2'nin "confluence YOK" sadeleştirmesi (§0) bu sürümle bilinçli olarak geri
alınmıştır; skor artık V1 formülünün V2-bağlamlı uyarlamasıdır.


---

## 17. Değişiklik kaydı — 2026-07-06 chain redesign: profil merdiveni senkronu

Python tarafında timeframe profil merdiveni yeniden tasarlandı (commit
`3c96029`, tek kaynak `data/timeframes.py` `PROFILES`). Pine v2.1 üçlü
(`profileMode` mapping) eski merdivene göre kalmıştı; bu sürümle senkronlandı.

| Profil | ESKİ (Pine v2.1) | **YENİ (PROFILES)** | Pine mapping (mtfTf / htfTf) |
|---|---|---|---|
| scalp | 5m / 1h / 12h | **5m / 1h / 4h** | `"60"` / `"240"` (htf 720→240) |
| mid | 15m / 1h / 4h | **15m / 4h / 12h** | `"240"` / `"720"` (mtf 60→240, htf 240→720) |
| long | 1h / 8h / 1w | **1h / 8h / 1d** | `"480"` / `"D"` (htf W→D) |

Rasyonel (Python tarafı): scalp SMC-yapıyı 1h'ta okur, trendi 4h'tan alır
(12h scalp için fazla atıl); mid'in yapı TF'i 1h→4h'e çıkarak HTF'siyle (12h)
orantılı hale geldi; long'un makro filtresi zaten Daily input'unda olduğundan
HTF 1w→1d'ye indi. Chain'ler kesin artan (entry < mtf < htf) — `resolve_timeframes`
bunu fail-fast doğrular.

Değişen satırlar: `efloud_signals.pine` (mapping satırları + başlık yorumu +
dashboard `chainStr`) ve `efloud_strategy.pine` (mapping satırları) — input
İSİMLERİ değişmedi, iki dosya senkron (§13 kuralı). `profEntry` (5/15/60)
değişmedi. Derleme: TradingView MCP bu oturumda erişilemediği için sıfır-hata
derleme + `pine_save` bir SONRAKİ masaüstü oturumunda yapılmalı (checklist:
tv_health_check → pine_set_source → pine_smart_compile → pine_get_errors →
pine_save; kullanıcının u2Algo_FVG-OTE script'ine DOKUNMA).


---

## 18. Değişiklik kaydı — 2026-07-06 (2): SL clamp ATR paritesi düzeltmesi — "hiç sinyal yok" bug fix

**Belirti:** Operatör TradingView grafiğinde indikatörün hiçbir LONG/SHORT
sinyali (△/▽) göstermediğini bildirdi.

**Kök neden:** `pine/efloud_signals.pine` + `pine/efloud_strategy.pine`
`calcSl()` fonksiyonu SL buffer'ı VE min/max clamp mesafesini gerçek
`ta.atr(14)` (`atr15`) üzerinden hesaplıyordu. Ama canlı Python motoru
(`safe_orchestrator.py:1960-1962`) `calc_sl()`'e gerçek ATR YERİNE bir proxy
besliyor: `atr_15m = max(entry_price * 0.01, |zone.high - zone.low|)`
(dokümante "DELIBERATE SIMPLIFICATION", `safe_orchestrator.py:1900-1903`).
`sl_calc.py` bu değeri hem buffer hem min/max clamp için kullanır (TF-agnostik
— hangi ATR'nin geleceğine karar vermez).

Proxy tipik olarak fiyatın ≥%1'i (veya zone genişliği) — gerçek 15m ATR'den
belirgin şekilde geniş. Chain redesign'den (3c96029, mid HTF 4h→**12h**) sonra
HTF swing anchor entry'den %3-15 uzaklaşınca: Python'un proxy-tabanlı clamp'i
bunu hâlâ kabul ediyordu, ama Pine'ın gerçek-ATR-tabanlı clamp'i (`max_sl_atr
× ATR(14)` ≈ fiyatın %1.5-2.5'i) SİSTEMATİK OLARAK reddediyordu → `calcSl` her
seferinde `na` dönüyordu → setup hiç `CONFIRMED`'e ulaşmıyordu → sıfır sinyal.
Scalp (4h anchor vs 5m ATR) ve long (1d anchor vs 1h ATR) profilleri de aynı
yapısal nedenle örtük olarak etkileniyordu — sadece mid'de en şiddetliydi.

**Fix (bu commit):** `calcSl`'de `atr15` yerine Python'un canlı kullandığı
proxy — `atrProxy = math.max(entry * 0.01, math.abs(zh - zl))` — buffer VE
min/max clamp için. `bufferMult` (V1-absorbe volatilite-hizalı çarpan, §16)
davranışı korunur; artık proxy tabanına uygulanır (Python'un canlı davranışına
birebir parite — "gerçek" ATR kullanmak Python'dan sapmaktı). Strategy
dosyasında artık kullanılmayan `atr15` yerel değişkeni temizlendi (kendi
değişikliğimin orphan'ı); `atrLen` input'u İKİ dosyada da korundu — ancak
gerekçesi dosyaya göre farklı: `efloud_signals.pine`'da dashboard'da (`ATR(14)`
satırı) hâlâ canlı tüketiliyor; `efloud_strategy.pine`'da artık HİÇBİR
fonksiyonel tüketicisi yok, sadece indikatör↔strateji input-isim senkronu
(§13) için tutuluyor (Pine unused input için hata vermez).

**Not:** Bu proxy Python tarafında dokümante bir geçici basitleştirme
("Real ATR threading is follow-up") — Pine bilinçli olarak CANLI davranışı
yansıtıyor, "doğru" tasarımı değil. Python'un ATR proxy'si gerçek ATR'ye
geçerse (follow-up PR), Pine'ın bu satırları AYNI oturumda güncellenmeli
(§13 senkron kuralı) — aksi halde parite tekrar bozulur.

**Sorumlu dosyalar:** `pine/efloud_signals.pine` (`calcSl`), `pine/efloud_strategy.pine`
(`calcSl` + `atr15` temizliği). Doğrulama: TradingView sıfır-hata derleme +
`pine_save` operatörün masaüstü oturumunda (bu oturumdan MCP erişimi yok).
Referans: `engine/smc_v2/sl_calc.py`, `engine/safe_orchestrator.py:1900-1903/1960-1962`.

---

## §19 — 2026-07-11 Python Değişiklikleri (Pine'a PORT BEKLİYOR)

1. **v3.2 Entry-anchored SMC TP targeting** (`engine/signals.py`,
   spec `docs/superpowers/specs/2026-07-11-tp-entry-anchored-targeting-and-bugfix-batch-design.md`):
   `smc_tp_targeting` blok havuzuna iki kaynak eklendi — (a) `RANGE_EQ`:
   entry-TF range EQ (0.50), entry doğru taraftaysa; (b) `LIQ_MTF` /
   `LIQ_MTF_EQ`: MTF swing + equal-level likiditesi. Canlı mid config artık
   `smc_tp_targeting: true, min_rr_tp1: 0.5, blended_rr_target: 1.5`.
   → Pine `calcTp` zinciri bir sonraki Pine oturumunda senkronlanmalı
   (indicator + strategy AYNI anda; input isimleri: smcTpTargeting,
   minRrTp1, blendedRrTarget).

2. **F10 — strategy state-reset fixi** (`efloud_strategy.pine`,
   `efloud_strategy_v1.pine`): `strategy.position_size == 0` koşulsuz reset'i
   entry barında SL/TP state'ini siliyordu (process_orders_on_close=true ile
   fill script SONRASI) → exit bloğu hiç kurulmuyordu. Reset artık yalnız
   open→flat geçişinde (`position_size[1] != 0`). Eski backtest sonuçları
   (bu fix öncesi) GEÇERSİZDİR — exit'siz koşuyorlardı.
