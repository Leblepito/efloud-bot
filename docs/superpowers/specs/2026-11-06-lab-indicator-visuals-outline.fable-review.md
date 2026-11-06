# İkinci görüş — Lab indicator SMC bölge görselleri (outline review)

> Kapsam: `2026-11-06-lab-indicator-visuals-outline.md` + `pine/lab/core.pine`, `pine/lab/tail_indicator.pine`,
> `pine/u2algo/wave1_signals.pine` (yalnız çizim fikri), `engine/smc_v2/luxalgo.py`. Bu dosya outline'ı **düzenlemez**; eklemedir.
> Etiketler: **MUST** = spec'e girmeden onaylanmalı / yoksa hata ya da yanlış görsel · **SHOULD** = güçlü öneri · **NICE** = sonraya bırakılabilir.

---

## 1. Tanımların doğruluğu

### 1.1 BB / MB — outline'daki `rawLow`/`rawHigh` kuralı neredeyse hep aynı sonucu veriyor

**Tespit (MUST):** LuxAlgo OB'si yalnız bir kırılımda oluşuyor. Bear OB, kapanış pivot low'un altına indiğinde
(`close < swingLow.level`) oluşur. OB mumu `[pivotBar, break)` aralığındaki en yüksek mum. Yani ICT dilindeki A (dip) → B (OB tepesi) → C
dizisinde C **her zaman** A'nın altında kapanmış oluyor. Kırılan pivota göre bakılırsa her delinen Lux OB'si tanım gereği **Breaker**
olur, MB hiç çıkmaz.

Outline'daki `rawLow` referansı bunu düzeltmiyor:
- `rawLow = min(low[pivotBar … createdIdx-1])` ≤ pivot seviyesi (aralık pivot barının kendisinden başlıyor).
- Kırılım barında `low < close < pivot seviyesi`.
- Takipçi kırılım barını içeriyorsa sweep neredeyse her zaman doğru çıkar: BB ≈ %100.
- Takipçi kırılım barını içermiyorsa kural "kırılımdan sonra fiyat bir bar daha uzadı mı?" sorusuna dönüşür. Bu da geçerli
  kırılımların çoğunda doğru; MB yalnızca "kırıp hemen dönen" (SFP benzeri) durumda çıkar. Bu, ICT'nin MB'si değil.
- Outline "oluştuktan sonraki uç" diyor ama başlangıç barını (`idx` mi, `createdIdx` mi, dahil mi) söylemiyor. Sonuç buna göre değişiyor.

**Öneri (MUST — operatör kararı, sessizce seçilmesin):** referansı iki ölçekli yap. MB'yi anlamlı kılan tek tanım bu:

| Adım | Kural (bear OB → bullish BB/MB; bull OB için ayna) |
|---|---|
| Referans A | OB kaydedildiği barda (`createdIdx`), `slPiv` içinde `bar < ob.idx` olan **son** swing-low pivotu (len 50). Kayıt anında **dondurulur** (sonradan onaylanan pivotlar değiştirmez). Yoksa → sınıf `NONE`, çizilmez. |
| Bacak ucu | `legExt = min(low)` aralığı `(ob.idx, flipBar)`, yani OB mumundan sonraki bardan flip barından önceki bara kadar. İlk kısım `(ob.idx, createdIdx]` kayıtta `bufLo`'dan **bir kez** okunur, sonra her onaylı barda güncellenen bir alanda tutulur. |
| Delinme (flip) | `createdIdx` sonrası ilk onaylı barda `close > ob.top()` olması (bull OB: `close < ob.bot()`), kesin eşitsizlik. `mitigatedIdx` dikkate alınmaz (bkz. 1.3). |
| Sınıf | `legExt < A.price` → **BB**, değilse → **MB**. Sweep fitille sayılır (core'daki `p.swept`'teki `low < price` ile aynı). |
| Kutu | Fiyat `[ob.bot(), ob.top()]` (parsed kenarlar, OB kutusuyla aynı). X: `ob.idx → bar_index + k`. Yön ve renk **yeni yön** (bear OB → BB/MB teal). |
| Pasifleşme | Flip sonrası ilk `close < ob.bot()` (bullish BB/MB için). Kutu kalkar. |

Bu kuralın sonuçları (test edilebilir değişmezler):
- **Swing OB'ler her zaman BB olur.** A, kırılan pivotun kendisidir (o anda en yeni `slPiv`). Kırılım barı A'nın altında kapanır.
  Tek istisna `ob.idx == pivotBar` (OB mumu pivot barının kendisi); o durumda A bir önceki swing low olur.
- **MB yalnız internal OB'lerden çıkar:** küçük bir dip kırılmış ama swing low (A) alınmamış, yani swing ölçeğinde higher low var.
  ICT'deki "failure swing" tanımı bu.

**SHOULD:** Karar vermeden önce Python'da (BTC/ETH/SOL 15m) her iki kuralla BB:MB oranını çıkar. Outline kuralı
~%95+ BB, iki ölçekli kural daha dengeli çıkıyorsa karar kolaylaşır. Yazıp çalıştırması 30 satır.

### 1.2 OTE sabit range — boşluklar

Operatörün "range" modeli tutarlı. Eksikler:

- **MUST — yeni range'in uçları kesin tanımlı değil.** (b) "yeni swing yapısı yeni range başlatır" diyor ama yeni H ve L'nin ne olduğunu söylemiyor. Öneri:
  - Swing kırılım barında (Brk `internal=false`, `idx == bar_index`):
    `L = min(ob.rawLow, low)`, `H = max(ob.rawHigh, high)`. Bunlar kırılan pivot barından kırılım barına kadar olan **impuls bacağı**
    (kırılım barı dahil). Kırılımda yeni oluşan OB'nin `rawLow`/`rawHigh` alanları zaten bu aralığı tutuyor, ek geçmiş okuması gerekmez.
  - `b.ob` `na` ise: `L = swingLow.level`, `H = swingHigh.level` (son onaylı pivotlar).
  - Aynı barda hem bull hem bear swing kırılımı olursa, core sırası nedeniyle sonuncu (bear) kazanır.
- **MUST — başlangıç durumu.** İlk swing kırılımına kadar range = core'un `trailTop`/`trailBot` değeri (ya da hiç çizilmez). Tek cümleyle yazılsın.
- **MUST — "aşar" fitille mi, kapanışla mı?** Öneri: fitil (`high > H` / `low < L`), yalnız `barstate.isconfirmed`. Core'un `trailTop`/`trailBot` güncellemesiyle aynı.
- **MUST — fib yönü uçların bar sırasıyla belirlenir; eşitlik kuralı eksik.** Yön = `hBar > lBar ? LONG : SHORT`, en son yapılan bacak. Bir outside bar
  aynı barda iki ucu da uzatırsa (`hBar == lBar`) **önceki yön korunur**. Bu yazılmazsa yön her outside barda belirsiz kalır.
  Not: L uzarsa yön kendiliğinden SHORT'a döner (son bacak artık aşağı). ICT ile tutarlı ama dashboard'da görünür olmalı (bkz. 3).
- **SHOULD — swing kırılımı yalnız swing yapısıyla sınırlansın (taslak doğru).** Internal (len 5) kırılımlar range'i birkaç barda bir sıfırlar.
  Bu "sabit range" isteğiyle çelişir.
- **SHOULD — dejenere range.** `R = H − L < 2 × syminfo.mintick` ise çizme. Bölme veya sıfır kutu oluşmaz.
- **Doğrulandı:** formüller doğru. Long `H − k·R`, short `L + k·R`, k ∈ [0.618, 0.786], 0.705 ve EQ = `L + 0.5·R`. Core'daki `f_tags`
  OTE bandıyla aynı aritmetik; yalnız range kaynağı farklı (trail ↔ sabit). Parity etkilenmez, çünkü yeni state tail'de yaşıyor ve core okunmuyor.
- **NICE:** range'in core'daki trail range'ten farkını (trail her yeni pivot onayında sıfırlanıyor, 50 bar gecikmeli) bir satırla spec'e yaz.
  Trader iki ayrı "EQ" görüp karıştırmasın: dashboard'daki "Range EQ" trail EQ'dur.

### 1.3 Mitigation ile delinme etkileşimi (MUST)

`f_mitigate` (HIGHLOW modu) bear OB'yi `high > barHigh` olduğunda mitigated sayar. Flip koşulu `close > top() ≥ barHigh` ise `high > barHigh`
koşulunu da içerir. Yani **her flip, mitigated bir OB üzerinde olur**; çoğu zaman fitil dokunuşu birkaç bar önce gelir. Bu yüzden BB/MB takipçisi:
- `mitigatedIdx >= 0` olan OB'leri de takip etmeli. Aktif OB filtresi (`mitigatedIdx < 0`) burada **kullanılmamalı**.
- Takibi flip, prune (`createdIdx < bar_index − liveWindowBars`) ya da ters yönde pasifleşme olana kadar sürdürmeli. Başka bir süre sınırı
  koyma, ya da konacaksa açıkça yaz.

### 1.4 T2 (`obInvalidate`) açıkken çift çizim (SHOULD)

`f_flipBreaker`, ters yönlü OB'yi aynı kutuyla `swingObs`/`intObs`'e itiyor (`createdIdx = bar_index`). T2 ON iken:
- `f_drawObs` bunu normal OB olarak çizer.
- Tail takipçisi de bunu yeni OB sanıp kaydeder; ileride "BB'nin BB'si" oluşur.

Kural: aynı `idx` ve ters `bias` ile havuzda zaten bir kaynak OB varsa yeni OB tail'de **breaker kopyası** sayılır. OB olarak çizilmez,
takipçiye alınmaz. Varsayılan T2 OFF olduğu için tek satırlık bir koruma yeter.

---

## 2. Pine v6 tuzakları (yeni çizim katmanı)

- **MUST — tail fonksiyonlarında `x[off]` ve `ta.*` kullanılmaz.** `f_storeOb` ve `f_confirm` hatasının aynısı: koşullu, döngü içinde ya da
  `barstate.islast` bloğunda çağrılan bir fonksiyonda `low[1]` veya `ta.lowest()`, bar geçmişini değil fonksiyonun **çağrı geçmişini** okur.
  Kurallar:
  1. Geçmiş veri yalnız core'un global ring buffer'larından (`bufHi`/`bufLo`/`bufClose`/`bufTime`) okunur. Tail core'dan sonra çalıştığı için
     tail'in `isconfirmed` bloğunda buffer'ın en yeni elemanı **mevcut onaylı bar** oluyor; spec'e bu indeks sözleşmesi yazılsın.
  2. Bacak ucu ve sweep bilgisi geçmiş okumayla değil, her onaylı barda güncellenen **durum alanlarıyla** tutulur.
  3. `tests/test_pine_lab_build.py`'ye `test_store_ob_reads_bar_history_from_global_buffers` kalıbında bir test eklensin. Test, tail'deki
     her `f_*` fonksiyon gövdesinde `\b\w+\[\s*\w` (history) ve `ta\.` bulunmadığını doğrulasın.
- **MUST — core'daki UDT'lere alan eklenemez (core değişmiyor).** Tail kendi kaydını tutar:
  `type Flip { OB ob, float A, float legExt, int flipBar = -1, int cls = 0 /*1 BB, 2 MB*/, bool dead = false }` ve `var array<Flip>`.
  Yeni OB'ler, her onaylı barda havuzun sonundan geriye `createdIdx == bar_index` olduğu sürece taranarak bulunur. Prune havuzun başından
  sildiği için `array.size` artışına güvenilmemeli. Pine nesneleri referans olarak tutulur; havuzdan prune edilen OB tail'de geçerli kalır.
  Tail kaydı da aynı prune kuralıyla budanmalı.
- **MUST — dashboard tablosu satır sayısı.** `table.new(position.top_right, 2, 7)` kullanılıyor. 7. indeksten sonra eklenen her sayaç satırı
  runtime hatası verir. Satır sayısı yeni satırlarla birlikte güncellenmeli.
- **MUST — bütçe tablosu spec'e girsin** (`max_*_count = 500`; aşılınca TV sessizce **en eski** nesneyi siler, yani eski sinyal çizgilerini):

  | Tür | Mevcut | Yeni (önerilen varsayılan) | Toplam |
  |---|---|---|---|
  | box | OB 40+40, zone ≤ 6 | BB/MB 10, FVG 10, OTE 1 | ≈ 107 |
  | line | sinyal 4 × `maxDrawings` (60 → 240) | likidite 20, OTE 0.705 + EQ + H/L 4 | ≈ 264 |
  | label | sinyal `maxDrawings` (60) | likidite 0–20 (tercihen 0, bkz. 3) | ≈ 60–80 |

  Mevcut bir hata da var: `maxDrawings maxval = 150` → 600 çizgi, 500'ü aşıyor. Yeni katmanlar eklenmeden `maxval` 100'e çekilsin ya da GC'nin
  eski sinyalleri sileceği belgelensin.
- **SHOULD — etiket yerine kutu metni.** BB/MB/FVG/OB isimleri `box.new(text=…)` ile yazılsın: label bütçesi harcanmaz, sinyal label seti
  değişmez (bkz. 4, regresyon). Likidite çizgileri için `line` + kutu metni olmadığından, label gerekiyorsa yalnız en yakın N tanesine.
- **SHOULD — döngü maliyeti.** Her onaylı barda yapılacak tek ek iş Flip kaydını dolaşmak (O(aktif kayıt)). Flip olmuş ve `dead` kayıtlar
  döngüden çıkarılsın. `barstate.islast`'taki çizim döngüsü (FVG havuzu 750 barda yüzlerce olabilir) bir kez çalışır; yine de "en yakın N" seçimi
  tam sıralama yerine **iki geçişli tarama** (önce mesafe eşiği, sonra N) ile yapılsın. Döngü sınırı ve süre aşımı riski en çok düşük TF + uzun
  geçmişte (1m/5m) çıkar; test edilecek.
- **SHOULD — repaint.** Tüm durum yalnız `barstate.isconfirmed`'da değişsin; core ile aynı. `islast`'ta silip yeniden kurmak repaint değil,
  çünkü yalnız çizim değişir. Gerçek zamanlı bar H'yi geçse de range bar kapanana kadar uzamaz; bu beklenen davranış, spec'e yazılsın.
- **NICE — `var` fonksiyon içinde kullanılmasın.** `f_leg` gibi her barda koşulsuz çağrılmayan bir yardımcı içindeki `var`, çağrı yeri bazında
  durum tutar; döngüde çağrılırsa yanlış sonuç verir. Tail durumu global `var` olmalı.
- **NICE — if/else dal tipi.** Core'da `f_onConfirmed` için yapılan `true` dönüşü (void/string dal karışımı) tail'deki çizim fonksiyonlarında da
  gerekebilir.

---

## 3. Trader okunabilirliği

- **MUST — her kutuya tip metni.** `OB` / `iOB` / `BB` / `MB` / `FVG`; `text_size=size.tiny`, `text_halign=text.align_right`; metin fiyatın
  yanında, sağda dursun. Kesikli ve noktalı kutu kenarları küçük boyda ayırt edilmiyor; tip yalnız metinle okunur.
- **MUST — üst üste binme önceliği (z-order = oluşturma sırası).** `islast`'ta şu sırayla kurulsun (en alttan en üste):
  OTE (çok şeffaf) → FVG → OB/iOB → BB/MB → likidite çizgileri → bekleyen zone'lar → sinyal çizgileri.
  Aynı fiyat kutusunda (OB ve onun BB'si, T2) yalnız biri çizilsin (1.4).
- **SHOULD — "son N" yerine "fiyata en yakın N, yön başına".** "Son N" uzaktaki yeni internal OB'leri gösterip yakındaki eski swing OB'yi
  gizleyebilir. Öneri: fiyatın üstünde N, altında N; mesafe = yakın kenar − `close`. Mevcut `shown < 40` ile tutarlı tek input (`maxZonesPerSide`).
- **SHOULD — mitigated ama delinmemiş OB kısa süre soluk kalsın.** Core'da OB, ilk fitil temasında aktiflikten düşüyor; trader kutunun tam tepki
  anında kaybolduğunu görüyor. Takipçi bu OB'leri zaten tuttuğu için maliyeti yok: flip olana kadar `alpha` yüksek, `text="OB ✓"` (test edildi).
- **SHOULD — süpürülmüş likidite.** Sweep barında bitsin (`x2 = sweepBar`) ve soluk, kesikli olsun. Sağa uzanırsa grafik kalabalıklaşır.
  Core `Piv`/`Equal`'da sweep barı yok; çizim anında global `bufHi`/`bufLo` taranarak bulunur (havuz başına ~20 öğe × ≤ 900 = önemsiz).
  Varsayılan: yalnız son 5 süpürülmüş.
- **SHOULD — renk ve yön sözleşmesi.** Renk = bölgenin **şu anki** yönü (BB/MB flip sonrası yön; bear OB'den doğan bullish BB teal).
  BSL (EQH + swing high) bear renginde, SSL bull renginde değil, nötr (ör. turuncu/mor): likidite yön değil, hedef. Bu karar spec'te yazılsın.
- **SHOULD — OTE okunurluğu.** Kutu (0.618–0.786) + 0.705 çizgisi + EQ çizgisi. Kutu metni `OTE LONG`/`OTE SHORT`, ince H/L çizgisi.
  Dashboard'a `OTE: LONG H=… L=…` satırı eklensin; yön değişimini trader buradan izler.
- **NICE — lejant.** Sol altta 1×6 küçük renk tablosu (OB/BB/MB/FVG/BSL-SSL/OTE) ya da input tooltip'leri. Kutu metinleri varsa önemi düşük.
- **NICE — FVG kısmi dolum.** Core FVG'yi yalnız tamamen dolunca düşürüyor. Dolmuş kısmı kırparak göstermek güzel olur ama ek durum ister; sonraya.

---

## 4. TradingView MCP ile koşulabilir doğrulama planı

Sınır: `data_get_pine_boxes` yalnız `{high, low}` çiftleri döndürüyor (renk, metin, x yok). `data_get_pine_lines` tekilleştirilmiş, sıralı fiyatlar
döndürüyor. Bu yüzden **katmanlar birbirinden input'larla ayrılmalı.**

1. **MUST — statik.** `python scripts/build_pine_lab.py --check` ve `pytest tests/test_pine_lab_build.py tests/test_pine_lab_parity.py`.
   `git diff --exit-code pine/efloud_lab_strategy.pine pine/lab/core.pine` → **bayt bayt aynı** olmalı ("core değişmez" iddiasının kanıtı).
   Yeni history/ta yasağı testi de burada (bölüm 2).
2. **MUST — derleme ve runtime.** `pine_set_source` → `pine_smart_compile` → `pine_get_errors` = 0. Runtime hatası için `ui_evaluate` ile
   `[title*="RE100"]` kontrolü. Aynı set BTC/ETH/SOL 15m ve bir stres TF'de (1m, en uzun geçmiş) tekrarlansın.
3. **MUST — katman izolasyonu.** Her ölçümde `indicator_set_inputs` ile yalnız tek katman açık olsun (`showObs`, `showZones`, `showLevels` dahil
   diğerleri kapalı). Ardından `data_get_pine_boxes study_filter="EFloud Lab"` (veya lines). Doğrulama sırasında "en yakın N" sınırı yüksek tutulsun
   (ör. 200); karşılaştırma kümesi N ile kesilmesin.
4. **MUST — Python beklenen kümeler.** Yeni küçük bir alt komut (öneri: `scripts/pine_lab_parity.py visuals --ohlcv … --out expected.json`),
   parity koşularında kullanılan **aynı CSV** üzerinde son 750 barla `lx.analyze(df.tail(750))` çalıştırır:
   - OB: `active_obs(internal=False/True)` → `{(top, bot)}`
   - FVG: `active_fvgs()` → `{(top, bot)}`
   - Likidite: `equals` + `swing_high_pivots`/`swing_low_pivots` → fiyat kümesi (swept bayrağı core kuralıyla 3 satırda hesaplanır)
   - **BB/MB ve OTE için Python referans implementasyonu** (bölüm 1.1/1.2 kuralları, ~60 satır, saf fonksiyon). Outline'daki "Python karşılığı
     yok → elle kontrol" yerine bu yazılsın: kural yalnız görüntü olduğu için ucuz ve deterministik. OTE beklenen çıktısı 6 fiyat
     (H, L, 0.618, 0.705, 0.786, 0.5) ve yön.
   - Karşılaştırma: `mintick` toleransıyla küme eşitliği, precision/recall raporu. **Isınma bölgesi hariç**: pencerenin ilk `2 × swingLen`
     barında oluşan nesneler (Pine tam geçmişle, Python 750 barla başlıyor). Eşik: OB/FVG ≥ %98, BB/MB/OTE = %100 (kendi kuralımız).
5. **SHOULD — sayaç üzerinden çapraz kontrol.** Dashboard'a tek satır `OB s/i · BB · MB · FVG · BSL/SSL` eklensin;
   `data_get_pine_tables` ile Python sayılarıyla karşılaştırılsın. Kutu okumadan önce hızlı bir duman testi olur.
6. **MUST — sinyal regresyonu.** Yeni katmanlar OFF ve ON iken `data_get_pine_labels` aynı küme olmalı. Yeni katmanlar label kullanmazsa
   (bölüm 2, kutu metni) eşitlik birebir aranır; kullanırsa metin önekine göre filtrelenir. Alert JSON'u değişmez; strateji dosyası zaten 1. adımda
   bayt bayt kontrol edildi.
7. **NICE — repaint kontrolü.** `replay_start` ile bir tarihe gidilir, `replay_step` ile ~100 bar ilerlenir, kutular okunur ve aynı bara kadar
   kesilmiş CSV üzerinde Python beklentisiyle karşılaştırılır. Onaylı-bar disiplini zaten parity'de kanıtlı; yalnız yeni takipçi için bir kez yeter.
8. **NICE — görsel kontrol listesi** (`capture_screenshot`): metinler okunuyor mu, z-order doğru mu, OTE yönü dashboard'la aynı mı, süpürülmüş
   çizgiler sweep barında bitiyor mu.

---

## 5. Kesilecekler (YAGNI)

- **SHOULD kes — katman başına renk input'ları.** 6 katman × 2 yön = 12 input. Yerine 2 renk (bull/bear) + 1 nötr (likidite) + 1 şeffaflık input'u.
- **SHOULD kes — `maxObDraw`/`maxFvgDraw`/`maxLiqDraw` ayrı ayrı.** Tek `maxZonesPerSide` (bölge katmanları) + sabit likidite limiti yeter.
- **SHOULD kes — `showBb` + `showMb` ayrı toggle.** Tek `showBreakers` toggle'ı; ayrım kutu metninde.
- **SHOULD kes — `showSweptLiq` + "eski/pasif bölgeleri göster".** Tek `showHistory` (soluk) toggle'ı. Varsayılan kapalı; mitigated-OB soluk
  gösterimi (bölüm 3) bundan bağımsız, kısa süreli.
- **Kes — OTE geçmişi, ölü BB/MB'lerin soluk gösterimi, BB/MB için swing/internal stil ayrımı.** Okunurluğa katkısı düşük, bütçe ve test yükü getirir.
- **Kes — EQL/EQH'yi BB sweep referansına eklemek.** Swing pivotu yeterli; ikinci bir likidite kaynağı kuralı yoruma açık hale getirir.
- **Tut —** dashboard sayaç satırı. Trader için kritik değil ama doğrulamanın en ucuz MCP kancası.

---

### Öncelik sırası (en önemli 5)
1. BB/MB referansı: outline kuralı neredeyse dejenere (≈ hep BB). İki ölçekli kural (dondurulmuş son swing pivotu A, `(ob.idx, flip)` bacak ucu)
   operatöre sunulsun; önce Python'da BB:MB oranı ölçülsün.
2. Flip mitigated OB'lerde olur: takipçi `mitigatedIdx` filtresi kullanmamalı; T2 açıkken çift kayıt koruması eklenmeli.
3. OTE: yeni range uçları = kırılım OB'sinin `rawLow`/`rawHigh` + kırılım barı; fitil ile uzama; `hBar == lBar` iken yön korunur; ilk swing
   kırılımından önceki durum tanımlı olmalı.
4. Pine: tail'de `[off]`/`ta.*` yasağı testle kilitlensin; core UDT'lere alan eklenemediği için ayrı `Flip` kaydı tutulsun; dashboard tablo satırı
   ve 500 çizgi bütçesi (mevcut `maxDrawings` 150 × 4 = 600 hatası) düzeltilsin.
5. Doğrulama: katmanlar input'la izole edilsin, BB/MB ve OTE için küçük Python referansı yazılsın (elle kontrol yerine), core ve strateji dosyası
   bayt bayt aynı olsun, sinyal label kümesi değişmesin.
