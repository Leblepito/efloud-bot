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
- TradingView "u2algo SMC — Wave 1" göstergesi (ücretsiz): çekirdek sinyal
  mantığı tamamlandı ve derleme doğrulamasından geçti; strateji (backtest)
  sürümü üzerinde çalışılıyor. Yayın, doğrulama tamamlanınca duyurulacak.
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
