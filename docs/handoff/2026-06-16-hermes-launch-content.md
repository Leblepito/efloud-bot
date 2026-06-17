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

## 🆕 GÜNCELLEME 2026-06-16 (Claude — v1.3.0 görsel polish sonrası)

İndikatör **v1.3.0 görsel polish** tamamlandı (PR #216, `wave1_signals.pine`) ve premium screenshot'ları üretildi. Bu, GÖREV 1'i etkiler:

### A) Gallery zaten gerçek görsellerle bağlandı (Claude yaptı)
`premium.html` §3 ("Grafik üzerinde nasıl görünüyor?") artık **gerçek v1.3.0 screenshot'larına** işaret ediyor (eski kırık `ornek-1/2/3.png` placeholder'ları değişti):
- `/assets/premium/wave1_eth_short_15m.png` — ETHUSDT 15m SHORT setup
- `/assets/premium/wave1_btc_short_15m.png` — BTCUSDT 15m SHORT setup
- ⏳ **LONG örneği EKSİK** (major'lar şu an bearish) → Claude/TV-MCP follow-up çekecek; eklenince 3. figure açılır. Hermes bu dosyayı ÜRETEMEZ (TV gerekli).

### B) ⚠️ ACCURACY/COMPLIANCE — "CHoCH/BOS" iddiası SHIPPED özelliklerle UYUŞMUYOR
GÖREV 1 değer-önermesi + `premium.html` metodoloji §"CHoCH / BOS" + (eski) caption "CHoCH/BOS yapı kırılımı" → indikatörün **CHoCH/BOS çizdiğini** ima ediyor. **Ama v1.3.0 indikatörü CHoCH/BOS ETİKETİ ÇİZMİYOR.** Gerçek SHIPPED detektör/çizim seti:
- **OB (Order Block)** demand/supply zone'ları · **FVG** zone'ları · **EQH/EQL** likidite · **Breaker (BB)** flip işaretleri · **Swing HH/LL** · **Confluence skoru** · **SL/TP/Entry + R:R** + **1H bias** info-panel.
- "Breaker" yapısal-kırılım sinyalidir ama **CHoCH/BOS olarak etiketlenmez**.

**Yapılacak:** Ücretli sayfada olmayan özelliği iddia etmek transparency/compliance riski. Metodoloji §"CHoCH/BOS"'u ya (i) gerçeğe uygun **"Breaker Block (yapı kırılımı sinyali)"** olarak yeniden yaz, ya da (ii) açıkça **"roadmap / yakında"** olarak işaretle. Değer-önermesi bullet'ını da SHIPPED set'e hizala (yukarıdaki A-B listesi). Getiri iddiası YOK kuralı aynen.

### C) Acceptance'a ek
- premium.html §3 gallery gerçek görsellerle çalışıyor (kırık link YOK) ✓ (Claude)
- Metodoloji + değer-önermesi SHIPPED feature-set ile tutarlı (CHoCH/BOS reconcile) — **Hermes**
- `node scripts/smoke.js` YEŞİL (disclaimer token'ları korunur)

## Acceptance
premium.html promo rafine + smoke YEŞİL · quickstart/FAQ eklendi (compliance'lı) · sitemap güncel · **metodoloji SHIPPED-feature uyumlu (CHoCH/BOS reconcile)** · bot'a dokunulmadı (G-P3-5). → Claude review.
