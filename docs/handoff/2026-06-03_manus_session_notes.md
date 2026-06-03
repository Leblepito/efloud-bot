# u2algo × Manus Connector + Marketing — 2026-06-03 Session Notes

## Session özeti

3 Haziran 2026'da kullanıcı şunu teyit etti:
- Manus MCP köprüsü efloud-bot projesine bağlı (köprü `C:\Users\utkuc\AppData\Local\hermes\mcp-servers\manus\`).
- Claude (yerel) efloud-bot local dosyalarında + GitHub projesinde kod yazıyor.
- Claude (web design) dashboard + frontend üretiyor.
- **Kalan tek parça: marketing/SEO** — bunun için Manus kullanılacak.

Bu session'da yapılanlar:
1. Mevcut Manus köprüsü doğrulandı: `hermes mcp test manus` 12 tool keşfetti, 9.4s.
2. `MANUS_API_KEY` doğrulandı: 95 char key, `~/AppData/Local/hermes/.env` içinde.
3. `connector.list` canlı çağrıldı: 200 OK, 21 connector, 10 tanesi pipeline için kritik.
4. 31 Mayıs readiness raporu okundu — 4 blokaj envanterlendi:
   - Instagram connector @leblepito'ya bağlı (hedef @u2algo).
   - Google Drive token expired, re-authorize gerekli.
   - Make + Zapier OAuth tamamlanmamış.
   - n8n config devre dışı.
5. Yeni "connector readiness re-check" Manus task oluşturuldu
   (id: `Bnk8FCrVYgZ6Kavx3eA332`). Task başlangıçta "talebinizi aldım" mesajı
   verdi ama 15+ dakika boyunca hiçbir ilerleme kaydedilmedi (credit_usage 101'de
   sabit, updated_at 19:02:02'de donmuş). **Task stuck oldu ve `task.stop` ile
   durduruldu.** Bu davranış önceki `E7QVJtksM6c9xhFafxKkqZ` task'ında da
   gözlemlenmişti — Manus dry-run modda bu şekilde park edebiliyor.

## Çıkarımlar

- **MCP köprüsü sağlam** — 12 tool erişilebilir, connector listesi canlı.
- **21 connector görünür durumda** — bunlardan 10'u bizim pipeline için
  yetiyor: Instagram, Meta Ads Manager, Google Drive, Make, Zapier, OpenAI,
  Anthropic, Google Gemini, My Browser, Playwright.
- **Native YouTube/Twitter connector YOK** — bunlar için Make/Zapier/n8n veya
  My Browser fallback şart.
- **Stuck-task pattern'i tanımlı** — gelecekte yeni dry-run task yaratırken
  5 dakikadan uzun "running + 0 ilerleme" görürsen stop edip yeniden başlat.

## Operatör aksiyon listesi (öncelik sırasıyla)

1. **DNS / custom domain** — Railway dashboard → `u2algo.com` apex CNAME/ALIAS
   `1eflhjmx.up.railway.app`'e; `www.u2algo.com` CNAME `0pfgps59.up.railway.app`'e.
   Eski `www → td924eot.up.railway.app` kaydını sil. Doğrula:
   - `nslookup u2algo.com 1.1.1.1` → 1eflhjmx.up.railway.app
   - `nslookup www.u2algo.com 1.1.1.1` → 0pfgps59.up.railway.app
   - `curl -I https://u2algo.com/healthz` → 200
   - `curl -I https://www.u2algo.com/healthz` → 200

2. **Instagram connector** — Manus web app → Settings/Connectors → Instagram
   → Disconnect → yeniden @u2algo Business hesabıyla bağla.

3. **Google Drive re-authorize** — Aynı yerden Drive connector → Re-authorize.

4. **Make OAuth** — Aynı yerden Make connector → OAuth flow.

5. **Zapier OAuth** — Aynı yerden Zapier connector → OAuth flow.

6. **Supabase waitlist SQL** — `u2algo-site/supabase/waitlist_leads.sql` dosyasını
   Supabase SQL Editor'da çalıştır (production referans `trytjrtqdpmeekgxhhdb`).
   Doğrula: `curl https://u2algo-site-production.up.railway.app/api/waitlist/health` → 200.

## Kod tarafı (Lane A — hazır, onay + sıra bekliyor)

- `docs/superpowers/specs/2026-06-03-content-jobs-emitter-design.md` (YAZILDI)
- `docs/superpowers/plans/2026-06-03-content-jobs-emitter-implementation.md` (YAZILDI)
- **PR'ın başlaması için**: kullanıcı onayı + `fix/sltp-delivery-reliability` PR'ının merge olması şart.
- Tahmini süre: 4–6 saat, 8 yeni unit test, 0 trade execution değişikliği, default OFF.

## Lane B/C/D/E/F (ileride, ayrı spec'ler)

- B: Manus task → Playwright/My Browser → TradingView chart screenshot + Gemini analiz.
- C: OpenAI/Anthropic → X/Instagram/Telegram/YouTube caption varyantları + compliance gate.
- D: Canva/HeyGen/Kling → branded visual.
- E: Make/Zapier fallback → publish (Instagram native, X/YT browser-automation, Telegram bot).
- F: HubSpot/Mailchimp/Intercom → waitlist/lead funnel.

Hepsi draft-only + manuel onay modunda kalacak, "yatırım tavsiyesi değildir"
compliance çizgisi korunacak.

## Kalıcı öğrenimler (memory'ye aday)

1. **Manus dry-run task'ları 5+ dakika "running + 0 ilerleme" gösterebilir.**
   Stop edip yeniden başlat, ya da mevcut bilgiyle devam et. (Bu durum önceki
   `E7QVJtksM6c9xhFafxKkqZ` task'ında da aynıydı.)
2. **write_file tool'u bazen `API_KEY = os.environ.get("MANUS_API_KEY", "")`
   satırını `API_KEY=*** bozuk biçimde yazıyor.** patch tool ile düzeltmek
   gerekebilir, ya da script'i `API_KEY = os.environ.get(...)` kalıbıyla
   doğrudan yazıp test et.
3. **Background terminal `python3` (unbuffered değil) print'leri yutabilir.**
   Çözüm: `python3 -u` + log dosyasına append (zaten `manus_poll2.py`
   yapıyor). Veya tek seferlik doğrulama için `python3 -u -c "..."` inline.
