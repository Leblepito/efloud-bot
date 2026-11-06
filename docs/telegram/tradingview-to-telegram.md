# TradingView -> Telegram kanalı (u2algo Price Action)

## Ne yapar
"u2algo Price Action" göstergesi her onaylanmış sinyalde (bar kapanışında) tek bir `alert()` üretir. İndikatör ayarlarında **Telegram alerts -> Telegram chat id** doluysa mesaj doğrudan Telegram `sendMessage` JSON'u olur; TradingView webhook'u bunu Telegram API'ye postalar. Alan boşsa mesaj eski bot JSON'u kalır (bot tüketicileri etkilenmez).

## Ön koşullar
- TradingView ücretli plan (webhook bildirimi ücretsiz planda yok; Essential ve üzeri yeterli).
- @BotFather'dan açılmış bir Telegram botu; bot topluluk kanalına **admin** olarak eklenmiş olmalı.
- Kanal kimliği: `@kanaladi` veya sayısal `-100…`. Sayısal id için kanalda bir mesaj yazın, sonra tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` açın; `chat.id` değerini alın.

## Adımlar
1. Grafiğe göstergeyi ekleyin -> Ayarlar -> **Telegram alerts** -> `Telegram chat id` alanına kanal id'sini yazın (isteğe bağlı: `Message footer`).
2. Alerts -> **Create Alert** -> Condition: `u2algo Price Action` -> **Any alert() function call**.
3. Notifications -> **Webhook URL** işaretleyin -> `https://api.telegram.org/bot<TOKEN>/sendMessage`
4. Message alanına dokunmayın (gösterge mesajı kendisi üretir). Kaydedin.
5. Her sembol/zaman dilimi için ayrı alert gerekir (bir alert = bir sembol + bir TF).

## Örnek mesaj
```
🟢 LONG BTCUSDT.P · 15
Entry: 67250.5
SL: 66800
TP1: 68100
TP2: —
Setup: OB BREAKER+OTE
u2algo Price Action
```

## Güvenlik
- Bot token'ı yalnız TradingView alert URL'sinde durur; repoya veya Pine kaynağına ASLA yazılmaz.
- Yalnız o kanala yazabilen ayrı bir bot kullanın. Sızarsa @BotFather -> `/revoke` ile yenileyin ve alert URL'lerini güncelleyin.

## Sorun giderme
- **403**: bot kanalda admin değil.
- **400 chat not found**: chat id yanlış (`@` unutulmuş veya `-100…` hatalı).
- **400 can't parse entities**: mesaj `parse_mode: HTML` ile gider. `Message footer` ve setup metnindeki `<`, `>`, `&` otomatik kaçırılır; bu hatayı görürseniz alarmı indikatörün güncel sürümüyle yeniden oluşturun (eski alarm eski kodu çalıştırır).
- **Hiçbir şey gelmiyor**: planda webhook yok, alert süresi dolmuş veya Condition "Any alert() function call" değil.
- Alert mesajı `alert()` çağrısından gelir; alert penceresindeki Message alanına bir şey yazarsanız gösterge mesajının yerine geçmez ama kafa karıştırır — boş bırakın.

## İki akış farkı
- **Gösterge (bu doc)**: alert eklediğiniz TÜM semboller; risk kapıları yok.
- **Bot bildirimi**: botun gerçek dolumları ayrıca Telegram'a gider (`EFLOUD_CUSTOMER_TG_TRADES`, varsayılan kapalı; PR #298 → `docs/telegram/community-channel.md`); yalnız canlı 10 sembol ve risk kapılarından geçenler.
