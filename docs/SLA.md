# u2algo — Hizmet Seviyesi Taahhütleri (SLA) ve İç Operasyon Hedefleri

> **T-022 / P-003 W-R** · Sürüm: v1 DRAFT (2026-06-11)
> **Statü: G-P3-B2 operatör sign-off paketi** — fiyatlandırma + refund policy ile birlikte
> yayından ÖNCE operatör onayı zorunlu. Onaylanana kadar hiçbir taahhüt müşteriye sunulmaz.

## 0. Kritik çerçeve: ne satılıyor, ne taahhüt ediliyor

Satılan ürün **TradingView strategy script erişimidir** (P-003 W2). Trading botunun kendisi
satılmaz; bot performansı yalnız **şeffaflık metriği** olarak yayınlanır (proof sayfası,
G-P3-B4). Bu yüzden SLA iki ayrı katmandır ve **karıştırılmaz**:

1. **§1 Müşteri taahhütleri** — sözleşmesel: destek, site, script bakımı.
2. **§2 İç operasyon hedefleri** — sözleşmesel DEĞİL: botun uptime/RPO/RTO hedefleri.
   Proof sayfasında "hedef" olarak yayınlanabilir; garanti dili KULLANILMAZ (G-P3-B1).

## 1. Müşteri Taahhütleri (sözleşmesel — operatör onayıyla yayınlanır)

| Taahhüt | Hedef | Ölçüm |
|---|---|---|
| Destek ilk yanıt | ≤ 2 iş günü | Destek kanalı (T-019) zaman damgası |
| Satın alma → TV erişim daveti | ≤ 2 iş günü (manuel grant — T-017) | entitlements `granted_at - created_at` |
| u2algo-site erişilebilirliği | %99 aylık (Railway altyapı sınırları dahilinde) | T-021 uptime monitörü |
| TV script bakımı | TradingView Pine sürüm kırılımlarında düzeltme: ≤ 10 iş günü | issue → fix yayını |
| Refund | Refund policy'ye göre (W0 T-010; LS üzerinden) | LS işlem kaydı |

**Kapsam dışı (müşteriye açıkça yazılır — T-010 legal pack):** trading sonuçları/performans
(yatırım tavsiyesi değildir); TradingView platform kesintileri; Binance/exchange kesintileri;
müşterinin kendi TV hesap/plan sorunları; force majeure.

## 2. İç Operasyon Hedefleri (sözleşmesel DEĞİL — ops disiplini + şeffaflık)

| Metrik | Hedef | Kaynak/Mekanizma |
|---|---|---|
| Bot service-uptime (`service_uptime_pct`) | ≥ %99 / 30g | healthz sampling (T-012/T-024; `suspended` = up sayılır) |
| Trading-active oranı (`trading_active_pct`) | hedef YOK — güvenlik sistemi gerektiğinde durdurur; "suspension" üründür, hata değil | healthz `ok` oranı |
| Veri kaybı penceresi (RPO) | ≤ 24 saat | günlük şifreli backup (T-020) |
| State restore süresi (RTO) | ≤ 1 saat | restore drill ile doğrulanır (G-P3-6) |
| VPS total-loss kurtarma | ≤ 1 iş günü | `docs/runbooks/disaster-recovery.md` Senaryo 2 |
| Olay tespiti | ≤ 5 dk (alerter 30s healthz poll + log tail) | ops/alerter → Telegram |

## 3. Bakım Pencereleri

- Planlı bakım: duyurulu, tercihen düşük-volatilite saatleri; bot `dry_run`/stop ile değil
  **breaker/operatör akışıyla** durdurulur (canlı pozisyon varken deploy yok —
  `feedback: deploy caution` kuralı).
- Plansız müdahale: on-call playbook'a göre (P1/P2/P3 — `docs/runbooks/on-call-playbook.md`).

## 4. Gözden Geçirme

- Bu doküman üç ayda bir (DR tatbikatıyla birlikte) gözden geçirilir.
- Müşteri taahhütlerinde değişiklik = yeni operatör sign-off (G-P3-B2) + site güncellemesi.

## Revizyon

| Tarih | Not | Yazar |
|---|---|---|
| 2026-06-11 | v1 DRAFT — G-P3-B2 paketi için hazırlandı | @claude |
