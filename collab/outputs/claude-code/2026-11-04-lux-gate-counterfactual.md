# LuxAlgo kapı reddleri — NET-cost karşı-olgu ölçümü (T-20261104-09)

- **Kaynak:** motor/config `master@6bea1e4` (canlı `configs/config.phase2_1k.yaml`, LuxAlgo modu açık);
  Binance USDT-M 15m/12h, 10 canlı sembol, **60 gün** (2026-08-28 → 11-04).
- **Üretim:** 2026-11-04 ~23:50 +03 · claude-code · ebeveyn: OB-entry-gap raporu (#273).
- **Yalnız ölçüm.** Hiçbir kapı/config değişikliği önerilmez; önerilirse default-OFF bayrak + TDD +
  risk-ops review + operatör onayı gerekir. Script'ler ve ham veri git dışında (laptop).

## 0. Kısa sonuç

1. **Kapıları gevşetmek için kanıt yok.** 12h trend, premium/discount, confluence ve recency kapılarının
   elediği dokunuşlar alınsaydı NET sonuç her birinde negatif (−0.17 ile −0.32 R/işlem). Bu kapılar
   kaybettiren işlemleri dışarıda tutuyor.
2. **Asıl bulgu başka: motorun bugün aldığı işlemler de NET negatif.** Kapıların hepsini geçen
   dokunuşlar (baz kategori) 60 günde 217 işlem, **−0.30 R/işlem, PF 0.65**. Brüt sonuç başa baş
   (−0.03 R); farkı **işlem maliyeti** açıyor: SL'ler dar (medyan fiyatın %0.72'si), bu yüzden
   komisyon + slippage + funding işlem başına ~0.27 R yiyor.
3. **Tek pozitif ve tutarlı kategori: motor penceresinde zaten mitige olmuş OB'ye dönüş** (breaker
   benzeri retest, motorun engulfing teyidiyle): 30 işlem, +0.24 R, IS +0.23 / OOS +0.25, 10 sembolün
   5'inde pozitif. Eşik sınırında (n=30) — **karar için değil, takip ölçümü için** aday.
4. Engulfing teyidini kaldırıp bölge kenarından limitle girmek (P2) bu teyidi alamayan dokunuşlarda
   başa baş (−0.04 R, PF 0.95, n=407) — teyidin bugünkü haliyle değer kattığına dair kanıt da yok.

## 1. Yöntem

- Her chart-görünür LuxAlgo OB dokunuşu (OB-entry-gap replay'i, 60 güne genişletildi; 3.044 dokunuş)
  dokunuş anında onu eleyen kurala göre sınıflandı.
- Her dokunuş için "o kural olmasaydı" işlem, **motorun kendi fonksiyonlarıyla** kuruldu:
  SL = `calc_sl` (zone + 0.5 ATR tampon, min 2 / max 5 ATR), TP = `luxalgo.tp_targets` (min R:R 1.8).
- İki giriş politikası:
  - **P1 (motor akışı):** dokunuştan sonra 48 bar içinde bölge içinde kapanan engulfing; giriş o kapanış.
  - **P2 (teyitsiz):** dokunuş barında bölgenin yakın kenarından limit dolum.
- Çıkış: aynı barda SL ve TP varsa önce SL (temkinli); TP1'de %50 + SL girişe; en çok 36 saat.
- Maliyet: taraf başına %0.05 taker + %0.02 slippage, 8 saatte %0.01 funding.
- IS / OOS: dokunuş zamanına göre ilk 2/3 / son 1/3 (OOS başlangıcı 2026-10-15).
- **Karar kuralı:** "umut verici" = n ≥ 30 **ve** IS ile OOS NET ortalamanın ikisi de > 0. Aksi "kanıt yok".

## 2. Sonuçlar (NET R/işlem)

| Kategori (eleyen kural) | Pol. | İşlem | NET ort. | PF | Kazanç % | IS | OOS | Sembol + | Karar |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **Baz: tüm kapıları geçti (motorun aldığı)** | P1 | 217 | **−0.30** | 0.65 | 31 | −0.48 | +0.03 | 3/10 | — |
| Baz | P2 | 232 | −0.75 | 0.27 | 19 | −0.85 | −0.56 | 0/10 | — |
| 12h trende ters | P1 | 472 | −0.31 | 0.64 | 31 | −0.34 | −0.25 | 1/10 | kanıt yok |
| 12h trende ters | P2 | 1222 | −0.29 | 0.66 | 31 | −0.26 | −0.35 | 0/10 | kanıt yok |
| Premium/discount | P1 | 170 | −0.32 | 0.64 | 32 | −0.25 | −0.44 | 1/10 | kanıt yok |
| Premium/discount | P2 | 383 | −0.31 | 0.65 | 31 | −0.32 | −0.28 | 1/10 | kanıt yok |
| Kırılım 168 bardan eski | P1 | 113 | −0.17 | 0.78 | 36 | −0.33 | +0.01 | 3/10 | kanıt yok |
| Kırılım 168 bardan eski | P2 | 429 | −0.22 | 0.72 | 33 | −0.32 | −0.08 | 4/10 | kanıt yok |
| Confluence < 1 | P1 | 29 | −0.24 | 0.71 | 34 | −0.18 | −0.33 | 4/10 | kanıt yok (n<30) |
| Confluence < 1 | P2 | 99 | −0.41 | 0.55 | 29 | −0.56 | −0.17 | 2/10 | kanıt yok |
| **OB motor penceresinde mitige** | P1 | 30 | **+0.24** | 1.42 | 50 | +0.23 | +0.25 | 5/10 | **umut verici (sınırda)** |
| OB motor penceresinde mitige | P2 | 93 | −0.53 | 0.44 | 27 | −0.27 | −1.00 | 2/10 | kanıt yok |
| Dokundu, engulfing gelmedi | P2 | 407 | −0.04 | 0.95 | 39 | −0.05 | −0.01 | 5/10 | kanıt yok |

Not: P1'de dokunuşların çoğu teyit almadığı için işlem sayısı dokunuştan azdır (ör. trend kategorisinde 1.301 dokunuştan 472 işlem).

## 3. Yorum

- **Kapılar işini yapıyor:** elenen her büyük kategori bazdan iyi değil, çoğu aynı ya da daha kötü.
  "Bot bölgede girmedi" gözlemi, bu 60 günde girmemenin doğru olduğu durumlara denk geliyor.
- **Maliyet / risk oranı ana sorun:** baz kategoride brüt sonuç sıfıra yakın; dar SL (min 2 ATR,
  medyan %0.72) yüzünden sabit maliyet R cinsinden büyüyor. Maker (limit) çıkışlar ya da daha geniş
  yapısal SL ile maliyetin R'deki payını düşürmek, kapı gevşetmekten daha anlamlı bir araştırma yönü —
  ama bu da ayrı bir NET-cost ölçümü ister.
- **Mitige OB retest'i** operatörün grafikte "BB" diye gördüğü bölgelere en yakın kategori. 30 işlem
  ile IS ve OOS'ta tutarlı pozitif; yine de tek pencere, tek parametre seti. Daha uzun veriyle (≥180 gün)
  tekrar ölçülmeden hiçbir şeye bağlanmamalı.
- **Uyarı (canlı mod):** LuxAlgo modu canlıya NET-cost ölçümü olmadan alındı (config notu). Bu ölçüm,
  baz akışın bu 60 günde NET negatif olduğunu gösteriyor. Bu bir canlı karar önerisi değil; operatörün
  bilmesi gereken bir risk bulgusu.

## 4. Sınırlar

- Karşı-olgu her dokunuşu bağımsız işlem sayar: sembol başına tek pozisyon, `max_open_positions`,
  breaker, pos_guard ve kapasite simüle edilmedi.
- Canlı motor 30 sn'lik fiyat örneklemesiyle çalışır; burada 15m bar OHLC kullanıldı. Aynı barda SL+TP
  durumunda SL varsayımı sonucu aşağı çeker; maker çıkış ve gerçek fill'ler sonucu yukarı çekebilir.
- 60 gün tek rejim penceresi olabilir; IS/OOS ayrımı bu pencerenin içindedir.
- Canlı journal ile birebir doğrulama yapılmadı (journal'daki LuxAlgo dönemi 3 gün, PnL alanları reconcile ile sıfır).

## 5. Takip önerileri (operatör kararı)

1. Baz akışın NET negatifliğini canlı journal + signal ledger ile doğrula; LuxAlgo modunun devamı
   operatör/risk-ops kararıdır (bu rapor yalnız bulgu sunar).
2. Mitige OB retest'ini ≥180 gün veriyle yeniden ölç; tutarsa default-OFF bayrak tasarımı tartışılabilir.
3. Maliyet/risk oranı: maker çıkış ve SL genişliği senaryolarını aynı harness ile NET-cost ölç.
