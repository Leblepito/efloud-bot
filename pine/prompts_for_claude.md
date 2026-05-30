# Claude Code için Pine Script v6 Çeviri Prompt'ları

Bu dosya, `efloud-bot` çekirdek SMC mantığını TradingView Pine Script v6'ya çevirmek için kullanacağınız prompt'ları içerir. Sırasıyla kopyalayıp Claude Code terminaline yapıştırabilirsiniz.

---

## 1) AŞAMA A — Python Repo Analizi (kod yazma YOK)

```markdown
Bu, `efloud-bot` Python repo'su. Görevin bu botun trade mantığını TradingView Pine Script v6'ya çevirmek. Henüz HİÇBİR Pine kodu yazma.

ADIM 1 — Python kaynağını anla:
- Çekirdek trade mantığı dosyalarını (`engine/signals.py`, `engine/smc.py`, `engine/confluence.py`, `config.yaml`) detaylı incele.
- Multi-Timeframe yapısını analiz et: HTF (4h) trend yönü, MTF (1h) yapı kırılımları, Entry (15m) sinyal tetikleyicileri ve Daily (1d) makro trend filtresini anla.
- Confluence puanlama mantığını çıkar (`engine/confluence.py`):
  - HTF bias hizalanması (25 Puan)
  - MTF CHoCH onayı (20 Puan)
  - Price in HTF FVG (15 Puan)
  - Price at Order Block (10 Puan) + OB near swing (+5 Puan) + OB at EQ (+3 Puan)
  - Price in OTE (10 Puan)
  - SFP likidite süpürmesi (10 Puan)
  - Correct premium/discount zone (5 Puan)
  - Range deviation (5 Puan)
  - Daily aligned/diverging bonus-penaltıları (±5 Puan)
  - Major level veya Stacked Zone (Price Action) bonusları (+5/+8 Puan)
- Stop Loss (SL) ve Take Profit (TP1/TP2) kurallarını tam olarak belgele:
  - Son 20 mumun en düşük/yüksek seviyesi + ATR(14) bazlı dinamik volatilite buffer'ı (0.5x ila 0.75x ATR).
  - range deviation play'de TP1/TP2 hedefleri (EQ ve Range Extreme).
  - Price discovery durumundaki Fibonacci uzantı hedefleri (1.272 ve 2.618).
- `pine/PINE_SPEC.md` adında bir spec dosyası üret. İçinde bu parametreleri, formülleri ve kuralları Türkçe/İngilizce olarak net bir dille listele.
- Gemini AI doğrulama katmanının (Python'daki market structure check) Pine'a çevrilemeyeceğini, bunun yerine Pine-native olarak confluence ve kural tabanlı filtrelerin kullanılacağını belirt.

PINE_SPEC.md'yi bana onaylatmadan koda geçme.
```

---

## 2) AŞAMA B — Indikatör Üretimi (MCP canlı bağlantı gerekir)

```markdown
ADIM 2 — Onaylanan PINE_SPEC.md'ye göre INDIKATÖR versiyonunu üret.

Önce `tv_health_check` çalıştır; cdp_connected:true ve aktif sembolü doğrula.

Gereksinimler:
1. 'EFloud Signals' adında bir Pine Script v6 indikatörü yaz.
2. Sadece v6 syntax: indicator() (study() değil), ta.ema()/ta.rsi()/ta.atr(), doğru var/series tiplemesi.
3. Multi-timeframe verisini almak için `request.security()` fonksiyonunu dürüst şekilde (gaps=barmerge.gaps_off, lookahead=barmerge.lookahead_off) repaint-safe olarak kullan. 1d, 4h, 1h ve 15m yapılarını hesapla.
4. Python `engine/smc.py` içindeki tüm algoritmaları (Swing, CHoCH/BOS, FVG mitigation, Order Block tespiti ve mitigation/breaker durumu, SFP sweep, OTE, Range EQ/Deviation) Pine Script'e uyarla.
5. Confluence skorunu her 15m barda hesapla. `min_confluence` (varsayılan 55) aşıldığında ve HTF bias ile uyumlu 15m BOS/CHoCH tetiklendiğinde grafikte plotshape ile Giriş seviyesini, SL invalidation seviyesini ve TP1/TP2 hedeflerini çiz.
6. Giriş, SL, TP1, TP2 seviyelerini etiketlerle (labels) ve çizgilerle (lines) görselleştir.
7. Her giriş ve çıkış sinyali için alertcondition() ekle.
8. TÜM sayısal parametreleri (lookbacks, threshold, buffers, R:R limitleri) `input.*` ayarı olarak dışarı aç.
9. Dosyayı repo'ya `pine/efloud_signals.pine` olarak kaydet.

Sonra MCP araçlarıyla:
- pine_set_source ile enjekte et
- pine_smart_compile ile derle
- pine_get_errors ile hataları oku, düzelt, SIFIR hata olana kadar yeniden derle
- pine_save ile TradingView cloud'uma kaydet

Çalıştığını grafikte doğrula ve bana rapor ver.
```

---

## 3) AŞAMA C — Strateji + Backtest

```markdown
ADIM 3 — Aynı mantığın STRATEJİ (backtest) versiyonunu üret.

1. 'EFloud Strategy' adında v6 strategy() yaz.
2. Gerçekçi varsayılanlar: initial_capital=10000, commission_value=0.04 (Binance futures taker fee), slippage=1, pyramiding=2, margin_mode=crossed (margin_mode=crossed ayarı olmasa da default crossed risk yönetimi kurallarını uygula).
3. `pine/efloud_strategy.pine` dosyasını oluştur.
4. PINE_SPEC.md'deki giriş/çıkış/TP/SL kurallarını `strategy.entry` ve `strategy.exit` ile uygula:
  - Giriş: 15m BOS/CHoCH + Confluence >= 55.
  - Stop Loss: Hesaplanan invalidation seviyesine sert stop.
  - Take Profit: TP1'de pozisyonun %50'sini kapat, TP2'de kalan %50'sini kapat.
5. Pozisyon büyüklüğünü (position size) `config.yaml` risk ayarlarına göre dinamik hesapla (`risk_per_trade_pct: 2.0` veya `reverse_from_risk` modunu Pine'da simüle et).
6. Tüm ayarlanabilir parametreleri input.* olarak aç — indikatör versiyonuyla AYNI isimler.
7. Enjekte et, sıfır hataya kadar derle, çalıştır.
8. Strategy Tester sonuçlarını raporla: Net Kar (Net Profit), Max Drawdown, Kazanma Oranı (Win Rate), Kar Faktörü (Profit Factor).
9. İleride mantık değişirse HEM indikatör HEM strateji dosyasını güncelle.

Özellik özellik ilerle: önce temel giriş/çıkış, derlenip backtest çalıştığını doğrula, SONRA risk yönetimi, kısmi kapanış (%50 TP1 / %50 TP2) yardımıyla ve alarmları katmanla.
```
