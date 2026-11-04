# OB/BB giriş açığı — "chart'ta bölgeye geldi, bot girmedi" teşhisi

- **Kaynak:** motor/config `master@b475d8f` (VPS `b6c6bd1` ile `engine/` + `configs/` farkı yok, `git diff` 2026-11-04);
  canlı config `configs/config.phase2_1k.yaml` (mid: 15m / 4h / 12h, LuxAlgo modu açık).
- **Üretim:** 2026-11-04 ~19:45 UTC · claude-code · takip: T-20261104-07, -08, -09.
- **Yöntem (salt-okuma):** (1) TradingView Desktop MCP ile grafikteki LuxAlgo kutuları okundu; (2) VPS'te
  `docker logs` + state dosyaları okundu (yazma yok); (3) Binance USDT-M 15m/12h verisi motorun kendi
  fonksiyonlarına (LuxAlgo analizi, aday üretimi, emit kapıları, bekleme/teyit akışı, SL/TP hesabı) bar-bar
  verildi — 10 canlı sembol, 14 gün (2026-10-21 → 11-04). Ham veri ve script'ler git dışında (laptop).

## 0. Kısa sonuç

1. **Motor bölgeleri görüyor.** Grafikteki LuxAlgo OB'leri ile motorun hedef bölgeleri aynı mumdan geliyor;
   ETH'de kenar farkı ~%0.05–0.1 (grafik Bitstamp spot, bot Binance perp). Sorun algı değil, **politika**:
   motor chart'ta görünen OB'lerin çoğunu bilinçli kurallarla eliyor.
2. **Replay:** 14 günde chart'ta görünen OB'lere 664 dokunuş oldu. Motor bunların **%78'i için hiç aday
   üretmedi**; aday ürettiklerinin yarısından fazlasında teyit mumu gelmedi. Dokunuşların yalnız **~%9'u**
   SL/TP kapılarını geçen bir emre dönüşürdü (pozisyon/kapasite kontrolleri hariç).
3. **En büyük tek sebep: 12h trend filtresi (%45).** Motor yalnız 12h LuxAlgo swing trendi yönündeki
   kırılımların OB'sinden işlem arar; grafik iki yöndeki OB'leri de çizer.
4. **Canlı ek sorun:** 2026-11-04 14:35 UTC restart'ından beri **scalp ve long botlar idle** (autostart kapalı,
   yalnız mid elle başlatılmış) → T-20261104-07 (operatör).
5. **Öneri:** (a) salt-okunur erken uyarı → **evet** (T-20261104-08). (b) TradingView'den motora bölge girdisi →
   **şimdilik hayır**; önce hangi kapının edge'e mal olduğunu NET-cost ölç (T-20261104-09).

## 1. Canlı durum (2026-11-04 ~19:15 UTC)

- `efloud-bot` (mid) çalışıyor: 19 LuxAlgo adayı `AWAITING_PULLBACK`, son 5 saatte hiçbiri bölgesine dokunmadı
  (piyasa yukarı kaçtı). Breaker OPEN / `can_trade: true`, açık pozisyon yok.
- ETH örneği — grafik ile motor eşleşiyor:
  - Grafikteki internal bull OB ≈ 2308–2317 → motorun bekleyen adayı 2309.09–2319.13.
  - Grafikteki swing bull OB ≈ 2231–2244 → motorun bekleyen adayı 2232.45–2246.73.
  - Fiyat ~2425; geri çekilme olmadığı için giriş yok — bu bir hata değil.
- Son 5 saatte 9 yeni ETH/BTC LONG adayı `max_entry_dist_atr: 12` kapısında düştü (bölge 12.3–13.7 ATR uzakta).
  Aynı yöndeki daha yakın adaylar zaten beklediği için pratik kayıp yok.
- `efloud-bot-scalp` ve `efloud-bot-long`: restart'tan beri 0 tarama döngüsü. Bu iki profil için "bot girmiyor"
  gözleminin sebebi doğrudan budur.
- Journal: LuxAlgo döneminde (11-01 → 11-03) 7 giriş var, sonuncusu 11-03 06:45 UTC. Replay 11-03 07:00 ile
  11-04 14:35 arasında da girişler öngörüyor; container logları restart'ta sıfırlandığı için o aralıkta botun
  çalışıp çalışmadığı **doğrulanamadı**.

## 2. Grafik ile motor neden farklı "görür"

| Konu | TradingView LuxAlgo | Canlı motor | Referans |
| --- | --- | --- | --- |
| Veri | Grafikteki sembol (şu an BITSTAMP:ETHUSD spot) | Binance USDT-M perp | — |
| Geçmiş | Grafikte yüklü tüm barlar | Son 750 adet 15m bar (~7.8 gün) | `config.phase2_1k.yaml:229` |
| Yön | İki yöndeki OB'leri çizer | Yalnız 12h LuxAlgo swing trendi yönündeki kırılımlar | `safe_orchestrator.py:1224`, `luxalgo.py:528` |
| Yaş | Kutu mitige olana dek durur | Kırılım son 168 bar (42 saat) içinde olmalı; aday 48 bar sonra EXPIRED | `config:270`, `config:199`, `safe_orchestrator.py:1203`, `:2126` |
| Premium/discount | Çizimi etkilemez | LONG: OB tepesi EQ altında; SHORT: OB dibi EQ üstünde | `luxalgo.py:541`, `config:194` |
| Confluence | Yok | OB + en az 1 etiket (SWING_OB/OTE/EQ/FVG/SWEEP) | `luxalgo.py:550`, `config:197` |
| "Giriş" anı | Kutuya değmek giriş gibi görünür | Bölgede 15m engulfing ve kapanışı **bölgenin içinde** (tek mumluk dar bölge) | `confirmation.py:86`, `:94` |
| Emit kapıları | — | ≤12 ATR uzaklık, ≤6 ATR aşım, sembol başı ≤6 aday | `safe_orchestrator.py:2524`, `:2539`, `setup_state.py:137` |
| Emir öncesi | — | SL 2–5 ATR, TP1 ≥ 1.8R, pos_guard / max_open / breaker | `sl_calc.py:67`, `safe_orchestrator.py:2772`, `:2804` |
| Breaker Block | LuxAlgo SMC BB çizmez | LuxAlgo modunda BB hedefi yok (efloud triggers yolu kapalı) | `config:175-181` |

Not: Grafikteki "EFloud Signals v2" göstergesi okuma anında hiç kutu/etiket çizmiyordu; görülen bölgeler LuxAlgo OB'leri.

## 3. Replay — chart OB dokunuşu başına motor kararı

Tanım: grafikte görünür bir LuxAlgo OB'sine (oluştuğu bardan sonra, mitige olana dek) fiyatın **ilk** fitil
teması = 1 dokunuş. Motor kararı, dokunuş barındaki durumdur. 10 sembol × 14 gün, 664 dokunuş, medyan OB yaşı 16 bar.
Ekim kısmı karşı-olgusaldır (LuxAlgo modu canlıya 11-01'de girdi): "bugünkü config o gün açık olsaydı".

| Motor kararı | Adet | % | Reddeden kural |
| --- | ---: | ---: | --- |
| Aday yok — OB yönü 12h trendine ters | 296 | 44.6 | `luxalgo.py:528` |
| Aday yok — premium/discount (yanlış yarıda) | 94 | 14.2 | `luxalgo.py:541` |
| Aday yok — kırılım 168 bardan eski | 75 | 11.3 | `safe_orchestrator.py:1203` + `luxalgo.py:528` |
| Aday yok — confluence < 1 | 30 | 4.5 | `luxalgo.py:550` |
| Aday yok — OB motor penceresinde zaten mitige | 22 | 3.3 | `luxalgo.py:537` |
| Aday var — dokundu, zone-içi engulfing gelmedi (timeout) | 83 | 12.5 | `confirmation.py:86/94`, `safe_orchestrator.py:2126` |
| Aday var — SL/TP kapılarını geçti (emir adayı) | 58 | 8.7 | — (sonra pos_guard / kapasite) |
| Aday var — replay sonunda hâlâ bekliyor | 5 | 0.8 | — |
| Aday var — TP1 < 1.8R | 1 | 0.2 | `safe_orchestrator.py:2804` |

Her sembolde dağılım benzer (HTF yönü 22–34 dokunuş/sembol ile her yerde ilk sırada). `sl_too_far`,
emit-uzaklık ve kapasite kapıları dokunuş anında hiç bağlayıcı olmadı.

## 4. Örnekler (LuxAlgo canlı dönemi, Binance verisi)

| Sembol | Chart OB (yön, kapsam, bölge) | Oluşum → dokunuş (UTC) | Motor kararı | Reddeden kural |
| --- | --- | --- | --- | --- |
| ETH | BEAR internal 2305.45–2313.77 | 11-02 06:15 → 11-03 13:30 | Aday yok | 12h trend BULL, SHORT aranmıyor — `luxalgo.py:528` |
| ETH | BULL internal 2287.59–2294.87 | 11-02 03:15 → 04:45 | Aday yok | OB, LTF equilibrium'un üstünde — `luxalgo.py:541` |
| ETH | BULL swing 2215.22–2232.10 (bugün grafikte de duran kutu) | 11-01 01:00 → 11-04 03:00 | Aday yok | Kırılım 296 bar önce, recency 168 — `safe_orchestrator.py:1203` |
| ETH | BULL internal 2254.18–2259.06 | 11-01 23:00 → 11-02 17:15 | Aday yok | Ek confluence etiketi yok — `luxalgo.py:550` |
| BTC | BULL swing 77561.9–77785.5 | 11-01 23:30 → 11-02 11:30 | Aday doğdu, dokundu | 48 bar içinde zone-içi kapanışlı engulfing yok — `confirmation.py:94`, `safe_orchestrator.py:2126` |
| SOL | BULL internal 92.81–93.35 | 11-03 15:45 → 16:00 | Emir adayı (replay) | Journal'da karşılığı yok; botun o saatte çalıştığı doğrulanamadı (§1) |
| ETH | BULL internal ~2309–2319 (canlı) | 11-04 → bekliyor | Aday bekliyor | Fiyat bölgeye dönmedi — red yok |

## 5. "Bota önceden haber verme" — değerlendirme

### (a) Salt-okunur erken uyarı → ÖNERİLİR (T-20261104-08)
Mevcut `efloud-alerter` container'ı bot logunu zaten takip ediyor; emir yoluna dokunmadan kural eklenir:
1. Bekleyen adayın bölgesine fiyat N×ATR yaklaştı ("ETH LONG bölgesi 2309–2319, 0.8 ATR kaldı").
2. Aday geçişleri: dokundu / çıktı / tekrar girdi / teyit / süresi doldu (`[lux]` satırları, #265).
3. Red/kapı satırları sebebiyle: `[v2 reject] …`, `[v2 gate] …`.
- Bayrak default OFF, TDD, dedup + saatlik üst sınır. Gerekirse motora **yalnız log satırı** eklenir.
- Risk: bildirim gürültüsü (dedup ile), uyarının "manuel işlem sinyali" sanılması (mesaj metni bunu açıkça
  belirtir). Emir/size/SL/TP etkisi yok.
- Fayda: operatör "neden girmedi" sorusunu anında, kural adıyla görür; bu teşhisin el ile yaptığını otomatikleştirir.

### (b) TradingView alert/MCP → motor girdisi → ŞİMDİLİK ÖNERİLMEZ
1. **Teşhis bunu gerektirmiyor:** motor aynı OB'leri zaten hesaplıyor. Açık algıda değil, filtrelerde;
   dış girdi bu filtreleri ya atlar (desk kuralını deler) ya da aynı filtrelere takılır (bir şey kazandırmaz).
2. **Desk kuralı:** emri yalnız motor verir; dış kaynak emir/size/SL/TP üretmez.
3. **Veri tutarsızlığı:** grafik başka borsa/sembol (Bitstamp spot), farklı geçmiş uzunluğu; MCP kutu okuması
   yalnız görünür/son N kutuyu verir → deterministik ve tekrarlanabilir değil.
4. **Güvenlik:** mainnet bota webhook = public repo'da yeni dış saldırı yüzeyi.
5. **Kanıt yok:** hangi ek girişlerin pozitif NET edge taşıdığı bilinmiyor.

### Daha fazla giriş isteniyorsa doğru yol
Kapıyı "dışarıdan" değil, **ölçerek** gevşetmek. T-20261104-09: her red kategorisi için "kapı olmasaydı"
işlemin komisyon+slippage+funding dahil NET R sonucu (≥60 gün, IS/OOS, kategori başına n≥30). Bir kapının
edge'e mal olduğu gösterilirse: default-OFF config bayrağı + TDD + risk-ops review + operatör onayı.
Öncelik sırası (etki büyüklüğüne göre): 12h trend filtresi > zone-içi engulfing teyidi > premium/discount > recency.

### Ölçüm planı
| Metrik | Kaynak | Sıklık |
| --- | --- | --- |
| Huni: chart-OB dokunuşu → aday → teyit → emir | replay harness + `scripts/lux_monitor.py report` | haftalık |
| Kapı başına karşı-olgu NET R | T-20261104-09 | bir kez, sonra aylık |
| Uyarı → sonuç (bölge tuttu mu) | alerter kayıtları (T-08 sonrası) | haftalık, bilgi amaçlı |

## 6. Yan bulgular (bu PR'da düzeltilmedi)

- **Bayat teyitle tekrar onay (replay'de görüldü, canlıda doğrulanmadı):** onaylanan aday store'dan çıkınca aynı
  kırılım recency penceresindeyse yeniden emit ediliyor; `confirm_last_bar_only: false` iken teyit fonksiyonu
  eski engulfing mumunu tekrar bulup fiyat bölgedeyse hemen yeniden onaylıyor. Pozisyon açıkken pos_guard
  frenler; pozisyon kapandıktan sonra aynı bölgeye bayat teyitle ikinci giriş mümkün. Mevcut C2 bayrağı
  (`config:112`) bunun içindir — NET-cost kararı T-09 kapsamında değerlendirilebilir.
- **Aynı OB için iki slot:** internal ve swing CHoCH aynı OB'yi işaret edince iki aday oluşuyor (canlıda ETH,
  SOL, BCH). Sembol başına 6 slottan ikisini tek bölge tutuyor.
- **Log saklama:** container logları restart'ta sıfırlanıyor; geçmiş huni analizi yapılamıyor (§1 son madde).

## 7. Sınırlar

- Replay canlı 30 sn'lik fiyat örneklemesini bar içi O→L→H→C (ya da O→H→L→C) yolu ile yaklaşıklar.
- "Emir adayı" = SL/TP kapılarını geçti; pos_guard, max_open, breaker, sizing ve borsa tarafı simüle edilmedi.
- Chart görünürlüğü motorun 2100 barlık analiziyle yaklaşıklandı; TradingView'in "son 5 OB" gösterim sınırı uygulanmadı.
- 14 gün kısa; sonuçlar sebep dağılımını gösterir, edge hakkında hiçbir şey söylemez.
