# Changelog

u2algo'nun müşteri-görünür değişiklikleri bu dosyada listelenir.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · tarihler UTC.
Site "Güncellemeler" bölümü bu dosyadan beslenir
(`u2algo-site/scripts/changelog-to-updates.js` → `u2algo-site/updates.json`).

> Not: Bu dosya yalnız ürün/müşteri perspektifinden yazılır — iç operasyon,
> altyapı ve güvenlik detayları burada yer almaz. Geçmiş performans gelecek
> getiri taahhüdü değildir.

## [Unreleased]

### Eklendi
- **BOS (Break of Structure) kırılımları da giriş üretiyor:** bot artık yalnız
  CHoCH (dönüş) değil, BOS (trend devamı) kırılımlarında da pozisyon arıyor.
  Her iki kırılım türü de aynı bekle-onayla akışından geçiyor: HTF bias uyumu →
  kırılımı yapan OB/BB bölgesi → geri çekilmede retest → engulfing teyidi →
  limit emir (SL likidite çizgisinde). Büyük pump/devam hareketlerinde fırsat
  kaçırma azaltıldı.
- **TradingView "EFloud Signals v2" + "EFloud Strategy v2" (Pine v6):** bot'un
  SMC v2 bekle-onayla durum makinesi artık grafikte — 0-100 confluence skoru,
  Order Block / FVG / OTE bölge zinciri, TP1/TP2 merdiveni, grafik üstü panel.
  Her iki betik sıfır hatayla derlendi; strateji sürümüyle backtest alınabilir.
- **Repaint'siz sinyaller:** tüm üst zaman dilimi verisi yalnızca kapanmış
  barları kullanacak şekilde yeniden düzenlendi — grafikte canlı gördüğünüz
  sinyal, backtest'te göreceğinizle birebir aynıdır.
- **Şeffaf edge ölçümü:** bot artık ürettiği her sinyalin varsayımsal sonucunu
  komisyon + funding + kayma maliyetlerini düşerek kendi üzerinde ölçüyor ve
  istatistiksel yeterlilik eşiğiyle raporluyor. Strateji kalibrasyonları bu
  canlı veriye dayanarak yapılacak.
- 7/24 bağımsız izleme katmanı güçlendirildi: devre kesici, marjin ve pozisyon
  tutarlılığı denetimleri trading döngüsünden ayrı, kendi ritminde çalışıyor.
- Türkçe ve Rusça dokümantasyon paketleri (README.tr.md / README.ru.md).

### Değişti
- **Acil bakiye HALTI kaldırıldı:** mutlak bakiye eşiği devre dışı bırakıldı
  (emergency_balance_threshold=0). Fon koruması artık günlük %10 ve haftalık
  %25 kayıp limitleriyle sağlanıyor; düşük bakiyede bot kalıcı HALTED
  durumunda kalmıyor.
- **Volatil rejimde girişler açıldı:** yüksek volatilite (ATR genişlemesi)
  artık girişleri engellemiyor — SMC pullback stratejisi volatil piyasa için
  tasarlandığından girişler rejim kapısına takılmıyor.
- **Bölge aşım toleransı genişletildi:** hedef bölgenin uzak kenarını aşan
  fiyatlar için tolerans 0.5 → 2.0 ATR'ye çıkarıldı; bölgeye yakın geri
  çekilmelerde setup'lar daha az eleniyor.
- **CHoCH sonrası giriş OB/BB bölgesinden:** kırılım anında market emri yerine
  kırılımı yapan Order Block / Breaker Block bölgesine geri çekilme bekleniyor
  ve giriş o bölgeden yapılıyor.
- TradingView "u2algo SMC — Wave 1" göstergesinin yerini gelişmiş
  "EFloud Signals v2" aldı.
- Aylık performans özeti otomasyonu (yayın öncesi iç doğrulama aşamasında).

## [2026-06-11]

### Eklendi
- Hizmet çalışma süresi (uptime) ölçümü: "servis aktif" ve "trading aktif"
  ayrı metrikler olarak izleniyor; güvenlik kaynaklı duraklatmalar (safety
  suspension) hata olarak değil, ayrı kategori olarak etiketleniyor.
- Site "Güncellemeler" bölümü (bu liste).
- Hizmet taahhütleri: SLA ve hizmet sürekliliği dokümanları hazırlandı
  (erken erişim açılmadan önce yayınlanacak).

## [2026-06-10]

### Eklendi
- Performans kanıt altyapısı: günlük kapanış bazlı, normalize edilmiş equity
  eğrisi — hesap büyüklüğü hiçbir zaman paylaşılmaz, yalnız kapanmış işlemler
  sayılır. Doğrulanmış raporlar hazır oldukça sitede yayınlanacak.
