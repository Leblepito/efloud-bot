# u2algo Frontend Railway Deploy Runbook — 2026-06-04

> Sıfırdan deploy. Önceki oturumdaki proje (`a360e403-...`) silindiği için
> ADIM 1-4 yeniden yazıldı. ADIM 1.5 itibarıyla bu rehber tamamlanır.
>
> Amaç: `u2algo.com` ve `www.u2algo.com` → Railway `u2algo-site` service,
> `/healthz` 200, `/` HTML, waitlist API çalışıyor.

## 0. Ön koşullar (tek seferlik)

- Repo public: github.com/Leblepito/efloud-bot, branch master, son commit
  `u2algo-site/` dosyalarını içeriyor. (`docs/handoff/2026-05-31_u2algo-railway-live.md`
  § "Files added/changed" + 2026-06-03 session.)
- Railway CLI hostta kurulu: `railway --version` → 4.36.1 (doğrulandı 2026-06-04).
- `railway whoami` → Leblepito, login geçerli.
- Supabase prod project `trytjrtqdpmeekgxhhdb`, env `.env.supabase`'de.
- Manuel DNS yönetimi (GoDaddy/Cloudflare) kullanıcı tarafında, erişim var.

## ADIM 1 — Railway projesi oluştur (sıfırdan, kullanıcı onayı gerekli)

Üç seçenek var. Kullanıcı tercih eder.

### 1A. UI (önerilen, hızlı)
1. https://railway.com/new → "Deploy from GitHub repo"
2. Repo: `Leblepito/efloud-bot` (zaten yetkili)
3. Railway otomatik `Empty Service` oluşturur → "Add variables" atla, **Cancel** de
   (henüz env yok)
4. Sağ üstten "Settings" → Project Name: `u2algo-prod` (veya kullanıcı ismi)
5. NOT: kullanıcı tek tıkla tüm süreci UI'da yürütebilir. Aşağıdaki adımlar UI/CLI
   dual-track yazıldı.

### 1B. CLI
```bash
railway init
# "Empty Service" seç (GitHub repo deploy değil, boş başla)
railway link --project <new-project-id>   # init çıktısından
```

### 1C. Önceki oturumdaki handoff project_id geri alınamaz
`a360e403-b4ee-47e8-a8b7-27307d41f67c` artık listede yok (`railway list` 2026-06-04
doğruladı). Yenisi gerekli.

## ADIM 2 — GitHub repo'yu projeye bağla (1 kez)

UI: Project → "+ New" → "GitHub Repo" → `Leblepito/efloud-bot`

CLI yok (GitHub bağlama UI-only).

## ADIM 3 — Service ayarları (KRİTİK: Root Directory)

Service `Settings`:

- **Root Directory**: `u2algo-site`  ← ZORUNLU. Yoksa Nixpacks monorepo kökünde çalışır,
  `package.json` bulamaz, build patlar.
- **Builder**: NIXPACKS (default zaten)
- **Healthcheck Path**: `/healthz`  (raylıway.json'da tanımlı, override gerekmez)
- **Watch Paths**: boş bırak (her push build tetikler, gerek yok)

Doğrulama: Settings ekranında "Build Command" boş olmalı, "Start Command"
`node server.js` Nixpacks'ten gelecek.

## ADIM 4 — Env variables (Variables sekmesi)

**Zorunlu**:
```
PORT=3000
LOCAL_WAITLIST_PATH=/tmp/waitlist_leads.jsonl
```

**İsteğe bağlı ama önerilen** (waitlist DB'ye yazsın):
```
SUPABASE_URL=https://trytjrtqdpmeekgxhhdb.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service_role_key_from_supabase_dashboard>
```

Eğer SUPABASE_DATABASE_URL varsa (pooler, port 6543):
```
SUPABASE_DATABASE_URL=postgresql://postgres.trytjrtqdpmeekgxhhdb:<pwd>@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
```

Eğer Supabase env yoksa: server.js `local-jsonl` fallback yazar, Railway
container'da `/tmp/waitlist_leads.jsonl` dosyasında birikir. **Geçici çözüm,
production için Supabase kurulmalı.**

NOT: Token'lar terminale yapıştırılmaz. Kullanıcı Railway UI Variables
sekmesine kendisi yazar veya `.env.supabase` içeriğini Hermes'e vermeden
okutur.

## ADIM 5 — İlk deploy (otomatik)

UI'da Root Directory + Variables kaydedildiğinde Railway otomatik deploy tetikler.

CLI'de log izlemek için:
```bash
railway logs --service u2algo-site -f
```

Beklenen log sırası:
```
Nixpacks: Node 20 detected
npm install --omit=dev
npm run smoke → "smoke OK: <N> bytes, compliance gate passed"
node server.js
u2algo-site listening on 3000
```

Smoke FAIL olursa deploy yine başarılı sayılabilir (Nixpacks `start` zaten
çalışır), ama `nixpacks.toml` build phase'inde `npm run smoke` hata verirse
build fail eder — index.html'de compliance phrase eksik demektir.

## ADIM 6 — Doğrulama (deploy bittikten ~30 sn sonra)

```bash
# Railway domain (otomatik üretilmiş):
curl -sI https://u2algo-site-production.up.railway.app/healthz
# Beklenen: HTTP/2 200
# Body: {"ok":true,"service":"u2algo-site"}

curl -sI https://u2algo-site-production.up.railway.app/
# Beklenen: HTTP/2 200, content-type: text/html

curl -s https://u2algo-site-production.up.railway.app/api/waitlist/health
# Beklenen: {"ok":true,"service":"u2algo-waitlist","database":"not_configured"...}
# (Supabase yoksa "not_configured" veya "unhealthy", SORUN DEĞİL)
```

UI doğrulama:
1. https://u2algo-site-production.up.railway.app/ → tarayıcıda landing aç
2. "yatırım tavsiyesi değildir" disclaimer görünüyor
3. Waitlist form email input → POST → 200 (Supabase yoksa local-jsonl'e yazar)

## ADIM 7 — Custom domain: u2algo.com + www.u2algo.com (kullanıcı işi)

### 7.1 Manuel DNS panelinde yeni CNAME'ler (kullanıcı)

Önceki oturumda hedefler belirlendi:
- apex `u2algo.com` → A record Railway edge IP'leri veya CNAME → `emjwy9v1.up.railway.app`
- www `www.u2algo.com` → CNAME → `o7cu2347.up.railway.app`

**Kullanıcı eklemedi henüz (2026-06-03 handoff §4).** Şimdi eklemeli.

Apex için Railway yönergesi:
- Apex (u2algo.com) için CNAME genelde çalışmaz, A record veya ALIAS gerekli.
- Railway Settings → Domains → "Add Domain" → `u2algo.com` ekleyince Railway
  **gerekli DNS kaydını** gösterir (A veya CNAME). Bu kaydı kullanıcı DNS
  paneline yazar.

### 7.2 Railway'de custom domain ekle
Service → Settings → Domains → "Add Domain" → `u2algo.com` → Railway DNS
bilgisi verir → kullanıcı DNS paneline yazar → SSL otomatik (~5-10 dk).

`www.u2algo.com` için de tekrarla.

### 7.3 Doğrulama
```bash
curl -I https://u2algo.com/healthz
curl -I https://www.u2algo.com/healthz
# 200 beklenir. SSL sertifika valid olmalı, Railway fallback 404 OLMAMALI.
```

## ADIM 8 — Supabase waitlist_leads tablosu (kullanıcı işi)

`u2algo-site/supabase/waitlist_leads.sql` içeriği 33 satır (2026-05-31 handoff
§ Waitlist backend). Kullanıcı Supabase Dashboard → SQL Editor →
`trytjrtqdpmeekgxhhdb` projesi → yapıştır → Run.

Sonra:
```bash
curl -s https://u2algo-site-production.up.railway.app/api/waitlist/health
# Beklenen: database: "ready", backend: "supabase"

curl -s -X POST https://u2algo-site-production.up.railway.app/api/waitlist \
  -H 'content-type: application/json' \
  -d '{"email":"test@example.com"}'
# Beklenen: {"ok":true,"backend":"supabase"}
```

## ADIM 9 — Sıradaki iş (deploy bittikten sonra)

1. DNS doğrulandıktan sonra: Google Search Console + Bing Webmaster
   `https://u2algo.com/sitemap.xml` submit
2. Lane A content_job emit kodu (handoff §5, `fix/sltp-delivery-reliability`
   merge sonrası)
3. Manus Görev 1 (DRY-RUN Meta keşif, Telegram msg 3894 prompt hazır)

## Bilinen yapışkan noktalar

1. **Supabase env yoksa** waitlist sadece local-jsonl'e yazar. Container
   restart'ta kaybolur (Nixpacks ephemeral fs). **Production için Supabase şart.**
2. **Apex domain (u2algo.com)** bazı DNS sağlayıcılarda CNAME reddeder, ALIAS
   veya A+CNAME flattening gerekli. Cloudflare → CNAME flattening otomatik,
   GoDaddy → "Domain forwarding" gerekebilir.
3. **Railway ücretsiz plan $5/month kredi** — production için yeterli değil,
   kullanıcı credit card eklemeli (handoff'ta belirtilmemiş ama deploy
   çalışabilir, kredi bitince durur).
4. **Repo monorepo.** `Root Directory: u2algo-site` ayarlanmazsa Nixpacks
   `efloud-bot/package.json` (Python projesi) bulur, Node kurmaya çalışır,
   "package.json not found" hatası verir.

## Rollback

Railway service silinirse:
```bash
# Railway Dashboard → Service → Settings → "Remove Service"
# Domain DNS'te eski CNAME kalırsa Railway 404 döner, kullanıcı DNS'ten
# silmeli.
```

Git revert gerekmez, repo etkilenmez.

## Son commit'ler (deploy tetikleyen master push'lar)

2026-05-31 sonrası `u2algo-site/` dosyalarında değişiklik yok (sadece trade bot
tarafı geliştirildi). Bu yüzden **mevcut master HEAD ile deploy güvenli**,
rebase gerekmez.
