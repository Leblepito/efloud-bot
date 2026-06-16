# Wave-2 Yeni-Edge Research & Design Proposal (Track 2 Faz 0)

**Tarih:** 2026-06-16  
**Hazırlayan:** 👑 Gemini SMR Orchestrator (Senior Architect)  
**Durum:** `spec_hazır / inceleme_bekliyor`  
**Referans:** `LLTODO/plans/P-001-u2algo-wave1-tradingview.md`, `pine/u2algo/WAVE1_SPEC.md`

---

## 1. Yönetici Özeti (Executive Summary)

Wave-1 kapsamında, efloud-bot'un temel SMC (Smart Money Concepts) algoritmaları TradingView Pine Script v6 platformuna başarılı bir şekilde port edilmiş ve `wave1_signals.pine` (ücretsiz indikatör) ile `wave1_strategy.pine` (premium strateji) olarak yapılandırılmıştır. Ancak Wave-1, derleme limitleri ve repaint riskleri nedeniyle **kapsam daraltmasına** maruz kalmış; HTF (4h) trend yönü, Daily makro filtresi ve MTF 1h swing kırılımları elenmiştir.

**Wave-2 (Track 2 Faz 0)**, bu ertelenen yapısal özellikleri geri getirmekle kalmayıp, TradingView ortamına özel yeni alfa kaynakları (**Yeni-Edge**) ekleyerek stratejinin getiri/risk (Sharpe/Drawdown) profilini optimize etmeyi hedefler. Bu belgede, Wave-2 için tasarlanan yeni konseptlerin matematiksel ve mantıksal temelleri ile Pine Script v6 mimari yol haritası sunulmaktadır.

---

## 2. Yeni-Edge (Alfa Kaynağı) Adayları

### 2a. Edge 1: Inducement (IDM) Sweeps & Extreme Entry
Geleneksel SMC modellerinde, yeni bir BOS (Break of Structure) oluştuktan sonra fiyata en yakın ilk minör pullback seviyesi **Inducement (IDM)** olarak adlandırılır. 
*   **Sorun:** Çoğu perakende SMC indikatörü, her oluşan Order Block (OB) bölgesini bir giriş fırsatı olarak görür. Bu da düşük kaliteli iç yapılarda (sub-structures) stop edilme oranını artırır.
*   **Çözüm (Yeni Edge):** Fiyat IDM seviyesini süpürmeden (sweep) ve likidite havuzunu temizlemeden işleme giriş tetiklenmez. IDM süpürüldükten sonra, daha derinlerde yer alan **Extreme Order Block** (en alttaki/en üstteki OB) veya Premium/Discount dengesindeki OTE (Optimal Trade Entry) seviyesi hedeflenir.

```
[BOS] ──────┐
            │   ┌───► [Geleneksel Giriş: Erken OB - Genelde STOP olur]
            └───┼───► [Minör Pullback = Inducement (IDM)]
                └───► [Likidite Süpürmesi - IDM Sweep]
                      └───────► [Extreme OB / OTE Girişi - Yüksek R:R ✅]
```

### 2b. Edge 2: Likidite Süpürmesi (SFP - Swing Failure Pattern) Giriş Tetikleyicisi
Order Block bölgesine doğrudan limit emir bırakmak yerine, fiyatın o bölgedeki likiditeyi süpürüp süpürmediğini teyit eden dinamik bir tetikleyici.
*   **Mantık:** Fiyat 4h POI (Point of Interest) veya 1h OB bölgesine girdiğinde, 15m TF üzerinde son swing high/low seviyesinin dışına iğne atıp (sweep) barı o seviyenin içinde kapatması (**SFP**) beklenir.
*   **Avantajı:** Yanlış kırılımlardan korur ve stop mesafesini sweep iğnesinin hemen arkasına koyarak R:R oranını çarpıcı bir şekilde büyütür (Slipped entry yerine Confirmed tight stop).

### 2c. Edge 3: Session & Killzone Likidite Havuzları (Intraday Edge)
Kripto ve Forex piyasalarında hacmin ve volatilitenin zamana göre dağılımını kullanan bir zaman-likidite matrisi.
*   **Asya Session Range:** Asya seansının en yüksek (Asian High) ve en düşük (Asian Low) seviyeleri belirlenir.
*   **London/NY Open Sweeps (Judas Swing):** London Open veya New York Open seanslarında Asya seansı ekstrem noktalarından birinin süpürülmesi (sweep), günün asıl yönünün tersine bir stop-hunt hareketidir. Wave-2 confluence skoruna bu seans süpürmeleri entegre edilecektir (+15 Confluence puanı).

### 2d. Edge 4: Previous Day / Previous Week High/Low (PDH/PDL, PWH/PWL)
Günlük ve haftalık ekstrem noktalar kurumsal emir bloklarının ve likidite havuzlarının yoğunlaştığı alanlardır.
*   **Uygulama:** Fiyatın PDH veya PDL seviyesini süpürüp içeri dönmesiyle tetiklenen dönüş modelleri, 15m trend yönüyle birleştirilir.

---

## 3. Çoklu Zaman Dilimi (MTF) Mimari Genişlemesi

Wave-2, 4 zaman dilimli tam akışı Pine Script v6 standartlarında repaint olmadan kurmayı amaçlar:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. DAILY TF: Makro Trend Regülatörü (Boğa / Ayı / Flat)         │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼ (Filtreler)
┌─────────────────────────────────────────────────────────────────┐
│ 2. HTF (4h) TF: Ana Yapı Kırılımları (BOS/CHoCH) & POI Alanları │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼ (Alan ve Yön Doğrulama)
┌─────────────────────────────────────────────────────────────────┐
│ 3. MTF (1h) TF: CHoCH Onayları & Swing Kırılımları (Bias)       │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼ (Tetikleyici & Likidite Süpürmesi)
┌─────────────────────────────────────────────────────────────────┐
│ 4. ENTRY (15m) TF: OB Retest, SFP, IDM Sweep & Sinyal Üretimi   │
└─────────────────────────────────────────────────────────────────┘
```

### Repaint Önleme Protokolü (Strict Repaint Protection)
Pine Script'te üst zaman dilimlerinden veri çekerken oluşabilecek look-ahead hatasını önlemek için şu kurallar katı bir şekilde uygulanacaktır:
1.  **Lookahead Kapatma:** Tüm `request.security()` çağrıları `lookahead = barmerge.lookahead_off` ile yapılacaktır.
2.  **Bar Gecikmesi (`[1]` Kuralı):** Üst zaman diliminin fiyat verisi (OHLCV) ve hesaplanan yapıları (swings, OBs) sadece kapanmış barlardan okunacaktır.
    *   *Örnek:* `htf_close = request.security(sym, "240", close[1])`
3.  **İndeks Hizalama:** 15m grafik üzerindeki zaman damgası (time), üst zaman diliminin bar kapanış zamanıyla karşılaştırılarak eşleştiği andan itibaren sinyalde kullanılacaktır.

---

## 4. Pine Script v6 Sınırları ve Çözüm Yaklaşımları

Wave-1'de karşılaşılan en büyük engel, compile-pass alıp runtime'da grafik üzerinde kırmızı ünlem veren **`RE10045` (Pine Runtime execution error)** hatasıydı. Bu hata, karmaşık User-Defined Functions (UDF) ve büyük dinamik dizilerin (arrays) bir arada kullanılmasından kaynaklanmaktadır.

Wave-2 için belirlenen sınır hafifletme (mitigation) mimarisi şudur:

### 4a. Array ve Çizim Optimizasyonu
*   **Kutuların ve Etiketlerin Sınırlandırılması:** Grafikte aynı anda çizilebilecek maksimum `box` ve `label` sayısı TV motorunu yormayacak şekilde sınırlandırılacaktır. `max_boxes_back = 100` ve `max_labels_back = 100` parametreleri kullanılacaktır.
*   **Çöp Toplama (Garbage Collection):** Aktif olmayan veya miladı dolmuş (mitigated) OB ve FVG kutuları, dizi içerisinden çıkarılacak ve çizimleri `box.delete()` ile bellekten temizlenecektir.
*   **Boyut Sınırı:** En fazla 10 adet aktif OB kutusu ve 5 adet aktif FVG kutusu bellekte tutulacaktır.

### 4b. UDF (User Defined Functions) Yerine Satır İçi (Inline) Hesaplama
*   `RE10045` hatasının ana tetikleyicisi olan çok katmanlı fonksiyon çağrıları azaltılacaktır.
*   Özellikle en yakın OB'yi bulma veya SL/TP hesaplama algoritmaları, fonksiyonlar yerine doğrudan bar döngüleri içinde (inline loops) çözülecektir.

---

## 5. Wave-2 Confluence Scoring Matrisi (Taslak)

Confluence skoru 0-100 arasında normalize edilecek ve sinyal üretimi için baraj puanı varsayılan olarak **80** olacaktır.

| Faktör / Kriter | Puan Ağırlığı | Açıklama |
|---|:---:|---|
| **4h Trend & 1h Bias Alignment** | **+20** | Üst zaman dilimlerinin yön uyumu |
| **Extreme OB Retest** | **+25** | Fiyatın en dipten/en tepeden tepki alması |
| **Liquidity Sweep (SFP)** | **+20** | Giriş TF'sinde (15m) likidite süpürme onayı (Yeni Edge) |
| **Inducement (IDM) Sweep** | **+15** | Giriş öncesi iç yapının temizlenmesi (Yeni Edge) |
| **Session High/Low Sweep** | **+10** | Asya seansı likiditesinin süpürülmesi (Yeni Edge) |
| **Premium/Discount Discount Zone** | **+10** | Pozisyonun ucuzluk (Long) veya pahalılık (Short) bölgesinde olması |

---

## 6. Doğrulama ve Backtest Planı (Faz 0 Kapısı)

Strateji kodlanmadan önce ve kodlandıktan sonra uygulanacak test aşamaları:

### 6a. Statik ve Dinamik Analiz (G-T1 & G-T2)
*   **Compile Test:** Pine Editor üzerinde 0 hata ve 0 uyarı garantisi.
*   **Repaint Görsel Analiz:** Bar bar geriye oynatma (Replay Mode) ile geçmiş barlardaki sinyallerin kayıp kaymadığı veya sonradan belirip belirmediği test edilecektir.

### 6b. Agregasyonlu Çoklu-Sembol Backtest Kapısı (G-T4)
*   **Sembol Grubu:** `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT` (Binance Futures perp verileri).
*   **Backtest Periyodu:** Son 6 ay (Min 200 trade örneği).
*   **Kabul Kriterleri (Gates):**
    1.  **Profit Factor (PF):** $\ge 1.5$ (Out-of-sample veri setinde).
    2.  **Sharpe Ratio:** $\ge 1.8$
    3.  **Maksimum Drawdown (MaxDD):** $\le \%8$ (Hesap bazlı, risk %1/trade iken).
    4.  **Min R:R:** Tüm işlemlerde realized R:R $\ge 1.8$ olmak zorundadır.

---

## 7. Sonraki Adımlar & Görev Dağılımı

Kullanıcı onayı sonrası Track 2 Faz 1 (İmplementasyon) aşamasına geçilecektir:

1.  **[Faz 1.1]** `WAVE2_SPEC.md` teknik spesifikasyon dosyasının oluşturulması (Sanal Opus).
2.  **[Faz 1.2]** Inducement, SFP ve Session Sweep algoritmalarının Pine dilinde prototiplenmesi (Sanal Flash).
3.  **[Faz 1.3]** `wave2_signals.pine` indikatörünün yazılması ve TradingView üzerinde RE10045 testinin yapılması.
4.  **[Faz 1.4]** `wave2_strategy.pine` stratejisinin oluşturulması ve backtest kapılarından geçirilmesi.

---

> [!NOTE]
> Bu araştırma belgesi, Wave-2'nin risk sınırlarını netleştirmek ve kodlamaya geçmeden önce mimari konsensüs sağlamak amacıyla hazırlanmıştır. Önerilen yeni-edge mekanizmaları efloud-bot'un live performansını TradingView tarafında birebir yansıtacak şekilde ölçeklenmiştir.
