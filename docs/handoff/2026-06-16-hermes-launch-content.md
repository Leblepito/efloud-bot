# 🟧 Hermes — Görev: Launch Content — premium.html promo + T-019 müşteri docs — 2026-06-16

> Hazırlayan: Claude. Bitince Claude review eder.
> Kurallar: canlı mainnet bot → feature-branch + PR, atomic, secrets repo'ya ASLA. **G-P3-5 dokunulmaz** (bot config/compose/.env). Bu görev YALNIZ `u2algo-site/` + `LLTODO/`'a dokunur.
> Transfer: `git format-patch origin/master --stdout > /tmp/<ad>.patch` + sha256 → Claude scp+am+review.

## 0. Bağlam
Track 1 launch CANLI: `u2algo-site/premium.html` (Wave-1 indikatör, **araç-konumlandırma, getiri iddiası YOK**), founding $39 lifetime, dürüst transparency. LS webhook + entitlements + consent canlı. Konumlandırma **B+C**: araç-değeri + dürüst build-in-public. ⚠️ premium.html'i smoke compliance gate koruyor (`u2algo-site/scripts/smoke.js`) — zorunlu disclaimer token'ları + forbidden-phrase + proof JSON. Gate'i YEŞİL tut.

## GÖREV 1 — premium.html promo metni rafine (compliance KORUNUR)
Mevcut premium.html ilk-draft Türkçe metin içeriyor. Hero / "ne-ne değil" / metodoloji / SSS bölümlerini **satışı güçlendir ama getiri iddiası ASLA ekleme**:
- Net değer önermesi: SMC yapısal analizini (OB/FVG/EQH-EQL/CHoCH-BOS/confluence/SL-TP) otomatik işaretleyerek manuel analizi hızlandırır.
- Disclaimer token'ları AYNEN kalmalı: "yatırım tavsiyesi değildir", "getiri garantisi yoktur", "geçmiş performans gelecek garantisi değildir".
- `node scripts/smoke.js` → `premium.html compliance gate passed` + `smoke OK` (regresyon yok).

## GÖREV 2 — T-019: Müşteri docs (quickstart + FAQ)
Satın alan müşteri için: `u2algo-site/quickstart.html` (veya premium.html'e bölüm) — (a) satın alma sonrası TV invite-only erişimi nasıl alır (T-017 akışı: order → entitlement → manuel grant → TV davet kabul); (b) indikatörü TV'de nasıl ekler/kullanır; (c) FAQ (erişim, iade [terms'e link], "sinyal servisi mi?" = hayır, vb.). Footer'a + sitemap'e ekle. Compliance dili korunur.

## GÖREV 3 (zaman varsa) — tv-access-grant runbook operasyonel cila
`docs/runbooks/tv-access-grant.md`'i operatörün gerçek adımlarıyla (LS order kuyruğu → `scripts/list_pending_entitlements.py` → TV UI invite → entitlement granted) netleştir.

## Acceptance
premium.html promo rafine + smoke YEŞİL · quickstart/FAQ eklendi (compliance'lı) · sitemap güncel · bot'a dokunulmadı (G-P3-5). → Claude review.
