# TradingView Script SEO & Lead-Magnet Optimization (TVS-1)

**Tarih:** 2026-06-17  
**Hazırlayan:** 🟦 Gemini (Growth Layer / Organic Acquisition Specialist)  
**Durum:** `inceleme_bekliyor`  
**Referans:** §4.1 SEO, §4.2 CON, §4.3 SD

---

## 1. Yönetici Özeti

TradingView Public Script Library, `u2algo`'nun sıfır reklam bütçesi ile doğrudan hedef kitleye ulaşabileceği (built-in audience) en yüksek kaldıraçlı organik kanaldır. TradingView'in dahili arama motoru optimizasyonu (SEO), LuxAlgo gibi pazar liderlerinin büyümelerini borçlu olduğu ana motordur. Bu çalışma, `wave1_signals.pine` indikatörünün TradingView kütüphanesinde üst sıralara tırmanması, maksimum etkileşim alması ve ziyaretçileri `u2algo.com` waitlist hunisine UTM parametreleri ile yönlendirmesi için tasarlanmış uçtan uca strateji rehberidir.

---

## 2. Arama Algoritması, Başlık ve Etiket Stratejisi

TradingView arama algoritması, script listelemesindeki başlık (Title), açıklama (Description) ve etiketlerdeki (Tags) anahtar kelime eşleşmelerine ve yoğunluğuna ek olarak şu faktörleri ağırlıklandırır:
* **Etkileşim Hızı (Velocity):** Yayınlandıktan sonraki ilk 24-48 saatte gelen beğeni (boost/like) ve yorum sayısı.
* **Kullanım Sayısı (Active Installs):** Kullanıcıların scripti grafiklerine ekleme oranı.
* **Güncelleme Sıklığı (Update Cadence):** Scriptin düzenli olarak güncellenmesi ve sürüm notlarının girilmesi.

### 2a. Başlık (Title) Stratejisi
Başlıklar hem TradingView'in dahili arama indeksinde hem de Google gibi dış arama motorlarında yüksek hacimli arama sorgularıyla tam eşleşmelidir. TradingView başlık limiti **60 karakterdir**.

| Başlık Önerisi | Karakter | Hedeflenen Arama Sorguları / Anahtar Kelimeler | Konumlandırma |
| :--- | :---: | :--- | :--- |
| **Smart Money Concepts (SMC) & Order Block Detector [u2algo]** | 59 | Smart Money Concepts, SMC, Order Block Detector | **(Önerilen)** Teknik özellik vurgulu, en popüler sorgularla eşleşen dengeli başlık. |
| **SMC Order Block & FVG Liquidity Indicator by u2algo** | 51 | SMC, Order Block, FVG Liquidity, SMC Indicator | FVG ve likidite arayan kullanıcılara yönelik teknik odaklı başlık. |
| **ICT Market Structure & Breaker Block Tool - u2algo** | 50 | ICT, Market Structure, Breaker Block, Market Structure Tool | ICT konsepti ve Market Structure aramaları için optimize başlık. |

### 2b. Etiket (Tags) Stratejisi
TradingView script yayınlanırken en fazla **5 etiket** seçilmesine izin verir. Aşağıdaki etiketlerin kullanılması zorunludur:
1. `smart-money-concepts` (Birincil yüksek hacimli kategori)
2. `order-block` (Teknik özellik aramaları)
3. `fair-value-gap` (FVG aramaları)
4. `market-structure` (Trend ve yapı analizleri)
5. `liquidity` (Destekleyici konsept araması)

---

## 3. Politika Uyumlu Açıklama Metni (Description Copy)

TradingView, kâr vaadi veren, abartılı getiri iddialarında bulunan ve açıkça ticari ürün satışı yapan açıklamaları kabul etmez, şikayet durumunda scripti kütüphaneden kalıcı olarak kaldırır. 

Metin yazılırken şu kurallara dikkat edilmiştir:
* **Framing:** Ürün kesinlikle "sinyal servisi", "otomatik trading botu" veya "kâr makinesi" olarak adlandırılmamıştır. **"Educational charting tool"** (eğitsel grafik çizim aracı) olarak konumlandırılmıştır.
* **Compliance:** Metin, `scripts/content_compliance.py` kuralları doğrultusunda hiçbir `$` işareti, mutlak para birimi (USD, USDT) ve getiri yüzdesi (win-rate, % kâr) içermemektedir.
* **Disclaimers:** CFTC Rule 4.41 standardında yasal uyarı ve zorunlu İngilizce risk disclaimers metne gömülmüştür.

### TradingView Script Tanıtım Metni (Copywriting)

```markdown
// This indicator is an educational charting tool designed to assist traders in visualizing key Market Structure and Smart Money Concepts (SMC) on TradingView. It automates the detection of essential technical analysis patterns, allowing for clean chart study and structural research.

### Key Visual Features Detectable:
* **Market Structure Mapping (Swing Levels):** Automatically plots swing highs and swing lows (HH, LH, LL, HL) based on localized price action filters to assist in trend analysis.
* **Order Blocks & Breaker Zones:** Highlights potential historical support/resistance areas by mapping consecutive opposing candle structures. These zones automatically update when breached.
* **Fair Value Gaps (FVG):** Visualizes inefficiencies and imbalances directly on the chart, indicating zones where liquidity was rapidly consumed.
* **Equal Highs & Equal Lows (EQH/EQL):** Identifies potential double tops or double bottoms representing pools of resting liquidity.

### Educational Risk/Reward Projections:
The tool features optional visualization tools for Risk-to-Reward (R:R) analysis:
* **Reference Levels:** Displays theoretical entry, stop-loss, and target regions based on user-configured ATR parameters.
* **Multi-Timeframe Trend Dashboard:** Shows higher timeframe bias indicators to help conceptualize internal vs. external structure.

### How to Use:
1. Use this tool for technical analysis education and market structure research.
2. Adjust input settings (ATR multipliers, swing lookbacks) to match your chart's asset volatility.
3. Combine this tool with your own risk management discipline.

---

Not investment advice. Trade at your own risk.

CFTC RULE 4.41: Hypothetical or simulated performance results have certain limitations. Unlike an actual performance record, simulated results do not represent actual trading. Also, since the trades have not been executed, the results may have under-or-over compensated for the impact, if any, of certain market factors, such as lack of liquidity. Simulated trading programs in general are also subject to the fact that they are designed with the benefit of hindsight. No representation is being made that any account will or is likely to achieve profit or losses similar to those shown.
```

---

## 4. Ekran Görüntüsü ve Grafik Tasarım (Screenshot Brief)

TradingView'de script kapak resmi, kullanıcının tıklama oranını (CTR) doğrudan etkileyen ilk temas noktasıdır. 
* **YASAK:** Higgsfield veya herhangi bir yapay zeka tarafından oluşturulmuş genel/abartılı tasarımlar, yanıltıcı ok/etiket eklemeleri kesinlikle yasaktır.
* **ZORUNLU:** Temiz, anlaşılır ve şeffaf TradingView grafik ekran görüntüleri kullanılmalıdır.

### Görsel Kompozisyon Gereksinimleri
1. **Sembol ve Timeframe:** Büyük ölçekli, likit bir parite (tercihen `BTCUSDT` veya `ETHUSDT`) ve `15m` (15 dakikalık) grafik seçilmelidir. Bu, yapı kırılımlarının ve FVG'lerin en dengeli göründüğü aralıktır.
2. **Tema:** TradingView Koyu Tema (Dark Mode) kullanılmalıdır. Arka plan ızgara çizgileri (grid lines) tamamen kapatılmalı veya en minimal seviyeye (%5 opaklık) indirilmelidir.
3. **Renk Paleti Tutarlılığı:** Kutu ve çizgi renkleri `wave1_signals.pine` içinde tanımlı standart palet ile uyumlu olmalıdır:
   * **Bullish Order Blocks:** `color.new(#0EA5E9, 85)` (Sky Blue)
   * **Bearish Order Blocks:** `color.new(#6366F1, 85)` (Indigo)
   * **FVG Zones:** `color.new(#00f0ff, 90)` (Cyan)
   * **Liquidity Lines:** `color.new(#a855f7, 50)` (Purple)
4. **Çizim Detayları:** Grafikte en az bir adet tetiklenmiş "Bullish OB", bir adet "Bearish OB", bir adet belirgin "FVG" ve "EQH/EQL" çizgisi açıkça görünmelidir.
5. **UI Temizliği:** Grafik üzerindeki gereksiz indikatörler, hacim barları ve çok kalabalık fiyat etiketleri kapatılarak sadece u2algo'nun çizdiği yapılar odak noktası haline getirilmelidir.

---

## 5. Pinned-Comment ve Cross-Link Stratejisi

TradingView topluluk kuralları gereği, script açıklaması içerisine ticari sitelerin linkleri doğrudan eklenemez. Ancak, scriptin altında yer alan **sabitlenmiş yorum (pinned comment)** alanı, web sitesine organik trafik çekmek için meşru ve kurallara uygun tek alandır.

### Sabitlenmiş Yorum Yapısı
Yayıncı (operatör hesabı) script yayınlandığı anda ilk yorumu yazar ve bu yorumu tepeye sabitleyerek u2algo.com landing page waitlist linkini paylaşır. Linkler mutlaka UTM parametreleri ile donatılmalıdır:

* **Hedef URL:**
  `https://u2algo.com/?utm_source=tradingview&utm_medium=organic&utm_campaign=tv-public-script&utm_content=wave1`

* **Yorum Metni (EN):**
  > 📢 **Access & Updates:**
  > This is a fully open-source charting tool for the community. If you want to follow our algorithmic development journey, receive regular educational updates, or join the early-access waitlist for our private beta dashboard, check out our website here: [u2algo.com](https://u2algo.com/?utm_source=tradingview&utm_medium=organic&utm_campaign=tv-public-script&utm_content=wave1)

* **Yorum Metni (TR - Destek):**
  > 📢 **Erişim ve Güncellemeler:**
  > Bu araç topluluk için tamamen açık kaynaklı bir grafik çizim asistanıdır. Algoritmik geliştirme sürecimizi takip etmek, eğitim içeriklerine erişmek veya özel beta paneli erken erişim bekleme listesine katılmak için web sitemizi ziyaret edebilirsiniz: [u2algo.com](https://u2algo.com/?utm_source=tradingview&utm_medium=organic&utm_campaign=tv-public-script&utm_content=wave1)

---

## 6. Boost ve Etkileşim Playbook'u (Launch & Update Cadence)

Scriptin kütüphanede üst sıralara tırmanması (trending listesine girmesi) için ilk 48 saat kritik öneme sahiptir. Bu süreci optimize etmek için uygulanacak adımlar:

### Adım 1: İç Etkileşim Tetikleme (İlk 6 Saat)
* **Ekip Beğenileri:** Ekipteki tüm üyelerin TradingView hesaplarından script sayfasına girilerek "Boost" (Beğeni) butonuna basılması sağlanmalıdır (en az 5-10 doğal boost).
* **İlk Yorumlar:** Yazarın sabitlediği yorumun altına, teknik sorular soran veya teşekkür eden en az 3-4 yapıcı kullanıcı yorumu yazılmalı ve yazar tarafından cevaplanmalıdır. Etkin yorum döngüleri TradingView algoritmasında yüksek puan alır.

### Adım 2: Topluluk Dağıtımı (İlk 24 Saat)
* **X (Twitter) Duyurusu:** X kanalı üzerinden TradingView script linki paylaşılmalı, TradingView SMC topluluğuna yönelik hashtag'ler (`#SmartMoneyConcepts`, `#TradingView`, `#OrderBlock`) eklenerek organik trafik yönlendirilmelidir.
* **Telegram Duyurusu:** Waitlist kanalındaki kullanıcılara "Kütüphanedeki yeni açık kaynaklı aracımızı grafiklerinize ekleyip destek olabilirsiniz" çağrısı yapılmalıdır.

### Adım 3: Sürüm Güncelleme Döngüsü (Update Cadence)
* TradingView, güncellenen scriptleri "Recently Updated" sekmesinde öne çıkarır. 
* Operatör, **her 10-14 günde bir** script kodunda minör görsel iyileştirmeler (örneğin kutu sınır çizgisi kalınlığı, etiket rengi optimizasyonu veya ufak performans iyileştirmeleri) yaparak script sayfasından "Publish New Version" seçeneği ile güncellemeler yayınlamalıdır.
* Her güncellemede, sürüm notlarına waitlist daveti (UTM linkli) eklenmelidir.
