# u2algo Launch Readiness — 2026-05-31

Bu doküman u2algo public website + Manus/social launch hazırlığının mevcut durumunu özetler.

## 1) Website / Railway durumu

Railway service:
- Project: perpetual-tenderness
- Service: u2algo-site
- Latest deployment: 4619340c-e488-439a-a208-e0cca33c7185
- Status: SUCCESS
- Geçici canlı URL: https://u2algo-site-production.up.railway.app

Canlı doğrulanan endpointler:
- https://u2algo-site-production.up.railway.app/ -> 200
- https://u2algo-site-production.up.railway.app/healthz -> 200
- https://u2algo-site-production.up.railway.app/robots.txt -> 200
- https://u2algo-site-production.up.railway.app/sitemap.xml -> 200

Eklenen launch/SEO dosyaları:
- u2algo-site/robots.txt
- u2algo-site/sitemap.xml

Build/smoke:
- `npm run smoke && node --check server.js && npm run build --workspace=web` geçti.
- Railway build içinde smoke geçti: compliance gate passed.

## 2) Custom domain durumu

Railway artık domainleri service üzerinde listeliyor:
- https://u2algo.com
- https://www.u2algo.com

Ancak canlı DNS/TLS henüz hazır değil:
- https://u2algo.com/ -> Railway 404 Application not found
- https://u2algo.com/healthz -> Railway 404 Application not found
- https://www.u2algo.com/ -> TLS/SNI certificate mismatch
- https://www.u2algo.com/healthz -> TLS/SNI certificate mismatch

Public resolver gözlemi:
- u2algo.com hâlâ 151.101.2.15 adresine çözülüyor.
- www.u2algo.com hâlâ td924eot.up.railway.app / 66.33.22.57 tarafına çözülüyor.
- Beklenen hedefler henüz görünmüyor:
  - apex için: 1eflhjmx.up.railway.app
  - www için: 0pfgps59.up.railway.app

Sonuç: Railway dashboard tarafı tamamlanmış görünüyor; DNS panelindeki kayıtlar ya henüz yayılmadı ya da eski kayıtlar hâlâ aktif. Public launch postlarında ana link olarak şimdilik custom domain kullanılmamalı; DNS oturana kadar Railway geçici URL sadece internal test için kullanılmalı.

## 3) DNS düzeltme/checklist

DNS sağlayıcı panelinde kontrol edilecekler:

Apex/root `u2algo.com` için:
- Host/name: `@`
- Type: CNAME veya sağlayıcı destekliyorsa ALIAS/ANAME flattening
- Value: `1eflhjmx.up.railway.app`
- TXT verification:
  - Host/name: `_railway-verify`
  - Value: Railway tarafından verilen verification değeri

WWW için:
- Host/name: `www`
- Type: CNAME
- Value: `0pfgps59.up.railway.app`
- TXT verification:
  - Host/name: `_railway-verify.www`
  - Value: Railway tarafından verilen verification değeri

Önemli:
- Eski `www -> td924eot.up.railway.app` kaydı kaldırılmalı.
- Eski apex A/CNAME kayıtları Railway’in yeni hedefiyle çakışmamalı.
- DNS provider CNAME at apex desteklemiyorsa ALIAS/ANAME veya Railway’in önerdiği flattening yöntemi kullanılmalı.
- Cloudflare/proxy benzeri bir katman varsa ilk doğrulamada DNS-only denenmeli.

Doğrulama komutları:

```bash
nslookup u2algo.com 1.1.1.1
nslookup www.u2algo.com 1.1.1.1
nslookup -type=TXT _railway-verify.u2algo.com 1.1.1.1
nslookup -type=TXT _railway-verify.www.u2algo.com 1.1.1.1
curl -I https://u2algo.com/healthz
curl -I https://www.u2algo.com/healthz
```

Kabul kriteri:
- `https://u2algo.com/healthz` -> 200
- `https://www.u2algo.com/healthz` -> 200
- sertifika hatası yok
- Railway 404 Application not found yok

## 4) Manus MCP/API durumu

Hermes -> Manus MCP bridge çalışıyor:
- `hermes mcp test manus` başarılı.
- 12 tool discovery başarılı.
- `connector.list` canlı API ile 200 OK.

Öne çıkan connectorlar:
- Instagram: `4b899211-fd12-410e-a8d2-264a409cbc78`
- Meta Ads Manager: `c073ede4-35a7-4c89-8158-c9b40c489932`
- Zapier: `433d2fe0-e56d-42b2-8625-9996eab0bb1d`
- Make: `f8405590-5602-4fee-bfd6-f221623e6f72`
- Google Drive: `f8900a57-4bd7-46cc-83a3-5ebd2420a817`
- Gmail: `9444d960-ab7e-450f-9cb9-b9467fb0adda`
- My Browser: `be268223-40b2-4f3c-a907-c12eb1699283`
- Supabase: `84ab78ef-139c-48ff-acd4-cba718b8a484`
- Vercel: `a50c5d31-af5e-4e01-a992-057663a7ee1f`
- Cloudflare: `119e6b13-c2e3-48db-b568-f82191de6b4e`

Manus private görevleri:
- Launch draft task: `aPPH7wem8WqcNTY5eojs4e` tamamlandı, private/draft-only.
- Connector readiness task: `E7QVJtksM6c9xhFafxKkqZ` oluşturuldu, private/dry-run-only. İlk poll sırasında hâlâ running idi; yayın yapmaması özellikle söylendi.

## 5) İlk paylaşım sistemi — güvenli mimari

Şu aşamada önerilen mod: draft-only + insan onayı.

Pipeline:
1. efloud-bot sinyal veya manuel launch olayı gelir.
2. TradingView/MCP ekran görüntüsü alınır.
3. Hermes/Manus taslak üretir:
   - X kısa post
   - Instagram carousel/reel caption
   - Telegram duyurusu
   - YouTube Shorts/Reels script/caption
4. Compliance scan:
   - yatırım tavsiyesi değildir
   - DYOR
   - risk bildirimi
   - geçmiş performans garantisi değildir
   - yasaklı vaat/garanti/fon toplama ifadeleri yok
5. İnsan onayı alınır.
6. Sadece onay sonrası platform connectorlarıyla yayın yapılır.

Yayın otomasyonu henüz kapalı kalmalı. İlk paylaşımlar domain hazır olduktan ve connector auth doğrulandıktan sonra yapılmalı.

## 6) İlk paylaşım için hazır taslak dosya

Manus tarafından oluşturulan private draft-only içerik paketi:
- `docs/handoff/2026-05-31_u2algo_launch_draft_only.md`

İçerik:
- 3 adet X/Twitter post taslağı
- 5 slide Instagram carousel metni
- Telegram topluluk duyurusu
- 30 sn Shorts/Reels script
- DNS/TLS kontrol checklist

## 7) Eksikler

Launch öncesi kalan işler:
1. DNS kayıtlarını gerçek hedeflere oturt:
   - `u2algo.com -> 1eflhjmx.up.railway.app`
   - `www.u2algo.com -> 0pfgps59.up.railway.app`
2. `https://u2algo.com/healthz` ve `https://www.u2algo.com/healthz` 200 olana kadar public duyuru yapma.
3. Manus web app içinde şu connectorların authorize edildiğini kontrol et:
   - Instagram
   - Google Drive
   - Make veya Zapier
   - My Browser gerekiyorsa
   - Meta Ads Manager sadece analytics/reporting için
4. X/Twitter ve YouTube için native Manus connector görünmedi; Make/Zapier/n8n veya browser automation fallback gerekiyor.
5. Supabase waitlist daha önce DB health 503 veriyordu; SQL migration/env/DNS ayrıca çözülmeli.
6. Public paylaşım için en az bir görsel asset hazırlanmalı:
   - 1200x675 X/link preview
   - 1080x1080 Instagram carousel cover
   - 1080x1920 Reels/Shorts dikey video veya story frame

## 8) Compliance notu

Tüm public metinlerde şu çizgi korunmalı:
- u2algo bir araştırma/gözlem/analiz altyapısıdır.
- Fon yönetimi veya para toplama değildir.
- Kâr/getiri garantisi yoktur.
- İçerikler yatırım tavsiyesi değildir.
- Kripto ve kaldıraçlı işlemler yüksek risk içerir.
- DYOR.
