# xurl Setup Runbook (P-002 Faz A M1 — T-026)

> **Operatör rehberi.** xurl CLI kurulumu + Twitter OAuth flow + VPS caveat + secret hygiene.

## 1. Mimari

```
┌─────────────────┐    OAuth PIN     ┌──────────────────┐
│ Local Operator  │◄────────────────►│  Twitter Dev App │
│ (browser var)   │   (1 kere)       │  (x.com portal)  │
└────────┬────────┘                  └──────────────────┘
         │ xurl auth (writes ~/.xurl)
         ▼
   ~/.xurl cache (4 OAuth credential)
         │
         │  SSH tunnel / rsync (1 kere)
         ▼
┌─────────────────┐
│ Hetzner VPS     │  xurl binary (Go, kurulum opsiyonel)
│ (no browser)    │  └─ XurlClient facade (`backend/social/xurl_client.py`)
│                 │     ├─ flag-gated (`X_API_ENABLED=true`)
│                 │     ├─ compliance gate (BANNED phrases / money / perf-pct)
│                 │     └─ shell-out → `xurl post --text "..."`
└─────────────────┘
```

**Neden VPS'te browser yok:** OAuth PIN-based flow kullanıcının tarayıcıda
onay vermesini gerektiriyor. VPS headless → mümkün değil. **Çözüm:**
auth local'de yapılır, `~/.xurl` cache SSH ile VPS'e kopyalanır.

## 2. Local Kurulum (5 dakika)

### Adım 1 — xurl binary kur

**macOS / Linux:**
```bash
# Go ile (önerilen — en güncel)
go install github.com/anthonyrabiaza/xurl@latest
# binary $GOPATH/bin/xurl veya ~/go/bin/xurl'a düşer

# veya Homebrew (macOS)
brew tap anthonyrabiaza/xurl
brew install xurl

# doğrula
xurl --version
# → xurl version 0.x.y
```

**Windows:**
```powershell
go install github.com/anthonyrabiaza/xurl@latest
# %USERPROFILE%\go\bin\xurl.exe PATH'e ekle
xurl --version
```

### Adım 2 — Twitter Developer App oluştur

1. <https://developer.twitter.com/en/portal/dashboard> → Sign in
2. **"+ Create Project"** → ad: `efloud-bot` (free tier), use case: "Making a bot"
3. **App oluştur** → Keys & Tokens sekmesi
4. **Consumer Keys** (`API Key` + `API Key Secret`) → **göster**, **kopyala**
5. **Authentication Settings** → "OAuth 1.0a" + "OAuth 2.0" + "Read and Write" permission
6. **"Regenerate"** User Access Tokens → **göster**, **kopyala**
7. Callback URL: `http://localhost:8080/callback` (xurl OAuth flow'u bunu kullanmaz
   — sadece portal validation için ister)

**Toplamda 4 credential:**
```
Consumer Key (X_API_KEY)            = abc123...
Consumer Secret (X_API_SECRET)      = XYZ789...
Access Token (X_ACCESS_TOKEN)        = 1234-AAAA...
Access Token Secret (X_ACCESS_SECRET) = BBBB
```

### Adım 3 — xurl auth (PIN flow)

```bash
xurl auth \
  --api-key "abc123..." \
  --api-secret "XYZ789..." \
  --access-token "1234-AAAA..." \
  --access-secret "BBBB"
```

`xurl` bunları `~/.xurl/config.json` (veya benzer path) cache'ler.
**Bu dosya SECRET içerir** — sızdırma.

```bash
chmod 600 ~/.xurl/config.json
ls -la ~/.xurl/config.json
# -rw------- 1 user user ...  config.json
```

### Adım 4 — Smoke test (local'de)

```bash
# dry-run (subprocess YAPMAZ, sadece parse)
xurl post --text "test smoke" --dry-run

# gerçek post (ilk gerçek tweet)
xurl post --text "test from efloud xurl setup"
# → tweet URL dönmeli: https://x.com/<kullanıcı>/status/<id>
```

Eğer hata alırsan:
- `auth failed: token expired` → adım 2'de Access Token regenerate et
- `forbidden` → App permission "Read and Write" değil
- `rate limit` → 15 dakika bekle, x.com free tier saatlik limit koyar

## 3. VPS'e credential aktar

**Önemli:** VPS'te `xurl` binary çalıştırmak **opsiyonel**. XurlClient facade
xurl binary'siz bile çalışır (shell-out fail olur, ama default OFF olduğu için
caller zaten XurlDisabled alır). **Credential transfer için 2 yol:**

### Yol A — SSH tunnel (önerilen, credential VPS'te tutulmaz)

VPS'te xurl auth gerektiğinde, local'den SSH ile reverse tunnel aç:

```bash
# LOCAL makinede
ssh -R 9001:localhost:8080 efloud-bot

# VPS'te (artık local:8081 erişilebilir)
# HENÜZ: efloud-bot auth flow'u bu yolu native desteklemiyor (T-026 facade basic)
# M6 içerik onay kuyruğu bu özelliği ekleyecek.
```

### Yol B — Env-based credential (basit ama VPS'te secret tutmak demek)

VPS'te `.env.production`'a credential ekle:

```bash
# /opt/efloud-bot/.env.production'a ekle (chmod 600)
X_API_ENABLED=true
X_API_KEY=abc123...
X_API_SECRET=XYZ789...
X_ACCESS_TOKEN=1234-AAAA...
X_ACCESS_SECRET=BBBB
```

**Secret hygiene:**
- `.env.production` zaten `.gitignore`'da (chmod 600)
- Repo'ya KESİNLİKLE commit etme (gitleaks CI fail eder)
- Bir kere sızdıysa: Twitter portal'dan regenerate et
- Free tier saatlik 100 tweet limit — beklenmedik rate spike'ları monitorle

### xurl binary VPS'e kur (opsiyonel — sadece ssh+tunnel veya env kullanacaksan gerekli)

```bash
# VPS'e SSH
ssh efloud-bot

# Go kurulu değilse
sudo apt install -y golang-go

# xurl kur
go install github.com/anthonyrabiaza/xurl@latest
# Binary $HOME/go/bin/xurl'a düşer — PATH'e ekle veya XURL_BIN_PATH=/root/go/bin/xurl env set et
```

## 4. XurlClient facade (Python) doğrulama

PR merge sonrası VPS'te:

```bash
cd /opt/efloud-bot
source /etc/efloud-backup.env  # veya .env.production source

# Auth + binary check
python3 <<'EOF'
import sys; sys.path.insert(0, '/opt/efloud-bot')
from backend.social.xurl_client import XurlClient, _binary_path, _mask_credential
c = XurlClient()
print(f"is_active={c.is_active()}")
print(f"bin_path={_binary_path()}")
print(f"creds={c.credentials_masked()}")
EOF

# Beklenen: is_active=True (flag + 4 creds), bin_path=/root/go/bin/xurl (veya None)

# Dry-run smoke
python3 -m backend.social.xurl_client post --text "smoke from VPS" --dry-run
# → {"ok": true, "dry_run": true, "would_execute": true, ...}

# Gerçek post (opsiyonel — free tier 100 tweet/saat limit)
python3 -m backend.social.xurl_client post --text "first VPS post via efloud xurl facade"
# → {"ok": true, "dry_run": false, "post_id": "...", "post_url": "https://x.com/.../..."}
```

## 5. Tehlike Sinyalleri

| Sinyal | Olası sebep | Aksiyon |
|---|---|---|
| `XurlDisabled: xurl client not active` | flag veya creds eksik | `.env.production` kontrol |
| `XurlNotInstalled` | `xurl` binary PATH'te yok | `XURL_BIN_PATH` env set veya `apt install` |
| `XurlComplianceViolation: banned_phrase:X` | post BANNED listesinde | text'i düzelt |
| `XurlComplianceViolation: text_too_long` | 280 char limit (free tier) | thread kullan veya kısalt |
| `XurlSubprocessError: http_401` (xurl stderr) | Twitter OAuth expired | portal'dan token regenerate |
| `XurlSubprocessError: timeout_after_15s` | xurl dondu / network kill | binary reinstall, retry |
| `would_execute: true` ama `ok: false` (shadow mode) | dry_run=True, gerçek post YOK | dry_run=False ile retry |

## 6. Compliance gate (otomatik)

`XurlClient.post()` her çağrıda `scripts/content_compliance.find_violations`
ile pre-flight check yapar:

- **TR banned phrases**: "Kesin kazanç", "Garantili getiri", "Her gün kâr",
  "Pasif gelir makinesi", "Sinyal al, kazan", "Fonumuza para yatır"
- **EN banned phrases**: "guaranteed profit", "guaranteed returns",
  "risk-free", "no loss", "passive income machine", "get rich" vb. (14 phrase)
- **Absolute money**: `$X` — whitelist sadece `$39 lifetime` ürün fiyatı
- **Performance %**: "%X kar" / "X% return" gibi performans iddiaları
- **Unlabeled simulation**: `[BACKTEST]` etiketi olmadan "backtest" kelimesi

Violation varsa `XurlComplianceViolation` raise edilir, subprocess **YAPILMAZ**.

## 7. Referanslar

- xurl GitHub: <https://github.com/anthonyrabiaza/xurl>
- Twitter Developer Portal: <https://developer.twitter.com/en/portal/dashboard>
- Twitter Free Tier limits: <https://developer.twitter.com/en/docs/twitter-api/rate-limits>
- Bu facade: `backend/social/xurl_client.py` (580 satır)
- 23 unit test: `backend/tests/test_xurl_client.py`
- Compliance modülü: `scripts/content_compliance.py`
- Plan: `LLTODO/plans/P-002-marketing-growth-pipeline.md` §2 M1
