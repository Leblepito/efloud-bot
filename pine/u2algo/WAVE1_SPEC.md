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

## 7. T-003 Bölümü: Strateji + Backtest (DRAFT — R2 claim bekliyor)

**Dosya:** `pine/u2algo/wave1_strategy.pine` (~430 satır — T-003)

**İçerik (isklet):**
- [x] `strategy()` header (v6, 10000 capital, %100 equity, 0.04% commission)
- [x] indicator ile senkron: tüm input isimleri, palette, ATR, 1h bias, swing, OB, confluence, SL/TP
- [x] B1 repaint fix kalıbı uygulandı: 1h pivot `[3±j]`
- [x] `strategy.entry()` / `strategy.exit()` — limit entry + SL/TP1/TP2 exit
- [x] Pyramiding=1, `calc_on_every_tick=false`
- [x] Backtest input'ları: `bt_date_start`, `bt_date_end`, `bt_oos_pct`
- [ ] Backtest validasyonu: min 100 trade + %30 OOS (bekliyor)
- [ ] Repaint kontrolü: `barstate.isconfirmed` + gecikmeli pivot (bekliyor)
- [ ] WAVE1_SPEC.md final güncelleme (bekliyor)

**Derleme durumu:** `DRAFT — T-002 G-T2 compile PASS bekliyor`

| Tarih | Bölüm | Değişiklik | Yazar |
|---|---|---|---|
| 2026-06-10 | T-001 | İlk sürüm: swing + OB + 1h bias | @hermes |
| 2026-06-11 | T-002 | Confluence scoring + SL/TP + sinyal + görsel plot | @hermes |
| 2026-06-11 | T-002 | Review fix'leri: B1 repaint (1h pivot `[-j]`), B2 visual_group, N1 var, N3 %0.1 SL tabanı; §1 tablo güncellendi | @claude |
| — | T-003 | (bekliyor) | — |
