# Veri çekme sıklığı: 15m REST mi, websocket mi? (T-20261105-01)

- **Kaynak:** master `57b0a19` (soru `1e9ad91` üzerinden soruldu; ilgili satırlar değişmedi), canlı mid config
  `configs/config.phase2_1k.yaml`, T-09 ham çıktısı `c:/tmp/obgap_data60/cf_trades.json` (laptop, git dışı).
- **Üretim:** 2026-11-05 · abacus · ebeveyn: T-20261104-09.
- **Bağlam:** Operatör o sırada fitil/temas girişini de istedi. Kod iki PR'da, ikisi de varsayılan KAPALI:
  #278 (WS kline Faz 1, gölge) ve #280 (Faz 2: olay tetiklemeli tarama + `smc_v2.touch_entry`). Bu rapor
  o kodun değerlendirmesi değil, verinin ne söylediği.

## 0. Kısa sonuç

1. "Her sembol için 15 dakikada bir veri çekiyoruz" **doğru**, ve bu bir **API sorunu değil, karar
   gecikmesi sorunu**. REST yükü önemsiz. Asıl kayıp: bölgeye fitil atıp kapanmadan dönen fiyatı motor
   hiç görmüyor, gördüklerini de bir mum geç görüyor.
2. Websocket tek başına **NET edge üretmez**. Sadece veriyi hızlandırır. Edge, o veriyle **ne karar
   verildiğine** bağlı. T-09 verisine göre teyitsiz temas girişi bugün NET negatif: taker ile
   −0.295 R/işlem. Bu, motorun bugünkü −0.298 R'siyle aynı seviye, ama yaklaşık 3 kat işlemle.
3. **Öneri: (b) + ölçüm.** Websocket'i hemen gecikme ve uyarı için kullan (#278 gölge → event_scan).
   Temas girişini (`touch_entry`) yalnız `shadow` modunda çalıştırıp ölç. `live` kararını eşik geçilince ver.

## 1. Bağımsız doğrulama (iddia → kanıt)

| İddia | Sonuç | Kanıt |
| --- | --- | --- |
| Döngü 30 sn | Doğru | `configs/config.phase2_1k.yaml:288` `check_interval_sec: 30` |
| Tarama yalnız yeni entry mumu kapanınca | Doğru | `backend/bot_runner.py:539-553` (1e9ad91): `current_candle_ts = ((now_ms - 2000) // tf) * tf`, aynı mumsa `return` |
| Sembol başına 4 REST çağrısı | Doğru | `bot_runner.py:561-566`: htf, mtf, entry (`kline_limit: 750`, config:229), `1d` 100. Canlı modda ayrıca `get_balance()` |
| Oluşan mum atılıyor (C1) | Doğru | `exchange/__init__.py:101-117`: `raw[-1][0] + tf_ms > now_ms` ise son satır düşer |
| `current_price` = son kapanmış 15m close | Doğru | `engine/safe_orchestrator.py` `run_cycle`: `float(df_entry["close"].iloc[-1])` |
| Bölge kararı fitil değil kapanış | Doğru | `engine/smc_v2/zones.py:81-83` `zone.low <= price <= zone.high`; çağrı `safe_orchestrator.py:2133` (1e9ad91; master'da #275 sonrası 2144) |
| Teyit = bölge içi engulfing kapanışı | Doğru | `engine/smc_v2/confirmation.py:4-8, 53` |
| SL/TP borsada emir olarak duruyor | Doğru | `exchange/__init__.py` `open_position`: STOP_MARKET reduceOnly; reconcile ayrı |
| Giriş emri | **Ek bulgu** | `open_position` → `create_order(..., "market", ...)`: giriş **market (taker)**. AGENTS.md'deki "limit emir" ifadesi kodla uyuşmuyor |

## 2. Websocket ne kazandırır, neyi riske atar

**Kazançlar**
- **Tarama gecikmesi:** bugün kapanıştan sonra tarama başlayana kadar 2 sn tampon + 0–30 sn döngü
  bekleniyor (ortalama ~15 sn). Kline WS kapanış mesajı (`x=true`) ile bu ~0.5 sn'ye iner (#280 `event_scan`).
  15m'lik bir sistem için küçük ama bedava bir kazanç. Karar mantığı değişmiyor.
- **Kaçan dokunuşlar:** claude-code'un ölçümüne göre fitil dokunuşlarının yaklaşık %15'i 48 mum içinde
  hiç bölge içi kapanış almıyor. Bunları yalnız intrabar veri görebilir. T-09'da bu küme
  (`touched_no_engulf`, P2) NET −0.037 R (taker), yani kaçırılması bugün para kaybettirmiyor.
- **Erken uyarı (#275):** `[lux] near/touch` satırları bugün kapanışta üretiliyor. WS fiyatıyla
  operatör dokunuşu anında görebilir. Gözlem değeri yüksek, risk yok.
- **API weight:** kline WS'in REST weight maliyeti yok. Bugünkü yük zaten önemsiz: 10 sembol × (3×750'lik
  kline, her biri weight 5 + 1d/100, weight 2 + bakiye, weight 5) ≈ 220 weight / 15 dk (tahmin, Binance
  futures klines weight tablosuna göre). Binance sınırı 2.400 weight/dk. Yani
  websocket'in gerekçesi weight değil, gecikme.

**Riskler**
- **Repaint / kapanmamış barla karar:** oluşan barın high/low'u kesin, ama "bölgeye değdi" kararı geri
  alınamaz. Fitil sonradan bölgeyi delip geçebilir. T-09 P2 SL-first ile bunu zaten fiyatladı.
- **Yeniden bağlanma:** Binance 24 saatte bağlantıyı keser. #278 23 saatte bir yeniler, kopunca 1→60 sn
  backoff uygular. Kopukluk süresince intrabar karar yok, kapanış taraması REST ile devam ediyor.
  #280 ayrıca `touch_max_age_ms` (5 sn) üstündeki WS barını yok sayıyor.
- **İki veri yolu tutarsızlığı:** WS kapanış barı ile REST barı farklı olabilir. #278 her taramada
  `[ws shadow] parity=OK|MISMATCH` sayıyor. Faz 2'yi canlıya almadan önce birkaç gün MISMATCH = 0 görülmeli.
- **Eşzamanlılık:** kapanış taraması ile temas yolu aynı adayı aynı anda ilerletebilir. #280'de
  `RLock` var, 8 thread → 1 emir testi geçiyor.

## 3. Öneri ve ölçüm planı

| Seçenek | Ne | Ölçüm (metrik · araç) | Karar eşiği |
| --- | --- | --- | --- |
| (a) Değiştirme | REST + kapanış | — | Gerekçe zayıf: gecikme ve görünürlük bedavaya iyileşiyor |
| **(b) WS: uyarı + izleme + olay tetiklemeli tarama** | #278 `data_feed.ws.enabled: true`, ardından `event_scan: true` | `[ws shadow]` parite sayaçları, `ws_seen_before_rest_ms`, reconnect sayısı · `docker logs` | 3 gün: MISMATCH = 0, kopukluk < %1. Sonra `event_scan` açılır |
| (c) WS ile giriş mantığı (temas girişi) | #280 `smc_v2.touch_entry: shadow` → `live` | `[touch shadow] would-enter` satırları, T-09 harness'iyle aynı SL/TP/maliyet (taker, canlı giriş market) ile NET R; IS/OOS zaman bölmesi; sembol başına tek pozisyon (çakışmaları ayıkla) | n ≥ 30 **ve** IS ile OOS NET > 0 **ve** bugünkü akıştan (P1) iyi. Aksi halde `shadow`'da kalır |

**Önerilen sıra:** (b) hemen (config PR + deploy ticket + operatör onayı) → (c) shadow'da veri topla →
eşik geçilirse live. Ayrı bir araştırma yönü: temas girişi maker (post-only limit) ile yapılırsa T-09
verisinde `touched_no_engulf` P2 +0.049 R'ye çıkıyor (IS +0.035 / OOS +0.080, n=407). Ama bugünkü
emir yolu market. Maker giriş ayrı bir tasarım ve ayrı bir ölçüm ister (#277 review yorumu).

## 4. Sınırlar

- T-09 verisi 60 gün, 10 sembol, tek rejim penceresi. Dokunuşların %31'i aynı sembolde zamanca çakışıyor,
  bu yüzden etkin n tablodakinden küçük.
- Bu rapordaki NET rakamlar T-09 ham çıktısından yeniden hesaplandı. Ayrı bir canlı WS prototipi
  koşulmadı. Gerçek WS gecikmesi #278 gölge logu ile ölçülecek.
