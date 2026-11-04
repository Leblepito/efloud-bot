---
id: T-20261104-11
title: Binance USDT-M WebSocket kline feed (Faz 1 — gölge/parite, varsayılan KAPALI)
from: operator
to: abacus
status: claimed
claimed_by: abacus
reviewer: claude-code
parent: T-20261104-07
created: 2026-11-04
touches_live: true   # kod yolu bot_runner'a dokunur; DEPLOY ayrı ticket + operatör onayı
---

## Amaç
Mid bot yalnız 15m mum kapanışında REST ile tarıyor (`backend/bot_runner.py::_scan_universe`,
`check_interval_sec: 30` + 2 sn tampon + sembol başına 4 REST çağrısı). Operatör isteği: veri
WebSocket ile anlık gelsin. Faz 1 yalnız veri katmanı: `kline` WS akışı + önbellek + REST ile
parite ölçümü. **Emir/karar mantığı değişmez**; C1 (yalnız kapanmış bar) korunur.

## Girdi
- `backend/bot_runner.py` (`_scan_universe`), `exchange/__init__.py` (`fetch_ohlcv`, C1 forming-bar drop)
- `requirements.txt`: `websockets>=13.0` zaten var.

## Beklenen çıktı
- [ ] `exchange/ws_klines.py`: `KlineStream` (combined stream, reconnect/backoff, 23 sa yenileme, bayatlık ölçümü, `last_price`, kapanan bar kuyruğu).
- [ ] `bot_runner`: `data_feed.ws.enabled` (varsayılan false) ile başlat/durdur; YALNIZ gölge: WS kapanış zamanı vs REST tarama gecikmesi + OHLC parite logu. Karar/emir yolu REST kalır.
- [ ] Testler (ağ yok, sahte mesajlarla) + `tests/collab` yeşil.
- [ ] Faz 2 önerisi: kapanışta olay-tetikli tarama (REST fallback) — ayrı task, operatör kararı.

## Kısıtlar
- `configs/*.yaml` DEĞİŞMEZ (özellikle `risk:`/`safety:`); açma ayrı PR.
- Intrabar (oluşan mum) üzerinde giriş kararı YOK (C1 repaint koruması; operatör kararı gerekir).
- scalp/long botlar başlatılmaz (operatör 2026-11-04).

## Log
- 2026-11-04 abacus: claim (operatör isteği).

## Review
