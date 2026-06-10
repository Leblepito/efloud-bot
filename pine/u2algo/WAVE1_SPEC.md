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
| `sl_atr_mult` | 0.5 | — (T-002) | — | T-002'de eklenecek |
| `sl_lookback` | 20 | — (T-002) | — | T-002'de eklenecek |
| `min_rr` | 1.5 | — (T-002) | — | T-002'de eklenecek |
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

**Dosya:** `pine/efloud_signals.pine` (259 satır, 11.9 KB)

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

**Derleme durumu:** `IMPL_READY, awaiting compile-verify` (VPS'te TradingView yok)

---

## 6. Revizyon Geçmişi

| Tarih | Bölüm | Değişiklik | Yazar |
|---|---|---|---|
| 2026-06-10 | T-001 | İlk sürüm: swing + OB + 1h bias | @hermes |
| — | T-002 | (bekliyor) | — |
| — | T-003 | (bekliyor) | — |
