# u2algo Price Action — TradingView Yayın Kiti

Lisans gereği (LuxAlgo, CC BY-NC-SA 4.0) yayın **Open-source**, ticari olmayan olmalıdır; ücretli, davetli (invite-only) veya korumalı sürüm YAYIMLANMAZ.

## (a) Operatör adımları (TradingView Desktop)

1. Pine Editor'ü açın, yeni bir indicator oluşturun ve içeriği **`pine/efloud_lab.pine`** dosyasının tamamıyla değiştirin (üretilmiş dosya; elle düzenlemeyin, gerekirse `python scripts/build_pine_lab.py` ile yeniden üretin). Başlık `u2algo Price Action` olmalıdır.
2. **Save** ile kaydedin; derleme hatası olmadığını doğrulayın.
3. Grafik hazırlığı (yayın görseli için): sembol **BTCUSDT.P**, zaman dilimi **15m**, temiz grafik, yalnızca bu gösterge açık (başka gösterge/çizim yok); bölgelerin ve bir sinyalin göründüğü bir an seçin. Referans görseller: `docs/assets/u2algo-price-action/`.
4. Editörde **Publish script** tıklayın.
5. Ayarlar:
   - Title: `u2algo Price Action`
   - Visibility: **Public**
   - Type: **Open-source**
   - Kategori/etiketler (öneri): Smart Money Concepts, Order Blocks, Fair Value Gap, Liquidity, Fibonacci, Price Action, Market Structure
6. Description alanına aşağıdaki (b) metnini yapıştırın; grafik anlık görüntüsünü kontrol edin; yayımlayın.
7. Yayın sonrası bölüm (d) adımlarını uygulayın.

## (b) İngilizce açıklama (yapıştırılacak)

```
[b]u2algo Price Action[/b]

[b]Concept[/b]
u2algo Price Action maps Smart Money Concepts (SMC) price-action zones onto your chart: order blocks, breaker and mitigation blocks, fair value gaps, liquidity pools, an OTE retracement band and structure-based LONG/SHORT signals with Entry, Stop and Target levels. It is built so that a trader can see, in one place, where structure, imbalance and liquidity sit.

[b]How it works[/b]
[list]
[*][b]Order Blocks (OB / iOB):[/b] active swing-scale and internal-scale order blocks.
[*][b]Breaker (BB) / Mitigation Block (MB):[/b] when an order block is closed through, it flips direction. If the prior swing was swept first it is a Breaker; if price turned with a failure swing without sweeping it, it is a Mitigation Block.
[*][b]Fair Value Gaps:[/b] active, unmitigated imbalances.
[*][b]Liquidity:[/b] BSL / SSL and equal highs / lows (EQH / EQL). A star marks a level formed by a move with at least three consecutive bars of rising volume and above-average volume. Swept levels can be shown faded.
[*][b]OTE:[/b] a fixed swing range with the 0.618-0.786 band, the 0.705 level and the equilibrium; direction follows the order of the range extremes.
[*][b]Signals:[/b] a CHoCH or BOS creates a candidate order-block zone; once price pulls back into the zone and an engulfing candle confirms on bar close, a LONG/SHORT label with Entry, SL and TP lines is drawn. A higher-timeframe (12h) bias filter, a Power-of-3 manipulation gate, minimum R:R and stop-distance limits apply.
[*][b]Dashboard:[/b] bias, pending candidates, Po3 state, range equilibrium, recent rejections, zone counts and OTE state.
[/list]

[b]How to use[/b]
Add the indicator to a liquid market; 15m is recommended. Use zones as areas of interest, read the dashboard for context, and combine with your own analysis and risk management. Turn individual layers off in Settings if the chart feels busy.

[b]Settings[/b]
[list]
[*]Visual: toggles for order blocks, pending zones, signal lines and dashboard.
[*]SMC zones: BB/MB, FVG, liquidity, OTE, history, candle-body boxes, volume confirmation, number of zones per side, colours, transparency.
[*]Baseline: structure lengths, trigger kinds, recency, zone distance, SL/TP and Po3 parameters.
[*]Experimental toggles are off by default.
[/list]

[b]Alerts[/b]
Create an alert with Condition set to this indicator and "Any alert() function call". A signal fires once per confirmed bar close. By default the message is a JSON payload; if a Telegram chat id is entered in Settings, the message is formatted for the Telegram sendMessage API instead.

[b]Limitations[/b]
Zones are display-only and are not trade recommendations. Signals follow a fixed rule set and can be wrong; drawings are final only on bar close. Historical behaviour is not a guarantee of future results.

[b]Credits[/b]
The market-structure engine is adapted from "Smart Money Concepts (SMC) [LuxAlgo]", licensed CC BY-NC-SA 4.0. This script is published open-source under the same licence, for non-commercial use only.

[b]Disclaimer[/b]
For educational and informational purposes only. This is not financial advice. Trading, especially leveraged derivatives, involves substantial risk of loss.
```

## (c) TradingView House Rules uyum kontrol listesi

- [ ] Açıklama ve grafikte harici bağlantı, Telegram/sosyal medya hesabı veya kanal adı yok (Telegram yalnızca ayar adı olarak anılır).
- [ ] Performans veya kâr vaadi yok; "kazandırır", "garantili" gibi ifadeler yok.
- [ ] Özgün katkı açıklanmış: iki ölçekli BB/MB ayrımı, sabit aralıklı OTE, hacim teyitli likidite, bota ayna sinyal motoru, Telegram'a hazır alert mesajları (LuxAlgo'dan farkı).
- [ ] Açıklama İngilizce.
- [ ] Yayın görseli yalnızca bu scripti gösteriyor (başka gösterge/çizim yok), sembol/TF okunaklı.
- [ ] Type = Open-source, Visibility = Public; kaynak kodda lisans satırı ve LuxAlgo atfı duruyor.
- [ ] Ücretli/davetli/korumalı sürüm yok (non-commercial).
- [ ] Başlık: `u2algo Price Action`.

## (d) Yayın sonrası

1. Yayınlanan scriptin TradingView URL'sini `README.md` içindeki `<!-- TV_URL -->` işaretinin yerine ekleyin.
2. Aynı URL'yi `docs/indicator/u2algo-price-action.md` içindeki `<!-- TV_URL -->` satırının altına yazın.
