---
id: T-20261104-04
title: Operatör kararları — erişim, kimlikler, master koruması
from: claude-code
to: operator
status: open
claimed_by: null
reviewer: null
created: 2026-11-04
touches_live: false
---

## Amaç
Sistemin güvenli çalışması için yalnız operatörün yapabileceği adımlar.

## Beklenen çıktı
- [ ] Karantina PR'ını (`feat/quarantine-hermes-skills`) incele + merge et; ardından protokol PR'ını (`feat/collab-protocol`).
- [ ] **master branch koruması** (şu an `protected: false`): "PR zorunlu, force-push yok" kuralını aç. Protokol bunu varsayıyor; koruma yokken kural yalnız sözlü.
- [ ] Hermes için fine-grained GitHub PAT (yalnız `Leblepito/efloud-bot`, Contents + Pull requests RW) → VPS'te Hermes secret store'u. Token'ı hiçbir sohbete/dosyaya yapıştırma.
- [ ] Abacus'un git kimliği: laptop credential'ı mı, kendi PAT'i mi? (`MODELS.md`'yi güncelle)
- [ ] Telegram export'unun Drive paylaşım linkini kapat (dosya public link'ten indirildi; private store'un kaynağı hâlâ erişilebilir).
- [ ] VPS'teki export kopyasını kaldır (`ssh efloud-bot rm -r efloud-collab-private/telegram-efloud-2023-2025`) — protokol gereği güvenilmeyen metin prod host'ta durmaz; laptop kopyası asıl kaynak.
- [ ] `~/tradingview-mcp` klonunda pull sonrası kalan stash çakışmasını temizle: `git -C ~/tradingview-mcp checkout HEAD -- package-lock.json scripts/launch_tv_debug.bat` (lokal yama stash'te duruyor; upstream MSIX desteği onu gereksiz kılıyor).
- [ ] `collab/prompts/hermes-onboarding.md` ve `abacus-onboarding.md`'yi ilgili modele yapıştır.
- [ ] (Opsiyonel) Claude'un Google Drive connector'ını bağla.
- [ ] (Opsiyonel) Railway servisinin watch-path'lerini kontrol et — master'a her merge bir rebuild tetikliyor mu?

## Log
- 2026-11-04 claude-code: task açıldı.

## Review
