# 🟧 Hermes — T-003 ROUND-5 Görev Prompt'u (2026-06-13)

> Hazırlayan: Claude (Architect/Review). Bitince Claude review + GATE_RUN_3'ü
> (compile + 5-sembol backtest) koşacak. Kurallar: feature-branch + PR, atomic,
> append-only/claim (`git add -A` YASAK), secrets sadece VPS, destructive-op yok.
> Transfer: **git push** (format-patch + sha256 yalnız push mümkün değilse, beyan=gelen
> sha doğrula). Branch: **`feat/p001-t003-strategy`** (PR #194, DRAFT — merge edilmedi).

---

## BAĞLAM — GATE_RUN_2 ❌ FAIL (neden buradayız)

GATE_RUN_2 (2026-06-13, Claude TV-MCP, 5 perp 15m, `allow_ob_less=true`) koştu.
Rapor: **`LLTODO/reports/REPORT-T-003-gate-run-2.md`** (commit `72e9755`). Özet:

| Gate | Sonuç |
|---|---|
| G-T3 compile · G-T4a count=168 · G-T5 inverted=0 · G-T6 subRR=0 · MaxDD≤%2.6 | ✅ PASS |
| WR ≥ %50 | ❌ ~%10-15 (sadece ETH %66.7) |
| PF ≥ 1.5 | ❌ agg 1.44 (XRP PF 0.38, net −%2.0 kaybeden) |
| **Limit-fill (F-01)** | ❌ **~%41, 9-60 değişken** (ETH %9 → sinyallerin >%59'u expire) |
| G-T4b OOS-Sharpe ≥ IS×0.7 | ⬜ **DEĞERLENDİRİLEMEZ** (`bt_oos_pct` ÖLÜ input) |

R1+R3 gevşetmesi trade'i 0→168 yaptı ama **OB-kenarı limit entry sinyallerin yarıdan
fazlasını ıskalıyor** + edge marjinal. Plan §6 kaçış maddesi + gate prompt kuralı
("fill düşükse FAIL → round-5") devrede.

---

## GÖREV (TOP SENDE) — ROUND-5: 3 değişiklik

### 1️⃣ R3 GERÇEK MARKET-ENTRY (çekirdek — F-01 BLOCKING çözümü)

Limit-at-OB entry **kaldırılıyor**, yerine **sinyal barı kapanışında market entry**:

- `strategy.entry(..., limit=sig_entry_*, ...)` → **`limit=` parametresini KALDIR** (market emri).
- `strategy()` header'a **`process_orders_on_close=true`** ekle → emir sinyal barının
  KAPANIŞINDA fill olur (deterministik; F4 intrabar-fill iyimserliğini de yok eder).
- **Entry fiyatı artık `close`** (OB seviyesi `bullish_ob_bot`/`bearish_ob_top` DEĞİL).
  Dolayısıyla **SL/TP'yi yeni entry fiyatıyla yeniden hesapla:**
  `f_calc_sl(dir, close)` ve `f_calc_tp(dir, close, sl)`. `valid` kontrolü
  (sl<entry<tp1) ve `min_rr` clamp aynen korunur.
- **OB confluence faktörü olarak KALIR** (+30, `allow_ob_less` mantığı değişmez) —
  sadece artık entry FİYATI değil. (R1'in orijinal niyeti: "OB faktör, zorunlu değil").
- Market entry → fill ≈ %100 olacağından **`limit_expiry_bars` / `extended_expiry_in_trend`
  ve F5/F6 pending-cancel mantığı entry için anlamsızlaşır** — sadeleştir/kaldır.
  `is_in_trade` gate'i (pyramiding önleme) KORUNUR. `pyramiding=1` kalır.

> ⚠️ Bu strateji karakterini değiştirir (retrace-bekleme yerine sinyalde market giriş).
> WR/PF'in market fiyatında hayatta kalıp kalmadığını GATE_RUN_3 ölçecek. Beklenen:
> trade sayısı ↑ (fill ~%100), edge ? — kanıt gate'i belirleyecek.

### 2️⃣ DEFEKT FIX — `bt_date_end` default (LATENT BUG, HIGH)

`bt_date_end = input.time(timestamp("2025-12-31"), ...)` → TV 15m derinliği 2026
olduğundan `in_window` TÜM bar'ları dışlıyor → **yayınlanan strateji her kullanıcıda
0 trade**. Düzelt: çalışır default. Öneri: `bt_date_start` default `timestamp("2020-01-01")`,
`bt_date_end` default `timestamp("2035-01-01")` (= "tüm yüklü veri"; operatör OOS için daraltır).
WAVE1_SPEC'e "default = tüm veri, OOS için operatör daraltır" notu.

### 3️⃣ DEFEKT FIX — `bt_oos_pct` ÖLÜ input → OOS-split implement (G-T4b'yi gerçek kıl)

`bt_oos_pct` şu an sadece yorumda; kodda IS/OOS bölme YOK → OOS-Sharpe gate'i ölçülemiyor.
Canlı kıl: **`bt_segment` input'u ekle** = `input.string("Full", options=["Full","IS","OOS"])`.
`last_bar_index` + `bt_oos_pct` ile bölme:
```
oos_start_idx = last_bar_index - int(last_bar_index * bt_oos_pct / 100)
seg_ok = bt_segment == "Full" ? true : bt_segment == "OOS" ? (bar_index >= oos_start_idx) : (bar_index < oos_start_idx)
```
`seg_ok`'ı entry gate'ine `in_window` ile birlikte AND'le. Böylece Claude aynı kodu
`IS` ve `OOS` segment'leriyle 2 kez koşup Sharpe karşılaştırabilir (G-T4b: OOS ≥ IS×0.7).
(`last_bar_index` Pine'da tüm bar'larda bilinir — repaint yok.)

---

## ⚠️ KRİTİK KURALLAR

1. **SENKRON (Plan v1.4 §8a.3):** Değişen INPUT isimleri/default'ları 3 dosyada birlikte:
   `wave1_strategy.pine` + `wave1_signals.pine` (indicator) + `WAVE1_SPEC.md`.
   - `bt_*` ve `bt_segment` **strategy-only** (indicator'da backtest yok) → indicator'a EKLEME.
   - Indicator'ın SİNYAL mantığı DEĞİŞMEZ; sadece varsa "entry" görsel etiketini
     yeni market-entry konvansiyonuna (entry ≈ sinyal barı close) hizala.
2. **PATH:** Wave-1 SADECE `pine/u2algo/`. `pine/efloud_signals.pine`,
   `pine/efloud_strategy.pine`, `pine/PINE_SPEC.md` = SMC v2 sadık portu — **DOKUNMA**.
3. **Pine v6 — derleyemiyorsun (VPS'te TV yok), defansif yaz** (G-T2/T-003'te yakalanan dersler):
   - Satır devamı `\` YOK ("no viable alternative at character '\'"). Girintili sar.
   - `x = na` YASAK → `float x = na` / `int x = na` (tip zorunlu).
   - Tuple dönüşü destructuring: `[a, b] = f()` (strategy'de `f()[0]` "operator SQBR" verir).
   - `line.new` named-arg zorunlu (`color=`/`width=`/`style=`).
4. **Repaint:** yalnız `barstate.isconfirmed`/`[1]`; `request.security` →
   `lookahead=barmerge.lookahead_off`; 1h pivot için mevcut gecikmeli-pivot kalıbı.
5. **Strategy ayarları:** `commission_value=0.04` + `slippage=2` + `calc_on_every_tick=false`
   + `process_orders_on_close=true` (yeni) korunur. `risk_pct=0.5%` risk-bazlı sizing korunur.

---

## GATE'LER (Claude koşacak — GATE_RUN_3, TV MCP lokalde)

- **G-T3 compile:** `pine_smart_compile` + `pine_get_errors` → 0 hata 0 marker.
- **G-T4a:** trade_count ≥ 100 (5-sembol agg). **G-T4b:** OOS Sharpe ≥ IS×0.7 (artık
  `bt_segment` ile ölçülebilir). **G-T5:** inverted=0. **G-T6:** sub-RR=0.
- **WR ≥ %50 · PF ≥ 1.5 · MaxDD ≤ %5.** Fill artık ~%100 (market) → F-01 yapısal çözülür;
  asıl soru market-fiyatında EDGE'in hayatta kalması.
- Semboller: BTC/ETH/SOL/BNB/XRP perp 15m. Claude metrikleri diagnostik-table tekniğiyle çeker.

**Acceptance:** kart checkbox'ları + LLTODO lint 8/8 + WAVE1_SPEC §7 round-5 revizyonu
(+ §8 revizyon geçmişi satırı) + PR #194 güncel. → GATE_RUN_3 PASS → IMPL_READY → FAZ 4 UR-001.

**Ref:** `LLTODO/reports/REPORT-T-003-gate-run-2.md`,
`LLTODO/tasks/IN_PROGRESS/T-003-strategy-backtest.md`,
`LLTODO/plans/P-001-*.md` (v1.4 §8a — round-5 için §6 kaçış maddesi konsensüsü gerekebilir),
`pine/u2algo/wave1_strategy.pine` (`533e225` committed) + `wave1_signals.pine` + `WAVE1_SPEC.md`.
