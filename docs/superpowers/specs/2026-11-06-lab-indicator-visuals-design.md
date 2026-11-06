# EFloud Lab indicator — SMC bölge görselleri (OB · BB · MB · FVG · likidite · OTE)

Tarih: 2026-11-06 · Branch: `claude/modest-archimedes-r70kle` · Durum: tasarım, operatör onayı bekliyor
Kaynaklar: ikinci görüş (`2026-11-06-lab-indicator-visuals-outline.fable-review.md`), BB/MB oran ölçümü (§3.2),
LuxAlgo "Pure Price Action Order & Breaker Blocks" ve DGT "Price Action – Support & Resistance" (yalnız kural sentezi, kod alınmadı).

## 1. Amaç ve kapsam

EFloud Lab **indicator**'ı grafikte botun gördüğü SMC bölgelerini okunur biçimde çizsin: Order Block (OB), Breaker Block (BB),
Mitigation Block (MB), Fair Value Gap (FVG), likidite havuzları (EQH/EQL, swing high/low; süpürülme durumu) ve sabit range üzerinde OTE.

- **Yalnız görüntü.** LONG/SHORT sinyalleri, alert JSON'u, aday durum makinesi, `core.pine` ve `tail_strategy.pine` **değişmez**;
  Python parity'si (`docs/pine-lab/2026-11-06-ilk-tur.md` §4b–4d) korunur. BB/MB'yi giriş bölgesi yapmak ayrı iştir (T2).
- Değişen dosyalar: `pine/lab/tail_indicator.pine`, `tests/test_pine_lab_build.py`, `scripts/pine_lab_parity.py` (yeni `visuals` alt komutu).
- Lisans: lab motoru LuxAlgo SMC portu (CC BY-NC-SA 4.0) → script private / invite-only, ticari kullanım yok. Dış kaynaklardan kod alınmaz.
- Kapsam dışı: kaldıraç likidasyon tahminleri, volume profile (POC/VAH/VAL), polarity-change işaretleri, FVG kısmi dolum, OTE geçmişi,
  strategy değişiklikleri, yayın.

## 2. Mimari

```
core.pine (değişmez)                              tail_indicator.pine (bu iş)
  swingObs / intObs  ──────────────────────▶  OB katmanı · Flip takipçisi (BB/MB)
  fvgs               ──────────────────────▶  FVG katmanı
  equals, shPiv/slPiv (swept) ─────────────▶  Likidite katmanı (+ hacim teyidi, bufVol tail'de)
  breaks (internal=false), OB.rawLow/rawHigh ─▶  OTE range durumu
  bufHi/bufLo/bufOpen/bufClose/bufTime ────▶  tek geçmiş veri kaynağı (history operatörü YOK)
```

Tail iki bloktan oluşur: **durum** (`if barstate.isconfirmed`, core bloğundan sonra) ve **çizim** (`if barstate.islast`: sil → yeniden kur).
Durum yalnız onaylı barda değişir (repaint yok). Gerçek-zamanlı bar bir range ucunu geçse de bar kapanana kadar hiçbir bölge değişmez.

Tail'in kendi kayıtları (core UDT'lerine alan eklenemez):

```
type Flip      // delinmiş OB → BB/MB
    OB    ob            // kaynak OB (referans; core prune etse de geçerli)
    float refA          // dondurulmuş swing pivot seviyesi (§3.2)
    float legExt        // (ob.idx, flipBar) aralığındaki uç (bear OB: min low; bull OB: max high)
    int   flipBar = -1  // delinme barı; -1 = henüz delinmedi
    int   cls = 0       // 0 bekliyor · 1 BB · 2 MB · 3 NONE (refA yok → çizilmez)
    bool  dead = false  // ters yönde delindi → çizimden kalkar
type Rng       // OTE range
    float h, l; int hBar, lBar; int dir  // 1 LONG (önce L sonra H) · -1 SHORT · 0 tanımsız
```

## 3. Katman kuralları

### 3.1 OB
- Kaynak: `swingObs` + `intObs`, `mitigatedIdx < 0` (botun aktif OB'leri). Kutu `[ob.bot(), ob.top()]`, x: `ob.idx → bar_index + 5`.
- Metin: `OB` (swing) / `iOB` (internal). Renk: yön rengi (bull/bear), swing kenar daha koyu.
- **Gövde/fitil toggle'ı** (`obBodyOnly`, varsayılan kapalı; LuxAlgo PPA'dan): açıkken kutu OB mumunun gövdesiyle çizilir
  (`max(open,close)`/`min(open,close)`, `bufOpen`/`bufClose`'dan). Yalnız görsel; core zone'u değişmez.
- Mitigated ama delinmemiş OB: flip olana kadar soluk (`alpha` yüksek), metin `OB ✓`. (Core'da ilk fitil temasında aktiflikten düşüyor;
  trader kutunun tepki anında kaybolmasını görmesin.) `showHistory` kapalıyken bu gösterim de kapalı.

### 3.2 BB / MB (Flip takipçisi) — iki ölçekli kural
Operatör onaylı. Ölçüm (Ocak–Kasım 2026, 15m, delinen OB'ler): taslak "bacak ucu" kuralı %98–99 BB verdi (dejenere);
iki ölçekli kuralla swing OB'ler %100 BB, internal OB'ler ~%50/50 BB/MB (BTC 678/634, ETH 662/633, SOL 624/621).

| Adım | Bear OB (→ bullish BB/MB); bull OB için ayna |
|---|---|
| Kayıt | Her onaylı barda havuzlarda `createdIdx == bar_index` olan OB'ler Flip kaydına alınır (havuzun sonundan geriye tarama). T2 koruması: aynı `idx` ve ters `bias` ile havuzda kaynak OB varsa bu bir breaker kopyasıdır → ne OB olarak çizilir ne kaydedilir. |
| Referans A | Kayıt anında `slPiv` içinde `bar < ob.idx` olan **son** swing-low pivotu (len 50). Dondurulur. Yoksa `cls = 3` (NONE), çizilmez. |
| Bacak ucu | `legExt = min(low)` aralığı `(ob.idx, flipBar)`: ilk kısım `(ob.idx, createdIdx]` kayıtta `bufLo`'dan bir kez okunur, sonra her onaylı barda güncellenir. |
| Delinme | `createdIdx` sonrası ilk onaylı barda `close > ob.top()` (kesin eşitsizlik). `mitigatedIdx` **filtre değildir**: her flip mitigated bir OB üzerinde olur. |
| Sınıf | `legExt < refA` → **BB**, değilse **MB** (sweep fitille sayılır; core `p.swept` ile aynı). |
| Kutu | Fiyat `[ob.bot(), ob.top()]` (veya gövde), x: `ob.idx → bar_index + 5`. Renk ve yön **yeni yön** (bear OB'den doğan BB/MB bull rengi). Metin `BB` / `MB`. |
| Pasifleşme | Flip sonrası ilk `close < ob.bot()` (bullish BB/MB için) → `dead`, çizimden kalkar. Prune: core kuralıyla (`createdIdx < bar_index − liveWindowBars`). |

Sezgisel özet: delinmeden önce fiyat OB'den önceki swing dibini süpürdüyse **BB**, süpürmeden (higher low) döndüyse **MB** (ICT "failure swing").
LuxAlgo PPA'nın "mitigated OB = breaker" tanımı bizim BB koluyla örtüşür; MB bunun üstüne gelen ayrımdır.

### 3.3 FVG
- Kaynak: `fvgs`, `mitigatedIdx < 0`. Kutu `[f.bot, f.top]`, x: `f.idx → bar_index + 5`, ince, yüksek şeffaflık, metin `FVG`.

### 3.4 Likidite havuzları
- Kaynak: `equals` (EQH/EQL: `priceB`, `idxB`) ve `shPiv`/`slPiv` (BSL/SSL: `price`, `bar`), `swept` bayrağı core'dan.
- Çizgi `x1 = oluşum barı`; süpürülmemiş: `x2 = bar_index + 5`, düz, **nötr renk** (likidite yön değil hedeftir). Süpürülmüş: `x2 = sweep barı`
  (çizim anında `bufHi`/`bufLo` taranarak bulunur), kesikli, soluk; yalnız `showHistory` açıkken, son 5.
- Metin: en yakın 10 için kısa label (`EQH`/`EQL`/`BSL`/`SSL`); fazlası yalnız çizgi.
- **Hacim teyidi** (`liqVolumeConfirm`, varsayılan açık; DGT kuralından sentez): seviyenin oluştuğu bara biten hareket, aynı yönde ≥ 3 ardışık
  bar ve hacmi her barda artan ise ve son barın hacmi `ta.sma(volume, 60)` üstündeyse çizgi kalın, etiket `★` ekli. Hacim ve SMA global satırda
  her barda hesaplanıp tail'in `bufVol`/`bufVolMa` ring buffer'larına yazılır; teyit çizim anında buffer'dan okunur. `volume` na ise teyit kapalı.

### 3.5 OTE — sabit range
- **Başlangıç:** ilk swing kırılımına kadar range tanımsız (`dir = 0`), çizilmez.
- **Yeni range:** swing kırılım barında (`Brk.internal == false`, `idx == bar_index`): `L = min(ob.rawLow, low)`, `H = max(ob.rawHigh, high)`
  (kırılan pivot barından kırılım barına kadar olan impuls bacağı; `b.ob` na ise `L = swingLow.level`, `H = swingHigh.level`).
  `lBar`/`hBar` ilgili ucun barı (`rawLow`/`rawHigh` için core bar indeksi tutmadığından `bufLo`/`bufHi` taranarak bulunur).
  Aynı barda iki swing kırılımı olursa sonuncusu (core sırası: bear) kazanır. Internal kırılımlar range'i **değiştirmez**.
- **Uzama:** yalnız onaylı barda, fitille: `high > H → H := high, hBar := bar_index`; `low < L → L := low, lBar := bar_index`.
  Range içindeki barlar hiçbir şeyi değiştirmez.
- **Yön:** `hBar > lBar → LONG`, `hBar < lBar → SHORT`, `hBar == lBar` (outside bar) → önceki yön korunur.
- **Seviyeler:** `R = H − L`; LONG: band `[H − 0.786R, H − 0.618R]`, 0.705 = `H − 0.705R`; SHORT: band `[L + 0.618R, L + 0.786R]`,
  0.705 = `L + 0.705R`; EQ = `L + 0.5R`. `R < 2 × syminfo.mintick` → çizilmez.
- **Çizim:** kutu (band, çok şeffaf, metin `OTE LONG`/`OTE SHORT`), 0.705 çizgisi, EQ çizgisi, ince H/L çizgileri; x: `min(hBar,lBar) → bar_index + 5`.
  Yalnız güncel range; geçmiş OTE yok.
- Botun `f_tags` OTE'si trailing range'e bağlıdır ve ayrı kalır; dashboard'daki "Range EQ" trail EQ'dur, OTE satırı ayrı gösterilir.

## 4. Çizim bütçesi, z-order, inputs

- `indicator()` başlığı: 500 box / 500 line / 500 label (TV aşılınca **en eski** nesneyi siler → sinyal çizgileri kaybolur).
- **Mevcut hata düzeltilir:** `maxDrawings` `maxval 150` (→ 600 çizgi) **100**'e çekilir.
- Z-order (`islast` kurulum sırası, alttan üste): OTE → FVG → OB/iOB → BB/MB → likidite → bekleyen zone'lar → sinyal çizgileri/label'ları.
- Seçim: "fiyata en yakın N, yön başına" (`maxZonesPerSide`, varsayılan 8; mesafe = yakın kenar − close) OB, BB/MB ve FVG için ortak,
  iki geçişli tarama (tam sıralama yok). Likidite: en yakın 10 süpürülmemiş + son 5 süpürülmüş (sabit). Doğrulamada N geçici 200.
- Bütçe (varsayılanlar): box ≈ OB 16 + BB/MB 16 + FVG 16 + OTE 1 + zone ≤ 6 ≈ 55; line ≈ sinyal 4×`maxDrawings` (≤ 400) + likidite 15 + OTE 4;
  label ≈ sinyal ≤ 100 + likidite ≤ 10. Kutu metinleri label harcamaz.
- Dashboard: `table.new(... 2, 9)` (7 → 9 satır): `Zones s/i·BB·MB·FVG·Liq` sayaç satırı ve `OTE: LONG H=… L=…` satırı.

Yeni input'lar (yalnız indicator; `INDICATOR_ONLY_INPUTS` güncellenir):
`showBreakers`, `showFvg`, `showLiq`, `showOte`, `showHistory`, `obBodyOnly`, `liqVolumeConfirm`, `maxZonesPerSide`,
`colBull`, `colBear`, `colNeutral`, `zoneAlpha`. Mevcut `showObs/showZones/showLevels/showDash/maxDrawings` kalır.
Kesilenler (YAGNI): katman başına renk, ayrı `showBb/showMb`, ayrı `maxObDraw/maxFvgDraw/maxLiqDraw`, OTE geçmişi, polarity-change, volume profile.

## 5. Pine v6 kuralları (yeni kod için)
1. Tail fonksiyonlarında **`x[off]` ve `ta.*` yasak** (koşullu çağrıda fonksiyonun çağrı geçmişini okur; `f_storeOb` hatası).
   Geçmiş yalnız global ring buffer'lardan okunur (core: `bufPHi/bufPLo/bufHi/bufLo/bufOpen/bufClose/bufTime`, kapasite `bufCap = 992`;
   tail: `bufVol/bufVolMa`). İndeks sözleşmesi: tail'in `isconfirmed` bloğu core'dan sonra çalışır → buffer'ın son elemanı
   **mevcut onaylı bar**; bar `i` → indeks `size − 1 − (bar_index − i)`. `ta.sma(volume, 60)` yalnız global satırda hesaplanır.
2. Tail durumu global `var`'larda; fonksiyon içi `var` yok. Bacak ucu/sweep gibi bilgiler geçmiş okumayla değil, her onaylı barda güncellenen alanlarla tutulur.
3. Flip/Rng kayıtları prune edilir; `array.size` artışına güvenilmez (`createdIdx == bar_index` taraması).
4. Çizim fonksiyonlarında if/else dal tipleri karışıyorsa açık dönüş değeri (`true`) verilir.
5. Statik test: `tests/test_pine_lab_build.py`'ye tail'deki her `f_*` gövdesinde history operatörü (`\b\w+\[\s*\w`) ve `ta\.` bulunmadığını doğrulayan test.

## 6. Doğrulama planı
1. **Statik:** `python scripts/build_pine_lab.py --check`; `pytest tests/test_pine_lab_build.py tests/test_pine_lab_parity.py`;
   `git diff --exit-code pine/lab/core.pine pine/efloud_lab_strategy.pine` (bayt bayt aynı → "core/strategy değişmedi" kanıtı).
2. **Derleme:** `pine_set_source` (CLI `pine set --file`) → `pine_smart_compile` → `pine_get_errors` = 0; runtime hatası için derleme konsolu
   (`pine_get_console`) ve ekran görüntüsü (`ui_evaluate` SKILL gereği kullanılmaz). BTC/ETH/SOL 15m + stres TF (1m, en uzun geçmiş).
3. **Katman izolasyonu:** `indicator_set_inputs` ile her ölçümde tek katman açık, `maxZonesPerSide = 200`; `data_get_pine_boxes` / `lines`
   / `labels`, `study_filter = "EFloud Lab"`.
4. **Python beklentileri:** yeni alt komut `scripts/pine_lab_parity.py visuals --ohlcv <csv> --out expected.json`: aynı CSV'nin son 750 barında
   `lx.analyze()` → aktif OB (`internal` ayrı), aktif FVG, likidite (equals + swing pivotları, `swept` core kuralıyla, hacim teyidi DGT kuralıyla)
   **ve** BB/MB (§3.2) + OTE (§3.5) için saf-fonksiyon referansları (~80 satır). Karşılaştırma: `mintick` toleranslı küme eşitliği, precision/recall;
   pencerenin ilk `2×swingLen` barı (ısınma) hariç. Eşik: OB/FVG/likidite ≥ %98, BB/MB/OTE = %100.
5. **Dashboard sayaçları** `data_get_pine_tables` ile Python sayılarına karşı (duman testi).
6. **Sinyal regresyonu:** yeni katmanlar OFF ve ON iken `data_get_pine_labels` sinyal kümesi (`LONG `/`SHORT ` önekli) birebir aynı; alert JSON'u değişmez.
7. **Görsel kontrol listesi** (`capture_screenshot`): metinler okunuyor, z-order doğru, OTE yönü dashboard'la aynı, süpürülmüş çizgi sweep barında bitiyor,
   hacim teyitli seviyeler kalın.
8. (NICE) Repaint: `replay_start` → ~100 `replay_step` → kutular, aynı bara kesilmiş CSV'de Python beklentisiyle karşılaştırılır.

## 7. Uygulama sırası (plan için)
1. Bütçe düzeltmesi (`maxDrawings` 100) + dashboard 9 satır + yeni input'lar + statik test → derleme.
2. FVG ve likidite katmanları (core verisi, durum yok) + `bufVol/bufVolMa` ve hacim teyidi.
3. OB gövde toggle'ı + mitigated-soluk gösterimi.
4. Flip takipçisi (BB/MB) + T2 koruması.
5. OTE range durumu + çizimi.
6. `visuals` alt komutu (Python referansları) + TV doğrulama koşuları + sinyal regresyonu.
7. PINE_SPEC §21 "indicator görselleri" notu, README güncellemesi.

## 8. Riskler
- `barstate.islast` döngü maliyeti düşük TF + uzun geçmişte; "en yakın N" iki geçişli tarama ile, test 2'de 1m stres koşusu.
- Hacim teyidi `volume` olmayan sembollerde kapalı; DGT kuralı sezgisel, parity hedefi yok (yalnız Python referansıyla birebir).
- OTE range'i trail range'ten farklı; iki EQ karışıklığı dashboard satırlarıyla ayrıştırılır.
- T2 açıkken breaker kopyası koruması tek satır; test 4'te T2 ON senaryosu da koşulur.
