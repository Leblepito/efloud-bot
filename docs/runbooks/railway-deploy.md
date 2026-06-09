# Railway Deploy & Bağlantı Runbook

Bu repo **iki** Railway servisi deploy eder:

| Servis | Config | Builder | Start | Healthcheck |
|--------|--------|---------|-------|-------------|
| Bot + operatör dashboard | `railway.json` / `railway.toml` (kök) | `DOCKERFILE` | Dockerfile CMD | `/` |
| Pazarlama sitesi (`u2algo-site`) | `u2algo-site/railway.json` | `NIXPACKS` | `node server.js` | `/healthz` |

Canlı pazarlama URL'i: `https://u2algo-site-production.up.railway.app`
(Hedef kanonik domain: `https://u2algo.com` — bkz. dashboard-redesign planı, karar #6.)

## 1) Token'ı gir ("button")

Railway client-id (`RAILWAY_CLIENT_ID`) zaten `.env`'de. **Gizli token'ı** sen gireceksin —
ekranda görünmeden lokal `.env`'e yazan helper:

```powershell
pwsh ./scripts/railway_set_token.ps1            # RAILWAY_TOKEN (proje/deploy token)
pwsh ./scripts/railway_set_token.ps1 -Var RAILWAY_API_TOKEN   # account-level token
```

- Token Railway Dashboard → **Project → Settings → Tokens** (proje token) ya da
  **Account → Tokens** (API token) altından alınır.
- `.env` **gitignored**'dır → token repoya/commit'e/log'a gitmez. Script değeri ekrana basmaz.

Elle de yazabilirsin: `.env` içindeki `RAILWAY_TOKEN=` satırının sağına yapıştır.

## 2) Railway CLI ile deploy

```bash
npm i -g @railway/cli          # kurulu değilse
railway login                  # tarayıcı OAuth (veya RAILWAY_TOKEN env'i otomatik kullanılır)
railway link                   # proje + servis seç
railway up                     # seçili servisi deploy et
```

`RAILWAY_TOKEN` set ise CLI non-interactive çalışır (CI/headless). `railway whoami` ile doğrula.

## 3) Environment değişkenleri (Railway tarafı)

Üretimde sırlar `.env`'den DEĞİL, **Railway Project → Variables**'tan okunur. Lokal `.env`
sadece geliştirme + CLI auth içindir. Bot için zorunlu prod değişkenleri: `BINANCE_API_KEY`,
`BINANCE_API_SECRET`, `EFLOUD_ALLOW_MAINNET`, `DASHBOARD_PASSWORD`, `SESSION_SECRET`,
`ALLOWED_ORIGINS` (bkz. `.env.example`).

> Güvenlik: Railway gizli token'ı sadece lokal `.env` ya da Railway Variables'ta tut.
> Repo/commit/handoff/log'a asla yazma.
