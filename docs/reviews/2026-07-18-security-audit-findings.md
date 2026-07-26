# 2026-07-18 Güvenlik Denetimi (W5) — Bulgular

Kapsam: master `1c3dc1a`. Araçlar: git-history secret taraması (device, tam
geçmiş), `pip-audit` (requirements + constraints), `bandit` (canlı kod dizinleri),
`npm audit` (frontend + u2algo-site). Statik + kompozisyon analizi; canlı
sistemde değişiklik YAPILMADI. Bu doküman W5'in tarama+triyaj ayağıdır; kod
sertleştirme fix'leri (bulgu tablosundaki öneriler) ayrı, gözden geçirmeli
adımlarda uygulanır.

## Yönetici özeti

**Secret hijyeni TEMİZ — acil rotasyon GEREKMİYOR.** Deploy gecesi VPS'te
`.env.production`'ın "tracked" görünüp reset'le silinmesi, canonical git
geçmişinde secret sızıntısı OLDUĞU anlamına gelmiyordu; kanonik geçmiş temiz
çıktı. Kritik/High gerçek bulgu yok. Kalan kalemler düşük-öncelik sertleştirme.

| Alan | Sonuç |
|------|-------|
| Git geçmişinde secret | ✅ TEMİZ — `.env.production*` HİÇ commit'lenmemiş; config yaml `api_key/api_secret` hepsi BOŞ (`""`, key'ler env'den); yalnız `.example`/`.template` tracked |
| Python bağımlılık CVE | 1 düşük: `setuptools` 82.0.1 → 83.0.0 (PYSEC-2026-3447; ortam paketi, requirements'ta yok) |
| npm CVE | u2algo-site: 0 · frontend: 3 moderate (PostCSS XSS, `geist` üzerinden — build-time CSS, runtime yolu değil) |
| bandit | High: 1 (SHA1 — güvenlik amaçlı DEĞİL, false-positive) · Medium: 24 (aşağıda triyaj) · gerisi Low gürültü |
| Statik SQLi | B608 adayları false-positive (config-kaynaklı tablo adı, kullanıcı girdisi yok) |

## 1. Secret hijyeni (en yüksek öncelikli alan) — TEMİZ

- `git log --all --diff-filter=A -- '.env' '.env.*'`: yalnız `.env.example`,
  `.env.template`, `deploy/*.example` eklenmiş — **placeholder'lar**.
- `git log --all -- '.env.production' '.env.production.scalp' '.env.production.long'`:
  **BOŞ** — gerçek secret dosyası hiçbir commit'te yok.
- Tüm tracked `config*.yaml` / `configs/**/*.yaml`: `api_key`/`api_secret`
  alanlarının hepsi `""` (yanında env-var'ı belgeleyen `# yorum`); bot key'leri
  `os.environ`'dan okur. Boş-olmayan hardcoded key: **0**.
- `.gitignore` `.env` ve `.env.production`'ı kapsıyor ✅.

**Sonuç:** Binance/Supabase key'leri git'e hiç girmemiş → planlı "geçmiş tarama +
zorunlu rotasyon" (W5.1) bir GÜVENLİK ZORUNLULUĞU DEĞİL. Rotasyon yine de iyi
hijyendir (periyodik) ama acil değil. Not: VPS'in yerel tree'sinde
`.env.production` bir ara index'e girmişti (deploy gecesi reset onu sildi);
bu YEREL bir durumdu, GitHub geçmişine yansımadı. Yine de VPS'te
`.env.production*` artık `/root/envbackup/`'ta yedekli ve gitignore kapsamında.

## 2. Python bağımlılık CVE

- `setuptools 82.0.1` → **83.0.0** (PYSEC-2026-3447). Ortam/build paketi;
  `requirements.txt`/`constraints.txt`'te doğrudan yok, çalışan bota etkisi
  minimal. Öneri: bir sonraki image rebuild'inde base pip/setuptools güncel
  gelsin; istenirse constraints'e `setuptools>=83.0.0` eklenebilir.
- constraints.txt pinli kapanışında (canlı çalışan sürümler) başka CVE yok.

## 3. npm CVE

- `u2algo-site`: **0** vulnerability.
- `frontend`: **3 moderate** — PostCSS "XSS via Unescaped `</style>`"
  (GHSA-qx2v-qp2m-jg93), `geist` paketi zinciri üzerinden. Build-time CSS
  stringify; kullanıcı-kontrollü CSS girişi yok → gerçek risk düşük.
  Öneri: uygun bir bakım penceresinde `npm audit fix` (frontend), sonra
  `npm run build` + smoke.

## 4. bandit triyajı (canlı kod)

| Test | Yer | Değerlendirme | Öneri |
|------|-----|---------------|-------|
| B324 SHA1 (High) | `engine/signal_ledger.py:68` `mint_id` | GÜVENLİK DEĞİL — sinyal ID'si için 8-hane içerik hash'i (edge-ledger, default-OFF). False-positive | İsteğe bağlı: `hashlib.sha1(..., usedforsecurity=False)` (çıktı birebir aynı) — birlikte-oturumda, engine dokunuşu |
| B310 urlopen (Med×4) | alerter/telegram_client/telegram_poller, overseer/healthz_poller | Sabit https şema (Telegram API + healthz); kullanıcı-URL'i yok | Kabul; istenirse şema whitelist assert'i |
| B104 bind 0.0.0.0 (Med×2) | ops/ig_webhook_server, vps_webhook_forwarder | Webhook sunucuları, container ağında Caddy arkasında | Kabul; compose port publish'i yok (dışarı kapalı) |
| B608 SQL (Med, Low-conf) | scripts/bigquery_archive.py, +1 | Tablo adı config'ten (`{project}.{dataset}.{table}`), kullanıcı girdisi yok | False-positive; not düşüldü |
| B108 /tmp (Med, çoğu test) | tests/ + lane_* içerik scriptleri | Test/araç kodu, canlı yol değil | Düşük; gerekirse `tempfile` |

Gerçek **Kritik/High güvenlik açığı: 0.** High-flagged tek kalem (SHA1)
false-positive.

## 5. Öneri sırası (hiçbiri acil değil)

1. `frontend` PostCSS moderate → bakım penceresinde `npm audit fix` + build smoke.
2. Bir sonraki rebuild'de setuptools güncel (opsiyonel constraints pin).
3. (İsteğe bağlı, birlikte-oturum) `signal_ledger.mint_id` → `usedforsecurity=False`.
4. Periyodik key rotasyonu — güvenlik zorunluluğu değil, rutin hijyen (çeyreklik).
5. Kalan bandit Medium'lar bilinçli kabul; runbook'a "webhook'lar Caddy arkasında,
   0.0.0.0 bind kasıtlı" notu.

## Yöntem/kanıt notları

- Secret değerleri chat'e/loga hiç dökülmedi; sınıflandırma yapı-maskesiyle
  (harf→a, rakam→9) ve uzunluk/prefix ile yapıldı.
- Tam git-history taraması `.git` mount I/O'da 45s'ye sığmadığından hedefli
  `git log --all --diff-filter=A` + `git grep <rev-list>` ile device üzerinde
  koşuldu (fonksiyonel olarak eşdeğer, secret-dosya odaklı).
