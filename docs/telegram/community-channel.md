# Topluluk Telegram Kanalı — İşlem Başı Paylaşımlar

Operatör dokümanı. Varsayılan: **KAPALI**.

## İki kanal

| Kanal | Env | Kod | İçerik |
|---|---|---|---|
| Ops (operatör) | `EFLOUD_TELEGRAM_*` | `backend/notifications/` | Bakiye, USD PnL, pozisyon büyüklüğü dahil tam detay. **Değişmedi.** |
| Topluluk | `EFLOUD_CUSTOMER_TG_*` | `engine/notifications/telegram_notifier.py` (`CustomerChannelNotifier`) | Müşteri-güvenli: sembol, yön, Entry/SL/TP, sonuç. |

İki kanalın token ve chat id'leri ayrıdır; birbirine karışmaz.

## Bot ne paylaşır

`backend/bot_runner.py::_on_position_change` ops bildirimiyle aynı olaylarda topluluk notifier'ını da çağırır:

- **Açılış** (`position_opened`): sembol, yön, Entry, SL, TP1, (varsa) TP2, setup adı.
- **TP1** (`tp1_hit`): Entry → TP1 fiyatı.
- **Kapanış** (`position_closed`): Entry → Exit, kapanış nedeni (yalnız TP1/TP2/SL/BE/kapandı); R çarpanı yalnızca çağıran verirse (bot şu an vermez).
- `position_rolled_back` (SL doğrulanamadığı için zorla kapatılan giriş) **topluluğa gitmez**, yalnız ops kanalına gider.

Hiçbir mesajda bakiye, USD PnL, pozisyon büyüklüğü veya hesap verisi yoktur. Her mesajda `u2algo Price Action` ve
"Eğitim amaçlıdır, yatırım tavsiyesi değildir. / Not financial advice." dipnotu bulunur.

Güvenlik: notifier hiçbir zaman exception fırlatmaz (hata `warning` olarak loglanır); bot_runner çağrısı ayrıca ayrı bir
`try/except` içindedir. Telegram kesintisi işlem akışını etkilemez. Postlar arka plandaki tek bir worker thread'den gönderilir
(100 mesajlık kuyruk; dolarsa yeni post düşürülür ve `warning` loglanır). HTTP timeout varsayılan 5 sn (`EFLOUD_CUSTOMER_TG_TIMEOUT_SECS`).

## Nasıl açılır

1. @BotFather ile topluluk botunu oluştur (veya mevcut topluluk botunu seç). Ops botunu KULLANMA.
2. Botu topluluk kanalına **yönetici** olarak ekle (mesaj gönderme yetkisi).
3. VPS'te docker compose'un okuduğu env dosyasına (örn. `.env.production`) üç değişkeni ekle:
   ```
   EFLOUD_CUSTOMER_TG_TOKEN=<BotFather token>
   EFLOUD_CUSTOMER_TG_CHANNEL_ID=<-100...>
   EFLOUD_CUSTOMER_TG_TRADES=1
   ```
   Opsiyonel: `EFLOUD_CUSTOMER_TG_THREAD_ID`, `EFLOUD_CUSTOMER_TG_PARSE_MODE` (yalnız günlük özeti etkiler;
   işlem mesajları her zaman Markdown gönderilir). Yorumlu satırlar `deploy/.env.production.example` şablonunda da var.
4. Bot konteynerini **pozisyonsuz (flat) bir pencerede** yeniden oluştur (prod compose servisi `efloud-bot`):
   `docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps efloud-bot`.
   `EFLOUD_AUTOSTART=0` ise bot restart sonrası idle açılır; **manuel olarak start edilmelidir**.
5. Doğrulama: açılış logunda `Customer Telegram per-trade posts: ENABLED` (aynı satırlarda `digest disabled (flag off)`
   görünmesi normaldir — günlük özet ayrı bir bayrakla yönetilir); bir sonraki gerçek açılışta kanalda mesaj.

Üç koşuldan biri eksikse (token, kanal id, `TRADES` bayrağı) notifier sessizce no-op'tur ve hiç HTTP isteği yapmaz.
Kapatmak için `EFLOUD_CUSTOMER_TG_TRADES=0` + konteyner yeniden oluşturma.

> **Uyum notu:** Gerçek zamanlı entry/SL/TP paylaşımı P-003 §2b "sinyal servisi" sınırındadır ve CMP-3 compliance gate bu postları kapsamaz. Kanal herkese açıksa operatör/hukuki onay olmadan `EFLOUD_CUSTOMER_TG_TRADES=1` yapılmaz. Kapanış nedeni yalnız TP1/TP2/SL/BE/kapandı olarak paylaşılır; postlar arka plan kuyruğundan gönderilir (işlem akışını bloklamaz).

## TradingView alert feed ile ilişkisi

Gösterge (indicator) alert'leri TradingView'den kanala ayrı bir akışla gider: bkz. `docs/telegram/tradingview-to-telegram.md`
(PR #299, `feat/u2algo-price-action`). Bot, merge sonrası aynı SMC v2 mantığıyla işlem açar; bu yüzden aynı kanalda gösterge alert'i
ile botun gerçek işlem paylaşımı birbirini doğrular. Mesaj biçimleri farklıdır; botunki `u2algo Price Action` satırıyla biter.

## Sosyal pipeline (Instagram / X) ile ileride kullanım

Kanaldaki paylaşımlar sabit, yapılandırılmış satırlardır (`Entry:`, `SL:`, `TP1:`, `Exit:`). `scripts/daily_social_run.py`
ve `scripts/chart_render.py` bu kanaldan (veya aynı verinin bot loglarından) işlem seviyelerini çekip chart/caption üretebilir.
Yayın öncesi `scripts/lane_g_publish.py` 3-gate güvenlik kapısı ve compliance kontrolü geçerlidir; bu belge bu entegrasyonu
kurmaz, yalnızca veri biçimini sabitler.
