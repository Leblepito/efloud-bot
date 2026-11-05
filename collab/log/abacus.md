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

## 2026-11-04 20:25 UTC — VPS boşta teşhisi (salt okuma)
- task: (operatör isteği) | branch/PR: collab/abacus/vps-idle-diagnosis | commit: PR'da
- ne yapıldı: VPS log/journal/env salt okundu; mid tarıyor ama bölgeye geri çekilme yok + max_entry_dist_atr kapısı; scalp/long AUTOSTART=0 ile boşta. Rapor: outputs/abacus/2026-11-04-vps-idle-diagnosis.md
- VPS: N/A
- istek: operator → T-20261104-07
## 2026-11-04 18:51 UTC — Telegram rulebook (full export)
- task: T-20261104-01 | branch/PR: collab/abacus/T-20261104-01-telegram-rulebook (#272) | commit: 47b5a59
- ne yapıldı: 892 mesaj özel laptop store'unda tarandı; yıllık tema frekansları, örnek ID'ler, LuxAlgo öncelikli motor eşlemesi ve test edilebilir hipotezler raporlandı. Ham metin/görsel repo'ya alınmadı.
- VPS: N/A
- not: Zamanlayıcı aracı bu ortamda yok; döngü manuel tetiklemeli. Sayılar mesaj-başı anahtar sözcük eşleşmesidir, kazanma oranı/performans iddiası değildir.
- istek: claude-code — review/CI.

## 2026-11-04 18:53 UTC — Git ve MCP erişim doğrulaması
- task: T-20261104-01 | branch/PR: collab/abacus/T-20261104-01-telegram-rulebook (#272) | commit: 151e16b
- ne yapıldı: Laptop'tan fetch/push ve `gh` ile PR oluşturma; browser MCP ile public GitHub PR'ını okuma doğrulandı. MODELS.md'de Abacus satırı düzeltildi.
- VPS: N/A
- not: GitHub/TradingView MCP ve bu oturumdan TradingView Desktop erişimi yok/doğrulanmadı; GitHub `gh` erişimi ayrı MCP değil.
- istek: claude-code — MODELS.md farkını da incele; bu protokol dosyası nedeniyle merge operatöre ait.
## 2026-11-05 — T-20261104-12 #280 CHANGES uygulandı (shadow-only)
- task: T-20261104-12 | branch/PR: collab/abacus/T-20261104-12-ws-touch-entry (#280) | commit: PR'da
- ne yapıldı: claude-code CHANGES: `touch_entry` live dalı + lease/emir kodu çıkarıldı (yalnız off|shadow, emir yok); event_scan 2 sn tamponu korundu, event uykudan sonra temizleniyor; shadow satırına trigger_bar_ts/bars_waited eklendi. master (#283) merge edildi. Config değişmedi.
- VPS: NOT-DEPLOYED: DEMO
- not: `live` ancak NET-cost eşiği (n>=30, IS+OOS NET>0, bazdan iyi) + emirleri ana döngüye kuyruklayan ayrı PR ile.
- istek: claude-code → re-review
## 2026-11-05 — T-20261105-03 VPS/GitHub/laptop eşitleme tespiti + deploy ticket'ı

- task: T-20261105-03 | branch/PR: collab/abacus/T-20261105-03-vps-sync-ticket | commit: PR'da

- ne yapıldı: VPS (b6c6bd1, 16 geride, temiz) ve laptop ana klon (d4d737a, 24 geride, 12 commit'siz dosya) salt-okuma karşılaştırıldı; deploy/pull ticket'ı claude-code'a yazıldı. Tespitte VPS'te yalnız `git fetch` çalıştı.

- VPS: N/A

- not: abacus VPS'e/ana klona yazmaz; eşitleme claude-code + operatör onayı.

- istek: claude-code → T-20261105-03 uygula

## 2026-11-05 — T-20261105-04 WS gölge + touch_entry shadow config PR

- task: T-20261105-04 | branch/PR: collab/abacus/T-20261105-04-ws-shadow-flags | commit: PR'da

- ne yapıldı: mid config'e `data_feed.ws.enabled: true`, `event_scan: false`, `smc_v2.touch_entry: shadow` eklendi (yalnız gözlem, emir yolu yok). risk/safety dokunulmadı. #286 review: APPROVE.

- VPS: NOT-DEPLOYED: DEMO

- not: canlıya alma = merge + claude-code deploy ticket + Risk PASS + operatör onayı. Laptop ana klon eşitlemesi başkasının commit'siz işleri yüzünden yapılmadı.

- istek: claude-code → review + (onayla) deploy; operator → onay

## 2026-11-05 — review'ler: #291 merge, #288 merge, #292/#293/#294 verdicts
- task: — | branch/PR: collab/abacus/T-20261105-07-reviews | commit: PR'da
- ne yapıldı: #291 (EF-20261105-04 deploy kaydı) VPS'te doğrulandı (HEAD 6d70ae0, 240 ok / 0 mismatch) ve merge edildi. #288 (gitleaks baseline) 27 fingerprint tek tek doğrulandı (8 geçmiş-yalnız dosya, 3 dummy key'li test dosyası, aktif sır yok) ve squash-merge edildi. #292 (v2 stale/watch_only/balance kapıları): APPROVE — 28 test yerel; #293 (SL taban epsilon): APPROVE — 163 test yerel; #294 (pine-lab): APPROVE — 28 test yerel + build --check rc=0; hepsi draft, merge claude-code/risk-ops/operatör.
- VPS: N/A
- istek: claude-code → #292/#293/#294 draft'larını review'umla birlikte ilerlet
