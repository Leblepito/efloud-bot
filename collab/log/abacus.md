# abacus — iş günlüğü (append-only)

> Yalnız abacus yazar. Yeni giriş en alta eklenir, eskiler düzenlenmez. Format: `collab/README.md` §4.


## 2026-11-04 18:46 UTC — Incubator skill bağımsız review
- task: T-20261104-02 | branch/PR: collab/abacus/T-20261104-02-skill-review (#271) | commit: fd6791e
- ne yapıldı: Beş `REVIEW.md` dosyasına bağımsız kanıtlar ve Claude review'u ile fark/uyum notları eklendi; SKILL.md, kod ve config değiştirilmedi.
- VPS: N/A
- not: Zamanlayıcı aracı bu ortamda yok; otomasyon manuel tetiklemeli. `tests/collab` + desk plugin doğrulaması 71 testle geçti; PR hazır/review bekliyor.
- istek: claude-code — review/CI.

## 2026-11-05 — T-20261105-01 veri çekme sıklığı raporu + T-20261105-02 review
- task: T-20261105-01, T-20261105-02 | branch/PR: collab/abacus/T-20261105-01-data-fetch-cadence, #281 | commit: PR'da
- ne yapıldı: 15m REST/websocket raporu (iddialar doğrulandı; giriş market/taker ek bulgusu; öneri b + touch_entry shadow ölçümü). #275 ve #277'ye VERDICT APPROVE yorumları; #277 için maliyet duyarlılığı T-09 ham verisinden yeniden hesaplandı.
- VPS: N/A
- not: motor/config kodu değişmedi; yalnız collab dosyaları.
- istek: claude-code → rapor + #277 maker-giriş/çakışma notuna cevap
## 2026-11-04 — T-20261104-11 WS kline feed (Faz 1, gölge)
- task: T-20261104-11 | branch/PR: collab/abacus/T-20261104-11-ws-klines (#278) | commit: PR'da
- ne yapıldı: `exchange/ws_klines.py` (Binance fstream kline, reconnect, 23 sa yenileme) + `bot_runner` gölge parite/gecikme logu, `data_feed.ws.enabled` varsayılan KAPALI; config/emir yolu değişmedi. 8 yeni test (ağ yok).
- VPS: NOT-DEPLOYED: DEMO
- not: yerel Python 3.14'te `backend/tests` pytest capture hatası var (master'daki `test_candle_close_sync.py` de aynı); doğrulama `-s` ile 8/8 + CI (py3.11).
- istek: claude-code → review + deploy ticket; operator → Faz 2 kararı (olay-tetikli tarama / intrabar)
