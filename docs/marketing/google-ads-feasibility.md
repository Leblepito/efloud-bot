# Google Ads Feasibility Analysis (ADS-0)

**Tarih:** 2026-06-17  
**Hazırlayan:** 🟦 Gemini (Growth Layer / Paid Acquisition Specialist)  
**Durum:** `approved (claude review 2026-06-17)`  
**Referans:** `docs/handoff/2026-06-17-gemini-google-ads-workstream.md`, §4.7 ADS

---

## 1. Yönetici Özeti & Bölge Verdict Tablosu

Google Ads Financial Products and Services politikaları, algoritmik trading indikatörleri ve sinyal servisleri için son derece katıdır. Bu analiz, `u2algo` markasının Google Ads platformunda reklam verme olasılığını bölge bazında değerlendirmektedir.

| Bölge / Ülke | Durum | Gerekçeler (Kanıt ve Politika) | Karar |
| :--- | :---: | :--- | :---: |
| **United States (US)** | **RESTRICTED** | G2RS finansal doğrulaması zorunlu değil. Ancak kelimeler "charting tool" olarak filtrelenmeli; CFTC 4.41 disclaimers zorunlu. Reklam kopya ve landing page'de en ufak finansal vaat hesabın askıya alınmasına yol açar. | **GO (Kısıtlı)** |
| **European Union (EU)** | **NO-GO** | Almanya (BaFin), Fransa (AMF), İrlanda ve İtalya gibi kritik EU ülkelerinde **G2RS (G2 Risk Solutions)** finansal doğrulama zorunlu. Regüle edilmiş bir broker ya da lisanslı finansal danışman olmadığımız için bu doğrulamayı geçmek imkansızdır. | **NO-GO** |
| **Turkey (TR)** | **NO-GO** | Google TR finansal doğrulama kapsamındadır. Sermaye Piyasası Kurulu (SPK) lisansı olmadan kaldıraçlı işlem, sinyal veya yatırım aracı reklamı yapmak yasaktır. Kripto ödeme yasakları ve katı SPK kuralları reklamın onaylanmasını engeller. | **NO-GO** |
| **Rest of World (Global)** | **RESTRICTED / NO-GO** | Birleşik Krallık, Avustralya ve Singapur gibi G2RS zorunlu olan ülkelerde **NO-GO**. G2RS doğrulaması olmayan diğer ülkelerde ise crypto/forex kelime filtreleri ve "misrepresentation" nedeniyle yüksek askıya alınma riski taşır. | **NO-GO (Büyük Kısım)** |

### 🚨 Kritik Stratejik Karar (Verdict)
* **Kanal GO/NO-GO Kararı:** **NO-GO (Global/TR/EU İptal, US Parked/Mooted)**
* **US RESTRICTED-GO Yolu PARKED:** US pazarı için kısıtlı "GO" yolu şu aşamada **izlenmemekte ve askıya alınmaktadır (parked)**. Gerekçeler:
  * Ürünün mevcut konumu "ücretsiz indikatör + waitlist" (PROD-0) olmasından ötürü paid reklam maliyetinin karşılanamaması.
  * Canlı engine kanıtının negatif (-%5.3) seyretmesi.
  * Google Ads tarafında yüksek hesap askı/kapatılma riski bulunması.
  * Bu koşullar altında free-waitlist funnel'ı için US paid arama ağı kampanyaları rasyonel ve karlı değildir.
  * Yalnızca gelecekte operatörün lisans alması VEYA u2algo'nun 90 günlük pozitif, kanıtlanmış bir track-record oluşturması durumunda bu opsiyon yeniden değerlendirilecektir.
* **Kanal Durumu:** **Organic-only.** Google Ads bütçesinin **%100'ü**, Google Ads'in katı kurallarına takılmayan **Organik Kanallara (YouTube, TradingView Script Library SEO, X/Telegram)** yeniden tahsis edilecektir. ADS-1..5 görevleri mooted ilan edilmiştir (ileride US parked opsiyonu canlandırılmadığı sürece).

---

## 2. Google Ads Politikaları Detaylı Analizi

### 2a. Cryptocurrencies & Related Products Policy ([Policy Link](https://support.google.com/adspolicy/answer/11181519))
* **Yasaklanan İçerikler:** Kripto para trading sinyalleri, kripto yatırım tavsiyeleri, DeFi işlem protokolleri, token likidite havuzları, ICO'lar ve regüle edilmemiş spekülatif kripto ürünleri.
* **Kısıtlı / Sertifikalı İçerikler:** Regüle kripto borsaları ve soğuk/sıcak cüzdan yazılımları (yalnızca exchange/swap içermiyorsa).
* **u2algo Etkisi:** Reklam veya landing page üzerinde "Crypto signals", "Binance bot", "USDT signals" kelimeleri kullanıldığı anda reklamlar otomatik olarak reddedilir ve hesap askıya alınır.

### 2b. Complex Speculative Financial Products Policy ([Policy Link](https://support.google.com/adspolicy/answer/7645254))
* **Tanım:** Fark Sözleşmeleri (CFDs), finansal spread betting ve rolling spot forex (FX) işlemleri.
* **Kısıtlama:** Yalnızca ilgili ülkenin regülatörü tarafından lisanslanmış kurumlar (veya yetkilendirilmiş broker partnerleri) Google Ads finansal sertifikası alarak bu ürünlerle ilgili reklam verebilir.
* **u2algo Etkisi:** İndikatörümüzün Forex veya kaldıraçlı işlemler için "sinyal" ürettiği algısı oluşursa, Google Ads bunu karmaşık spekülatif ürün sınıfına sokarak lisans kanıtı talep eder. Lisansımız olmadığı için kampanya bloke olur.

### 2c. Trading Signals & Speculative Advice ([Policy Link](https://support.google.com/adspolicy/answer/6089309))
* **Yasaklama:** Google, spekülatif trading tüyoları, al-sat sinyalleri, sinyal üreteçleri veya broker karşılaştıran affiliate sitelerinin reklamlarını açıkça **yasaklar**.
* **u2algo Etkisi:** `u2algo`'nun pazarlama dilinde "Buy/Sell Alerts", "Signal Indicator", "AI Signal Generator" gibi ibareler kesinlikle yer alamaz. Ürün yalnızca teknik analiz çizim yardımcısı ve eğitim aracı olarak konumlandırılmalıdır.

### 2d. Misrepresentation & Unrealistic Claims ([Policy Link](https://support.google.com/adspolicy/answer/6020590))
* **Yasaklama:** "Get-rich-quick" (kolay yoldan zengin olma) vaatleri, garanti kazanç iddiaları, risksiz kazanç söylemleri veya doğrulanmamış performans yüzdeleri.
* **u2algo Etkisi:** Landing page üzerinde "SMC v2 ile %80 Win Rate", "+81% kâr", "Milyoner olun" gibi ibareler yer alamaz. Reklam kopyaları tamamen "teknik analiz eğitimi" ve "TradingView için ücretsiz indikatör ve waitlist" odaklı olmalıdır.

### 2e. Advertiser Financial Services Verification ([Policy Link](https://support.google.com/adspolicy/answer/10770884))
* **Süreç:** Google, finansal hizmet ve ilişkili ürün reklamı verenlerin **G2 Risk Solutions (G2RS)** üzerinden kimlik ve regülasyon doğrulaması yapmasını şart koşmaktadır.
* **Bariyer:** Doğrulama için firmanın resmi olarak finansal lisans sahibi (danışmanlık veya aracı kurum) olması gerekir. Pure-software indikatör satıcıları bu lisanslara sahip olamadıkları için G2RS doğrulamasını geçemezler ve bu ülkelerden kalıcı olarak elenirler.

---

## 3. Landing Page & Ad Copy Uyum Kuralları (US Pazarı İçin)

Eğer yalnızca Amerika Birleşik Devletleri (US) pazarında kısıtlı bir Google Ads arama kampanyası test edilecekse, landing page ve reklam kopyalarında şu kuralların uygulanması zorunludur:

### 3a. Yasaklı ve İzin Verilen Kelime Matrisi
| 🚫 Yasaklı Kelimeler (Otomatik Askı Tetikler) | ✅ İzin Verilen Alternatifler |
| :--- | :--- |
| Trading Signals / Sinyaller | Technical Analysis Indicators / Teknik İndikatörler |
| Buy/Sell Alerts / Al-Sat Uyarıları | Market Structure Visualization / Piyasa Yapısı Çizimi |
| Auto-Trading Bot / Otomatik Bot | Educational Charting Tool / Çizim Yardımcısı |
| Guaranteed Profit / Kesin Kâr | Research-based Software / Araştırma Odaklı Yazılım |
| Win Rate: 80% / Kâr Oranı | Open Source Backtest Framework / Backtest Altyapısı |

### 3b. Landing Page Üzerinde CFTC Rule 4.41 Disclaimers Zorunluluğu
Landing page'in en altında, gizlenmemiş ve kolayca okunabilir biçimde şu yasal uyarı yer almalıdır:
> **CFTC RULE 4.41:** Hypothetical or simulated performance results have certain limitations. Unlike an actual performance record, simulated results do not represent actual trading. Also, since the trades have not been executed, the results may have under-or-over compensated for the impact, if any, of certain market factors, such as lack of liquidity. Simulated trading programs in general are also subject to the fact that they are designed with the benefit of hindsight. No representation is being made that any account will or is likely to achieve profit or losses similar to those shown.

---

## 4. Bütçe Yeniden Tahsis & Fallback Planı

Google Ads'in global bazda NO-GO olması sebebiyle, planlanan pazarlama bütçesi aşağıdaki organik büyüme kanallarına aktarılacaktır:

```
                  ┌───────────────────────────────────────────┐
                  │   Google Ads Bütçesi (%100 Yeniden Sevk)  │
                  └─────────────────────┬─────────────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│ TV Script SEO    │           │ YouTube Organic  │           │  X / Telegram    │
│ (Lead Magnet)    │           │ (Build-in-Public)│           │ (Community Build)│
└──────────────────┘           └──────────────────┘           └──────────────────┘
```

### 1. TradingView Public Script Library SEO (En Kritik Kanal)
* **Playbook:** LuxAlgo modelinin başarısının arkasındaki ana motor. Ücretsiz `wave1_signals.pine` indikatörü TradingView public kütüphanesinde yayınlanır.
* **Yöntem:** Başlık ve açıklama kütüphanesi "SMC, Order Blocks, Liquidity, FVG" anahtar kelimeleriyle optimize edilir. TradingView kütüphanesinde üst sıralara tırmanarak waitlist linkine (landing page) organik trafik çekilir.
* **Avantajı:** Google Ads politikalarına takılmaz, sıfır reklam maliyeti üretir ve doğrudan TradingView kullanan sıcak hedef kitleye ulaşır.

### 2. YouTube Eğitici İçerik Pazarlaması (Build-in-Public)
* **Yöntem:** Canlı engine'in performansını, indikatörün grafik üzerindeki backtest sonuçlarını dürüstçe gösteren haftalık videolar yayınlanır. Kâr vaadi vermeden, "algoritmik trading geliştirme günlüğü" formatında ilerlenir.
* **Avantajı:** Yüksek güven unsuru oluşturur, uzun vadeli organik trafik sağlar.

### 3. X (Twitter) ve Telegram Komünite Yönetimi
* **Yöntem:** Günlük teknik analiz grafikleri ve indikatörün belirlediği Piyasa Yapısı (BOS/CHoCH) kırılımları X üzerinde paylaşılır. Telegram kanalı waitlist durum güncellemeleri ve teknik eğitim grubu olarak konumlandırılır.

---

## 5. Google Ads US Yayına Hazırlık Sertifikasyon Checklist'i

Eğer US pazarında deneme amaçlı arama ağı reklamı açılması kararlaştırılırsa, geçilmesi gereken adımlar:

- [ ] **[CMP-1]** Landing page'e CFTC Rule 4.41 uyarısı ve genel risk bildirimi eklendi.
- [ ] **[CMP-3]** Landing page yardımı ve reklam metinleri `scripts/content_compliance.py` üzerinden geçirilerek $ ve kâr yüzdesi içeren tüm kelimeler temizlendi.
- [ ] **[ADS-1]** GA4 ve Google Ads conversion tracking entegrasyonu tamamlandı.
- [ ] **[ADS-2]** Sadece branded ("u2algo") ve long-tail keywords ("tradingview order block indicator") belirlendi, yüksek rekabetli generic keywords elendi.
- [ ] **[ADS-4]** `cac_gate.json` dosyası `gate_open=true` durumuna geldi ve organik conversion kanıtlandı.
- [ ] **[@operator]** Reklam bütçesi limitleri tanımlandı ve onay imzası alındı.
- [ ] **[@operator]** Advertiser identity verification (Reklamveren kimlik doğrulaması) tamamlandı.
