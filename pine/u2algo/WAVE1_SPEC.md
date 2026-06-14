# WAVE1_SPEC — u2algo Wave-1 Python → Pine v6 Çeviri Haritası (P-001)

> u2algo Wave-1 indikatörünün (`pine/u2algo/wave1_signals.pine`) çeviri kararları.
> Son güncelleme: 2026-06-10 — T-001 (+ Claude review düzeltmeleri)
>
> ⚠️ `pine/PINE_SPEC.md` ve `pine/efloud_signals.pine` (SMC v2 sadık port,
> compile-verified 2026-05-30) AYRI üründür — bu spec onları kapsamaz.

---

## 1. Parametre Eşleme (Python → Pine Input)

| Python Parametresi | Python Default | Pine Input | Pine Default | Not |
|---|---|---|---|---|
| `swing_lookback` | 4 | `swing_lb_left/right` (hardcoded) | 4 | Pine `ta.pivothigh` simple-int gerektirir; manuel pivot detection kullanıldı |
| `ob_sequential` | 5 | `ob_seq_default` (hardcoded) | 5 | Pine for-loop sabit sayı ister |
| `ob_body_atr_mult` | 1.5 | `ob_body_mult` (`input.float`) | 1.5 | ✅ Dinamik input |
| `confluence_threshold` | 55 | `conf_thresh` (`input.int`) | 55 | T-002'de kullanılacak |
| `sl_atr_mult` | 0.5 | `sl_atr_m` (`input.float`) | 0.5 | ✅ T-002 |
| `sl_lookback` | 20 | `sl_lb` (`input.int`) | 20 | ✅ T-002 |
| `min_rr` | 1.5 | `min_rr` (`input.float`) | 1.5 | ✅ T-002 (live-prod: 1.8) |
| `fib_tp2` | 1.618 | `fib_tp2` (`input.float`) | 1.618 | ✅ T-002 |
| `min_sl_dist_pct` | 0.1% | `min_dist` içinde `0.001*entry` tabanı | 0.1% | ✅ T-002 review fix (N3) — ATR tabanıyla max() |
| — | — | `show_sltp` (`input.bool`) | true | T-002 görsel toggle |
| `body_mode` | True | `true` (hardcoded) | true | OB hesaplamada open/close referans; Pine'da body-mode zorunlu |

---

## 2. Live-Prod Değerleri (Plan §3d Claude Review Notu)

> Pine input **DEFAULT'ları** plan §3d referans değerleridir.
> Canlı prod tuning farkları aşağıdadır. Operatör input'tan değiştirebilir.

| Parametre | Plan Default | Live Prod | Açıklama |
|---|---|---|---|
| `conf_thresh` | 55 | **80** | Prod'da daha sıkı confluence filtresi |
| `min_rr` | 1.5 | **1.8** | Prod'da daha yüksek R:R eşiği |
| `ob_body_mult` | 1.5 | 1.5 | Aynı |
| `swing_lb` | 4 | 4 | Aynı |
| `ob_seq` | 5 | 5 | Aynı |

---

## 3. Çeviri Kararları

### 3a. Swing Detection (T-001)

- **Python:** `all(h[i] > h[i-j] and h[i] > h[i+j] for j in range(1, lb+1))`
- **Pine:** Manuel for-loop ile her bar için sol+sağ karşılaştırma. `ta.pivothigh()` simple-int istediği için kullanılamadı.
- **Karar:** `high[lb]` referans noktası, `lb` sol + `lb` sağ bar karşılaştırması. Sadece `barstate.isconfirmed` altında değerlendirilir.
- **Repaint koruması:** Değerlendirme `lb` bar gecikmeli (sağdaki `lb` barın da kapanması beklenir). Label `bar_index - lb` konumunda.

### 3b. Order Block Detection (T-001)

- **Python:** Son `ob_seq` ardışık ters yönlü mum + breakout mum gövdesi > 1.5×ATR(14)
- **Pine:** Aynı mantık. `for k = 1 to ob_seq_default` ile geriye dönük tarama.
- **Body mode:** Python'da `body_mode=True` default. Pine'da open/close ile gövde hesabı.
- **Swing proximity:** Son swing'e 30 bar mesafe + %1.5 fiyat yakınlığı kontrolü.
- **Görsel:** `box.new()` ile OB bölgesi çizimi.

### 3c. 1h Bias (T-001)

- **Python:** 1h timeframe'de `analyze()` → trend (CHoCH/BOS tabanlı). Karmaşık yapı kırılımı mantığı.
- **Pine (Wave 1 basitleştirme):** `request.security(sym, "60", ...)` ile 1h EMA20 eğimi. `lookahead=barmerge.lookahead_off` ile repaint önlendi.
- **Karar:** Wave 1 için EMA20 yeterli. Wave 2'de tam CHoCH/BOS yapısı eklenecek.

### 3d. Repaint Politikası

| Kural | Uygulama |
|---|---|
| Tüm sinyaller `barstate.isconfirmed` altında | ✅ |
| `request.security()` → `lookahead=barmerge.lookahead_off` | ✅ |
| Higher-TF değerler sadece kapanmış bar'dan | ✅ |
| Swing detection `lb` bar gecikmeli (sağ pencere kapansın diye) | ✅ |
| Tarihsel bar referansları `[N]` (look-ahead yok) | ✅ |

---

## 4. Pine v6 Uyumluluk Matrisi

| Özellik | v6 Kullanım | Legacy (KULLANILMAZ) |
|---|---|---|
| Script tipi | `indicator()` | ~~`study()`~~ |
| ATR | `ta.atr(14)` | ~~`atr(14)`~~ |
| EMA | `ta.ema(src, 20)` | ~~`ema(src, 20)`~~ |
| Box | `box.new()` | — |
| Label | `label.new()` | — |
| Table | `table.new()` / `table.cell()` | — |
| Color | `color.new(hex, transp)` | — |
| Input | `input.int/float/bool()` | — |
| Alert | `alertcondition()` | — |

---

## 5. T-001 Bölümü: Swing + OB Core

**Dosya:** `pine/u2algo/wave1_signals.pine` (301 satır, 12.4 KB — T-001)

**İçerik:**
- [x] `indicator()` header (v6, overlay)
- [x] Parametre input'ları (§3d): `ob_body_mult`, `conf_thresh`, `use_cb_palette`
- [x] Renk paleti (§4a + §4b): koyu tema + renk körü alternatif input flag
- [x] ATR(14) hesaplama
- [x] 1h bias: `request.security("60", ...)` + EMA20 eğimi
- [x] Swing High/Low detection: manuel pivot, lookback=4, `barstate.isconfirmed`
- [x] Order Block detection: bullish + bearish, `box.new()` görsel
- [x] Swing label'ları: "HH" / "LL"
- [x] 1h bias table: sağ üst köşe
- [x] Alert stub'ları (T-002 dolduracak)

**Derleme durumu:** `DONE` (T-001 tamamlandı, T-002'ye geçildi)

---

## 6. T-002 Bölümü: MTF Confluence + SL/TP

**Dosya:** `pine/u2algo/wave1_signals.pine` (608 satır, 26.6 KB — T-002)

**Eklenenler (v1.1.0):**
- [x] Input'lar: `sl_lb`, `sl_atr_m`, `min_rr`, `fib_tp2`, `show_sltp`
- [x] Confluence scoring (7 faktör, 0-100): OB (+30), OB near swing (+15), strong breakout (+10), 1h bias aligned (+20), EMA slope (+10), FVG (+5), recent swing break (+10)
- [x] 1h swing level detection (lookback=3 HTF pivot, TP1 hedefi)
- [x] SL hesaplama: `f_calc_sl()` — son 20 mum ekstremi + ATR(14)×0.5 buffer, 0.5-5.0×ATR clamp
- [x] TP hesaplama: `f_calc_tp()` — TP1=1h swing/15m swing, TP2=Fib(1.618) extension, fallback min_rr
- [x] Sinyal üretimi: `long_signal`/`short_signal` — confluence >= threshold + 1h bias alignment
- [x] Görsel plot: SL (orange-red dashed 2px), TP1 (green dashed 1px), TP2 (blue dashed 1px), entry label (score %), entry zone box
- [x] Alert condition'ları sinyal değişkenlerine bağlandı

**Derleme durumu:** `IMPL_READY, awaiting compile-verify` (VPS'te TradingView yok)

**T-002 review notları (@claude, 2026-06-11 — REQUEST_CHANGES → fix'ler uygulandı):**
- **B1 (repaint, BLOCKING):** 1h pivot tespitinde `[-j]` gelecek-bar erişimi vardı —
  TP1 hedefleri repaint ederdi (R-002'nin tam uyarısı). 15m'deki gecikmeli-pivot
  kalıbına çevrildi: aday `htf_high[3]`, komşular `[3±j]`, onay 3 bar gecikir.
- **B2 (compile, BLOCKING):** `visual_group` forward-reference — tanım yukarı taşındı.
- **N3:** referans spec'in min %0.1 SL mesafe tabanı eklendi (`max(0.5×ATR, 0.001×entry)`).
- **N2/N4 (kabul edilen sadeleştirmeler):** `prev_swing_*` en SON swing'i tutar (önceki
  değil) — TP2 swing_range'i eşleşmemiş high/low çiftinden gelebilir; "strong breakout"
  (+10) OB body koşuluyla korele — efektif bağımsız faktör sayısı ~6. İkisi de Wave-1
  kapsam kararı; T-003 backtest'i bozarsa revize edilir.

---

## 7. T-003 Bölümü: Strateji + Backtest (R1+R3 konsensüs — 2026-06-11)

**Dosya:** `pine/u2algo/wave1_strategy.pine` (622 satır, ~28 KB — T-003, 5 patch: round-1 + limit-expiry + round-3 + alert + gate-raporu)

**SENKRON kuralı (Plan v1.4 §8a.3):** Bu dosyadaki tüm input isimleri + default değerler `wave1_signals.pine` (indicator) ile aynı olmak ZORUNLU. Yeni input'lar (aşağıdaki R1+R3) 3 dosyaya birlikte uygulanır.

### 7a. R1 — Sinyal Mantığı Gevşetme (Plan v1.4 §8a.2)

**Kök neden:** §2a kombinasyonu (5-ardışık-ters-mum × 1.5×ATR × ≤5-bar pencere × bias × conf≥55) 15m'de nadir.

| Input | Tip | Default | Açıklama |
|---|---|---|---|
| `ob_active_window_bars` | `input.int(15, ..., minval=1, maxval=50)` | 15 | OB-aktif penceresi (eski: hardcoded 5). 3× daha uzun hafıza. |
| `allow_ob_less` | `input.bool(false, ...)` | false | true: OB-aktif ön koşulu kaldırılır; sinyal `conf_thresh + 1h bias + (swing_break OR strong_breakout)`'a iner. OB confluence'a +30 verir ama zorunlu değil. |

**Sinyal mantığı (R1 sonrası):**
```
long_signal  := barstate.isconfirmed AND
                confluence_score_long >= conf_thresh AND
                htf_bias_up AND
                ( (allow_ob_less AND (recent_higher_high OR (bar_body > 2.0*atr14)) ) OR
                  (NOT allow_ob_less AND bullish_ob_active) )
```

### 7b. R3 — Fill Güvenilirliği Artışı (Plan v1.4 §8a.2)

| Input | Tip | Default | Açıklama |
|---|---|---|---|
| `limit_expiry_bars` | `input.int(40, ..., minval=10, maxval=100)` | 40 | Limit-entry expiry (eski: hardcoded 20). 15m'de 40 bar = 10 saat. |
| `extended_expiry_in_trend` | `input.bool(false, ...)` | false | true: 1h bias aligned durumda expiry 80 bar (20 saat). Range/flat'te 40 bar. |

**Limit-expiry + cancel mantığı (R3 sonrası, R5+F5+F6 round-3 fix'leri korunur):**
- F5 (karşı-yön cancel): `if is_in_trade AND (sig_entry_bar_long > 0 OR sig_entry_bar_short > 0)` → her iki yöne `strategy.cancel`
- F6 (pending gate): sinyal üretimi `... AND sig_entry_bar_long == 0 AND sig_entry_bar_short == 0`
- R3 expiry: `if sig_entry_bar_long > 0 AND not is_in_trade AND (bar_index - sig_entry_bar_long) > limit_expiry_bars` (veya 80 bar trend'de)

### 7c. Çoklu-Sembol Gate Re-Run (Plan v1.4 §8a.5)

Gate run 1 (BTCUSDT.P/ETHUSDT.P 15m, ~4.3 ay) → trade_count=0. R1+R3 sonrası:
- Semboller: BTCUSDT-PERP, ETHUSDT-PERP, SOLUSDT-PERP, BNBUSDT-PERP, XRPUSDT-PERP
- TF: 15m
- Period: 2026-01-26 → 2026-06-11 (~4.3 ay TV 15m derinliği)
- Beklenen: 5 × ~120 trade = 600 trade (min 100 kolay geçilir)

### 7d. Limit-fill Intrabar Caveat (F4 — round-3'ten korunur, genişletildi)

Strategy(`calc_on_every_tick=false`) bar kapanışında hesaplanır. Limit order bar İÇİNDE fill olursa backtest aynı bar'ın high/low'unu aynı anda kullanır — gerçek hayutta fill sırası belirsizdir. R3 expiry uzatması (20→40 bar) bu riski AZALTIR (daha fazla bar'da fill olma şansı, bar-içi yarış durumunu seyreltir) ama tamamen ortadan kaldırmaz. Güven aralığı: OOS Sharpe × 0.7 → gerçekte 0.5-0.6'ya düşebilir. Risk_pct=0.5% default muhafazakâr.

## 8. Revizyon Geçmişi

| Tarih | Bölüm | Değişiklik | Yazar |
|---|---|---|---|
| 2026-06-10 | T-001 | İlk sürüm: swing + OB + 1h bias | @hermes |
| 2026-06-11 | T-002 | Confluence scoring + SL/TP + sinyal + görsel plot | @hermes |
| 2026-06-11 | T-002 | Review fix'leri: B1 repaint (1h pivot `[-j]`), B2 visual_group, N1 var, N3 %0.1 SL tabanı; §1 tablo güncellendi | @claude |
| 2026-06-11 | T-003 §7a-§7d | R1 sinyal gevşetme (ob_active_window_bars=15, allow_ob_less) + R3 fill güvenilirliği (limit_expiry_bars=40, extended_expiry_in_trend) + çoklu-sembol gate notu + F4 caveat genişletme. SENKRON kuralı 3 dosyaya | @claude (R1+R3 konsensüs, Plan v1.4) |
| 2026-06-13 | INDICATOR §9 | v1.2.0 round-6 detektör portu (OB/Breaker zone + FVG + EQH/EQL likidite) + RE10045 runtime by-pass (tamamen inline, UDF yok) → **indicator-only ship** | @claude |

## 9. INDICATOR v1.2.0 — Round-6 Detektör Portu + RE10045 By-pass (2026-06-13)

**Dosya:** `pine/u2algo/wave1_signals.pine` (527 satır). **Karar:** GATE_RUN_4-prelim NO-GO sonrası
(strateji shippable değil), lead-magnet **indicator-only** ship edilir. Indicator'ın değeri
**görsel SMC tespiti** (zone/likidite/FVG/breaker + SL/TP görseli) — kompleks engine-TP değil.

### 9a. Port edilen round-6 detektörleri (strategy SENKRON)
- **OB + Breaker zone array** (engine smc.py:200-256): OB tespiti → `ob_top/bot/dir/bar/brk` array; close zone'dan geçince yön flip + "BB" breaker etiketi. OB kutuları çizilir.
- **FVG array + mitigation** (engine smc.py:38-44): `low>high[2]` / `high<low[2]`; mitigation takibi; FVG kutuları çizilir.
- **EQH/EQL likidite** (engine smc.py pairwise): swing array'lerinden eşit-seviye (±%0.1) tespiti; son bar'da turuncu likidite çizgileri (max 8'er).
- Swing (HH/LL), 1h EMA20 bias, confluence (7-faktör 0-100), 1h swing (B1 repaint-fix) — T-001/T-002'den korundu.

### 9b. ⚠️ RE10045 RUNTIME HATASI — KÖK NEDEN + BY-PASS
İlk port (strategy'nin user-defined fonksiyonlarını — `f_engine_tp`/`f_nearest_zone`/`f_calc_sl`/`f_eq_levels` — birebir kullanan) TV'de **compile PASS (0 hata) ama RUNTIME `RE10045`** verdi (chart'ta kırmızı "!", hiçbir çizim render olmuyor). Sistematik bisect ile lokalize edildi:

| Test | Sonuç |
|---|---|
| Tüm çizimler kaldırıldı (sadece hesaplama) | ❌ RE10045 — hata çizimde değil |
| `max_bars_back=500` eklendi | ❌ RE10045 |
| Sinyal bloğu son-bar'a gate'lendi | ❌ RE10045 (kümülatif çağrı değil) |
| `g_eqh` var-array reassign → strategy-internal pattern | ❌ RE10045 |
| **Engine fonksiyon ÇAĞRILARI kaldırıldı** | ✅ **TEMİZ** → hata UDF'lerde |
| `f_calc_sl` / `f_engine_tp`+`f_eq_levels` / `f_nearest_zone` **izole tek tek** | ✅ üçü de TEMİZ |

**Bulgu:** Üç UDF de izole TEMİZ; hata YALNIZ üçü + gerçek detection tam-script bağlamında birlikteyken. `RE10045` TradingView'de dokümante DEĞİL (Pine docs sadece RE10139=memory, RE10143=historical-buffer listeler). Tam-script ölçeğinde UDF+collection etkileşimine bağlı bir Pine iç limiti olduğu değerlendirildi.

**By-pass:** Indicator **tamamen inline** yazıldı — **user-defined function YOK**. Sinyal SL/TP sadeleştirildi:
- entry = en yakın aktif OB|BB near-edge (inline tarama, aday-array yok)
- SL = `ta.lowest/ta.highest(±sl_lb) ± ATR buffer` (her bar; N3 %0.1 taban korundu)
- TP1 = en yakın 1h swing (RR sağlıyorsa) yoksa RR-projeksiyon; TP2 = fib(1.618) projeksiyon
- Çok-adaylı engine-TP (EQH/EQL+FVG-aday seçimi) DROP edildi → bu strategy'ye özgü; lead-magnet için 1h-swing+RR yeterli.

### 9c. SENKRON durumu (divergence dokümante)
- ✅ Input isimleri + default'lar strategy ile AYNI (`ob_body_mult`, `conf_thresh`, `sl_lb`, `sl_atr_m`, `min_rr`, `fib_tp2`, `ob_active_window_bars` + görsel toggle'lar).
- ✅ Detektörler (OB/Breaker/FVG/EQH-EQL/swing/confluence/1h-bias) strategy ile AYNI mantık.
- ⚠️ **Divergence:** indicator sinyal SL/TP = sadeleştirilmiş inline; strategy = çok-adaylı engine-TP UDF'leri. Lead-magnet kapsam kararı (strateji shelved/NO-GO).
- ⚠️ **Strateji notu:** strategy aynı UDF'leri kullanıyor → güncel TV'de RE10045 verip vermediği DOĞRULANMALI (eğer veriyorsa GATE_RUN verileri yeniden-değerlendirilmeli). Strateji zaten NO-GO/rafta — düşük öncelik.

### 9d. Yayın (publish)
TV publish = MANUEL operatör adımı (MCP publish otomasyonu kırık, bkz. [[reference_tradingview_mcp_launch]]). Pine TV cloud'a kaydedildi (`pine_save`). Repo source-of-truth: `pine/u2algo/wave1_signals.pine`.
