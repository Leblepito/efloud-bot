# u2algo İlk Sosyal Paylaşım — Final Onay Paketi

Durum: HAZIR TASLAK / YAYIN İÇİN MANUEL ONAY GEREKİR.

Bu paket u2algo public launch için compliance-safe metinleri ve görsel assetleri içerir. Hiçbir sosyal platforma otomatik yayın yapılmamıştır.

## 1. Yayın Kararı

Önerilen karar: Şimdilik yayınlama, onay beklet.

Neden:
- `u2algo.com` ve `www.u2algo.com` custom domainleri daha önce DNS/TLS açısından doğrulanmış değildi.
- Manus readiness raporuna göre Instagram connector hedef `@u2algo` yerine farklı hesaba bağlıydı.
- X/Twitter, Telegram ve YouTube için doğrulanmış native yayın connector’ı yoktu.
- Sosyal yayınlar manuel onay kapısından geçmeli.

Güvenli alternatif:
- İçerikler hazır tutulur.
- DNS/TLS `https://u2algo.com/healthz` ve `https://www.u2algo.com/healthz` 200 döndüğünde yayın onayı alınır.
- Instagram connector hedef `@u2algo` hesabına bağlanmadan otomatik paylaşım yapılmaz.

## 2. Görsel Assetler

Klasör:
`u2algo-site/launch-assets/2026-05-31-first-share/`

Dosyalar:
- `x-launch-1600x900.png` — X/Twitter 16:9 görsel.
- `instagram-carousel-cover-1080x1080.png` — Instagram carousel kapak görseli.
- `shorts-cover-1080x1920.png` — Reels/Shorts dikey kapak görseli.
- SVG kaynakları:
  - `x-launch-1600x900.svg`
  - `instagram-carousel-cover-1080x1080.svg`
  - `shorts-cover-1080x1920.svg`
- Metin dosyası:
  - `captions.md`

Görsel kalite kontrol:
- X görseli: okunabilir, 16:9 oran uygun, çakışma yok.
- Instagram görseli: okunabilir, 1:1 oran uygun, çakışma/taşma giderildi.
- Shorts/Reels görseli: okunabilir, 9:16 oran uygun, sağdaki MCP etiketi kırpılmayacak şekilde kısaltıldı.

## 3. X / Twitter Final Post

u2algo public site hazırlandı: efloud-bot tabanlı SMC ve risk-disiplinli algoritmik trading araştırmasını artık TradingView + MCP gözlem katmanı ile daha açıklanabilir gösteriyoruz.

Botun takip ettiği coin evreni, chart üzerindeki hareket markerları ve scalp/mid/long profilleri tek deneyimde.

Yatırım tavsiyesi değildir. DYOR. Kripto ve kaldıraçlı işlemler yüksek risk içerir.

Link: https://u2algo.com/

Kullanılacak görsel:
`u2algo-site/launch-assets/2026-05-31-first-share/x-launch-1600x900.png`

Yayın notu:
- `https://u2algo.com/` ve `https://u2algo.com/healthz` 200 OK olmadan linkli public paylaşım yapılmamalı.
- Gerekirse link çıkarılıp “launch hazırlığında” formatında paylaşılabilir.

## 4. Instagram Carousel Caption

u2algo public site launch hazırlığı tamamlandı.

Bu bir “kesin sinyal” servisi değil; efloud-bot tabanlı SMC yaklaşımını, risk disiplinini ve botun analiz akışını daha şeffaf hale getiren build-in-public araştırma katmanı.

Yeni TradingView + MCP gözlem bölümüyle botun takip ettiği coin evreni ve önemli hareket markerları chart üzerinde daha okunabilir hale geliyor.

Yatırım tavsiyesi değildir. DYOR. Kripto piyasaları ve kaldıraçlı işlemler yüksek risk içerir; kararlarınızdan siz sorumlusunuz.

#u2algo #algoritmiktrading #tradingview #riskmanagement #dyor

Kullanılacak görsel:
`u2algo-site/launch-assets/2026-05-31-first-share/instagram-carousel-cover-1080x1080.png`

Yayın notu:
- Sadece hedef hesap `@u2algo` doğrulanırsa kullanılmalı.
- `@leblepito` hesabına otomatik gönderim yapılmamalı.

## 5. Telegram Topluluk Duyurusu

Merhaba u2algo topluluğu,

u2algo public site ve ilk launch içerik paketi hazırlandı. Yeni yapı, efloud-bot tabanlı SMC ve risk-disiplinli algoritmik trading araştırmasını daha şeffaf şekilde göstermek için TradingView + MCP gözlem katmanını öne çıkarıyor.

Botun takip ettiği coin evreni, chart üstü hareket markerları ve scalp/mid/long trade profilleri tek yerde anlatılıyor.

Not: Custom domain DNS/TLS ve sosyal connector kontrolleri tamamlanmadan dış paylaşıma geçmiyoruz. Bu yaklaşım bir kâr vaadi veya yatırım yönlendirmesi değildir.

Yatırım tavsiyesi değildir. DYOR. Kripto ve kaldıraçlı işlemler yüksek risk içerir.

Yayın notu:
- `@Ualgo_bot` ve u2algo topluluğu bağlantısı netleşince manuel gönderim önerilir.

## 6. YouTube Shorts / Reels Açıklaması

u2algo, efloud-bot tabanlı SMC araştırmasını TradingView + MCP gözlem katmanıyla daha açıklanabilir hale getiriyor. Amaç getiri vaadi değil; bot analiz akışını, risk disiplinini ve chart üstü hareket markerlarını şeffaf biçimde göstermek.

Yatırım tavsiyesi değildir. DYOR. Kripto piyasaları yüksek risk içerir.

Kullanılacak görsel:
`u2algo-site/launch-assets/2026-05-31-first-share/shorts-cover-1080x1920.png`

## 7. Yayın Öncesi Zorunlu Checklist

- [ ] `https://u2algo.com/healthz` 200 OK.
- [ ] `https://www.u2algo.com/healthz` 200 OK.
- [ ] `https://u2algo.com/robots.txt` 200 OK.
- [ ] `https://u2algo.com/sitemap.xml` 200 OK.
- [ ] Instagram connector hedef hesap `@u2algo` olarak doğrulandı.
- [ ] X/Twitter yayın hesabı `@Ualgobot` manuel veya connector ile doğrulandı.
- [ ] Telegram yayın hedefi `@Ualgo_bot` / u2algo topluluğu doğrulandı.
- [ ] YouTube hedef `@Leblepito` için manuel upload veya connector akışı doğrulandı.
- [ ] Kullanıcı final yayın onayı verdi.

## 8. Compliance Sonucu

Zorunlu ifadeler mevcut:
- “Yatırım tavsiyesi değildir”
- “DYOR”
- “Risk”

Yasak vaatler kullanılmadı:
- Getiri/kâr garantisi yok.
- Fon toplama yok.
- Para yönetimi vaadi yok.
- Geçmiş performansın geleceği garanti ettiği ima edilmiyor.

## 9. Teknik Not

Waitlist endpoint’i için public formun 500 göstermemesi amacıyla local JSONL fallback hazırlandı:
- Supabase hazırsa Supabase’e upsert eder.
- Supabase eksik veya sağlıksızsa `local-jsonl` fallback ile 200 döner.
- Bu geçici güvenli fallback’tir; production lead yönetimi için Supabase migration ve env değerleri ayrıca düzeltilmelidir.
