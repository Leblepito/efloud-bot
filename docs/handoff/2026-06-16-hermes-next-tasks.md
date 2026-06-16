# 🟧 Hermes — Sıradaki Görev: T-010 Legal Sayfaları Tamamlama (2026-06-16)

> Hazırlayan: Claude (backend orchestrator). Bitince Claude review eder.
> Kurallar: canlı mainnet bot → feature-branch + PR, atomic, secrets sadece VPS/Railway env
> (repo'ya ASLA), destructive-op yok. **G-P3-5 dokunulmaz:** bot config/compose/.env/EFLOUD_*.
> Bu görev YALNIZ `u2algo-site/`'a dokunur.
> **Transfer:** `git format-patch origin/master --stdout > /tmp/<ad>.patch` + sha256 →
> operatör scp ile Claude'a iletir → Claude `git am` → review → PR → merge.

## 0. Durum
master = `e303e49`. Sprint #2 (#204) ile T-011 consent + **`u2algo-site/privacy.html` (KVKK
aydınlatma) CANLI**. T-016 webhook INERT (B.1-B.4 bekliyor). Sıra **T-010 legal sayfa
tamamlama** — indicator-as-premium satışı için legal yüzey eksiksiz olmalı.

## GÖREV — T-010: Terms + Footer + Sitemap (W0, ungated, atomic)

privacy.html zaten var; eksik legal parçaları tamamla. **Premium ürün = INDICATOR** (TV
invite-only karar-destek aracı); satılan şey strateji değil, getiri vaadi YOK, yatırım tavsiyesi
DEĞİL — terms bu çerçeveyi netleştirmeli.

1. **`u2algo-site/terms.html`** (Kullanım Koşulları / Terms of Service) — privacy.html ile aynı
   self-contained dark-theme stil (Inter/Outfit, `--accent:#00f0ff`, `hello@u2algo.com`). Bölümler:
   - Hizmet tanımı: u2algo bir **araştırma/karar-destek indicator'ı** sağlar; TradingView
     invite-only erişim. **Yatırım/finansal tavsiye DEĞİL; getiri garantisi YOK.**
   - Lisans: kişisel, devredilemez, tek kullanıcı; indicator'ı kopyalama/yeniden dağıtma/decompile
     yasak (IP koruması). Erişim ihlalinde iptal.
   - Ödeme & erişim: satın alma sonrası TV invite-grant (manuel kuyruk — T-017 runbook). İade
     politikası: dijital ürün/erişim verildikten sonra LS politikasına göre (B.1 kararıyla
     netleşecek — şimdilik "satın alma öncesi proof inceleyin" + LS standart 14-gün notu placeholder).
   - Sorumluluk reddi: trading risklidir, kullanıcı kendi kararından sorumlu; max sorumluluk =
     ödenen ücret.
   - Yürürlük tarihi + güncelleme notu (privacy.html ile aynı kalıp).
2. **`u2algo-site/index.html` footer** — privacy.html + terms.html linklerini ekle (mevcut footer
   bloğuna; consent checkbox zaten privacy.html'e linkli). Footer'da: Privacy · Terms · hello@u2algo.com.
3. **`u2algo-site/sitemap.xml`** + (yoksa) **`robots.txt`** — `/`, `/privacy.html`, `/terms.html`
   listele; robots.txt sitemap'i refere etsin. index.html `<head>`'e `<link rel="sitemap">` opsiyonel.

## Sağlık & Acceptance
- ✅ terms.html + footer linkleri render eder, 404 yok (privacy.html linki zaten çalışıyor).
- ✅ sitemap.xml geçerli XML; robots.txt sitemap'i gösterir.
- ✅ Bot config/compose/.env'e **dokunulmadı** (G-P3-5); yalnız `u2algo-site/`.
- ✅ Legal metinler "yatırım tavsiyesi değil + getiri garantisi yok" disclaimer'ını net taşır.
- Çıktı: format-patch + sha256 → "review" sinyali. **Hukuki metin operatör tarafından rafine
  edilecek** — sen standart/forward-compatible taslağı kur (privacy.html emsali).

> NOT: B.1-B.4 (LS AUP/payout/legal-entity/domain) iade & ödeme detaylarını netleştirecek →
> terms'teki iade/ödeme bölümünü placeholder + "B.1 sonrası finalize" notuyla bırak, CANLI satış
> açmadan operatör onayı şart.
