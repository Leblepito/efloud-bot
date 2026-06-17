# u2algo Cold-Start Playbook: First 100 Users (TVS-1 Integration)

**Tarih:** 2026-06-17  
**Hazırlayan:** 🟦 Gemini (Growth Layer / Organic Acquisition Specialist)  
**Durum:** `taslak (operator onayı bekliyor)`  
**Referans:** §4.1 SEO, §4.3 SD, TVS-1

---

## 1. Giriş ve Stratejik Çerçeve

Sıfır takipçili ve sıfır marka bilinirliğine sahip yeni bir algoritmik trading markası (`u2algo`) için en zor aşama, ilk 100 aktif waitlist kullanıcısını kazanmaktır. Paid reklam kanallarının askıya alındığı (parked) ve organik büyümenin önceliklendirildiği bu aşamada, growth motorunun yakıtı **aktif topluluk etkileşimi** ve **değer-odaklı pazarlamadır (value-first marketing)**.

Bu playbook, ücretli reklam harcaması yapmadan, SMC/ICT (Smart Money Concepts / Inner Circle Trader) nişindeki sıcak kitlelere ulaşarak ilk 100 kullanıcıyı `u2algo.com` waitlist hunisine çekmek için uygulanacak somut, adım adım taktikleri tanımlar.

---

## 2. TradingView Ekosistemi ve TVS-1 Entegrasyonu

TradingView, SMC ve teknik analiz odaklı trader'ların en yoğun bulunduğu platformdur. Ücretsiz `wave1_signals.pine` indikatörümüz, bu kitleye ulaşmak için ana "lead-magnet" unsurumuzdur.

### Taktik 2a. Sektör İndikatörleri Q&A Katılımı
* **Eylem:** Kütüphanedeki en popüler SMC indikatörlerinin (örneğin LuxAlgo Smart Money Concepts, vb.) yorum ve soru-cevap alanları taranmalıdır.
* **Taktik:** Kod hataları alan, indikatörün çalışma mantığını (örneğin "Breaker Block nasıl çiziliyor?", "Repaint var mı?") soran kullanıcılara, tamamen teknik ve yapıcı yanıtlar verilmelidir.
* **Tonalite & Linkleme:** Yanıtlar asla doğrudan reklam veya spam içermemelidir. Profilimiz üzerinden ücretsiz scriptimize yönlendirme yapılabilir (örneğin: *"I explained a similar open-source visual approach in my public script profile if you want to check the Pine v6 code directly."*).

### Taktik 2b. Pine Script Topluluk Forumları
* **Eylem:** TradingView Pine Script sohbet odaları ve resmi forumlarında aktif olunmalıdır.
* **Taktik:** Pine v6 geçişleri, optimize swing tespiti ve RE10045 runtime hatası gibi teknik zorlukları aşma yöntemlerimiz (inline detection vb.) açık kaynak kod paylaşımları ile topluluğa sunulmalıdır. Geliştirici kimliği ile itibar inşa etmek, profesyonel trader kitlesini waitlist'e çekmenin en organik yoludur.

---

## 3. X (Twitter) "Reply-Guy" ve Grafik Kültürü

X platformu, kripto ve finansal grafiklerin anlık paylaşıldığı ana mecradır. Sıfır takipçi ile X'te görünürlük elde etmenin tek yolu, yüksek takipçili hesapların altındaki etkileşim alanlarını (replies) domine etmektir.

### Taktik 3a. Değer-Odaklı Grafik Yorumculuğu (Reply-Guy)
* **Hedef Hesaplar:** SMC/ICT alanındaki popüler trader'lar ve fenomenler (örneğin ICT, MentFx vb. hesaplar ile popüler kripto analistleri).
* **Eylem:** Bu hesapların paylaştığı güncel analizlerin altına, `wave1_signals.pine` indikatörümüzün çizdiği temiz grafikler ve piyasa yapısı (BOS/CHoCH, swing HH/LL, aktif OB/Breaker bölgeleri) ekran görüntüsü olarak eklenmelidir.
* **Kural:** Reklam kopyası yazılmamalıdır. Sadece grafik ve nesnel teknik analiz verisi paylaşılmalıdır: *"15m chart shows a clear bullish OB mitigation at this lower edge, aligned with 1h HTF bias."*

### Taktik 3b. "Build-in-Public" Günlükleri
* **Eylem:** Algoritmanın geliştirilme sürecindeki aşamalar, backtest optimizasyonları ve dürüst araştırma logları (research log) flood (thread) halinde paylaşılmalıdır.
* **Taktik:** Canlı motorun negatif performans gösterdiği dönemler de dahil olmak üzere, tüm metrikler şeffaf bir şekilde "Single-config research log" başlığı altında paylaşılmalı, trader komünitesine dürüstlük ve şeffaflıkla yaklaşılmalıdır.

---

## 4. Telegram ve Discord SMC Komünite Katılımı

Birçok profesyonel trader, özel veya yarı-açık Telegram kanallarında ve Discord sunucularında SMC konseptlerini tartışmaktadır.

### Taktik 4a. Discord Sunucularında Teknik Mentorluk
* **Eylem:** Popüler SMC eğitim sunucularına katılınmalıdır.
* **Taktik:** "Chart-share" kanallarında indikatörümüzün ürettiği temiz grafikler paylaşılmalı ve diğer üyelerin grafik analizlerine teknik geri bildirimler verilmelidir. İnsanlar grafiklerin temizliğini gördükçe indikatörü nereden indirebileceklerini soracaklardır.
* **Yönlendirme:** İlgilenen kişilere TradingView kütüphane linkimiz veya `u2algo.com/?utm_source=discord` UTM linkimiz doğrudan mesaj (DM) veya sohbet içinde doğal bir tavsiye olarak iletilmelidir.

### Taktik 4b. Telegram Gruplarında Bilgi Paylaşımı
* **Eylem:** Kripto ve FX analiz gruplarında aktif tartışmalara katılınmalıdır.
* **Taktik:** Günlük FVG ve likidite boşluğu (liquidity sweep) analizleri indikatörümüzün çıktıları referans gösterilerek paylaşılmalıdır. Grup yöneticileri ile iyi ilişkiler kurularak ücretsiz açık kaynaklı aracımızın grupta pinlenmesi veya tanıtılması sağlanabilir.

---

## 5. Politika Uyumluluk ve Yasal Sınırlar (Compliance-Gate)

Tüm cold-start paylaşımlarında, yorumlarında ve sosyal medya yanıtlarında `content_compliance.py` kuralları ve marka ilkeleri tavizsiz uygulanacaktır:

1. **Finansal Vaat Yasağı:** Hiçbir paylaşımda kâr vaadi, win-rate oranı, getiri yüzdeleri veya mutlak para tutarları ($, USD) yer alamaz.
2. **Framing Uyum Kontrolü:** İndikatörden bahsederken "sinyal", "al-sat uyarısı", "trading botu" yerine **"educational charting tool"** (eğitsel çizim aracı) veya **"market structure visualization software"** (piyasa yapısı görselleştirme yazılımı) terimleri kullanılacaktır.
3. **Zorunlu Yasal Uyarı:** Uzun metinlerin ve topluluk duyurularının altına mutlaka İngilizce risk uyarısı eklenmelidir:
   > *Not investment advice. Trade at your own risk.*

---

## 6. Cold-Start Metrikleri ve Başarı Kriterleri (KPIs)

İlk 100 kullanıcının kazanım sürecini takip etmek için kullanılacak metrikler:

| Metrik | Hedef / Eşik Değer | Takip Yöntemi | Açıklama |
| :--- | :---: | :--- | :--- |
| **Waitlist UTM Kayıtları** | 100 Kullanıcı | Plausible / GA4 / Supabase | `utm_source=tradingview` veya `utm_source=x` etiketli net waitlist kayıt sayısı. |
| **TradingView Script Favori Oranı** | 50+ Beğeni | TradingView Dashboard | TV script sayfasındaki organik beğeni (boost) sayısı. |
| **Organik Erişim (X Replies)** | 10,000+ Gösterim | X Analytics | Yapılan replies paylaşımlarının toplam görüntülenme sayısı. |
| **Dönüşüm Oranı (Waitlist %)** | >= 3% | GA4 Funnel Events | u2algo.com ziyaretçilerinin waitlist formunu doldurma oranı. |
