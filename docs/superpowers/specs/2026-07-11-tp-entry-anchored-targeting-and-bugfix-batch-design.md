# TP Entry-Anchored Targeting (v3.2) + Kritik Bugfix Batch — Design Spec

**Tarih:** 2026-07-11
**Operatör talimatı:** Utku — "TP1/TP2 entry'ye mantıklı mesafede, setup'a dayalı olsun; range'de 0.50 (EQ) önem arz ediyor; bulunan tüm bugları sormadan düzelt, baştan sona tamamla." Bu talimat, CLAUDE.md'deki "Python kaynağını değiştirme" kuralını bu oturum kapsamında **operatör onayıyla** geçersiz kılar (kural Pine-port misyonu bağlamındaydı; bu iş botun kendisinin düzeltilmesi talebidir).
**Karpathy sözleşmesi uyumu:** Varsayımlar aşağıda açık; değişiklikler cerrahi; her fix failing-test-önce; davranış değişikliği config-gated (mevcut `smc_tp_targeting` bayrağı — YENİ bayrak eklenmedi).

---

## Bölüm 1 — TP1/TP2 Problemi: Kök Neden

Canlı config (`configs/config.phase2_1k.yaml`, profile **mid** = 15m entry / 4h MTF / 12h HTF, `min_rr: 1.8`, `smc_tp_targeting` YOK → legacy path):

1. **Legacy TP path hedef havuzu SADECE HTF (12h) yapıları**: swing high/low, EQH/EQL, FVG kenarları (`signals.py:732-755`). 15m entry'ye göre 12h yapıları doğal olarak çok uzak.
2. **`>= min_rr × risk` filtresi + üst sınır YOK**: 1.8R'den yakın tüm hedefler elenir; en yakın geçerli 12h hedefi 4-6R uzakta olabilir → TP1 oraya konur (`signals.py:744-755`).
3. **Range EQ (0.50) sadece deviation setup'ında TP1** (`has_dev` dalı, `signals.py:736-745`). Range İÇİ (discount/premium) normal trade'lerde EQ hedef havuzunda değil.
4. **Lifecycle SL→BE sadece TP1 sonrası** (`lifecycle.py:410-414`): TP1 uzak → BE koruması pratikte hiç devreye girmiyor → başta kârlı pozisyon full-SL yiyor. Kullanıcının gözlemlediği davranışın mekanizması birebir bu.
5. Çözüm altyapısı (scalp v3.1 `smc_tp_targeting`: en yakın yapısal blok ≥0.5R = TP1, blended R:R gate) mevcut ve test edilmiş, ama **sadece scalp config'inde açık**; ayrıca blok havuzu yine HTF-only + range ekstremi + level'lar — MTF ve range-EQ yok.

## Bölüm 2 — Tasarım: Entry-Anchored SMC TP (v3.2)

Seçenekler:
- **A) v3.1 `smc_tp_targeting`'i genişlet + mid'de aç (SEÇİLEN).** Var olan, test edilmiş mekanizmayı kullanır; yeni bayrak yok; cerrahi.
- B) Legacy path'e max-R cap ekle — semptomu maskeler, yapısal hedef mantığını iyileştirmez; yeni tunable doğurur.
- C) Yeni TP motoru — over-engineering (Karpathy #2 ihlali).

### Değişiklikler (hepsi `smc_tp_targeting: true` altında; bayrak kapalıyken davranış bit-bit aynı)

**D1. `_collect_smc_blocks` yeni kaynaklar** (`engine/signals.py`):
- **RANGE_EQ**: entry-TF range EQ (0.50), entry doğru taraftaysa (LONG: entry < eq; SHORT: entry > eq) kâr yönü bloğu olarak eklenir. → "Range'de 0.50 önem arz ediyor."
- **MTF likidite**: MTF swing high/low + MTF equal levels (EQH/EQL). Yeni opsiyonel `mtf: Optional[dict]` parametresi; None ise davranış eskisiyle aynı (geriye dönük uyumlu).

**D2. `generate_signals`**: zaten hesaplanan `mtf_sh`/`mtf_sl`'den + `engine.equal_levels()` ile hafif bir MTF dict kurulur (full `analyze()` YOK) ve `smc_tp_targeting` açıkken `_collect_smc_blocks`'a geçilir.

**D3. Config**: `configs/config.phase2_1k.yaml` (canlı) + `config.yaml` (kök):
```yaml
risk:
  smc_tp_targeting: true
  min_rr_tp1: 0.5          # TP1 ilk yapısal blokta, en az 0.5R
  blended_rr_target: 1.5   # 0.5×TP1_R + 0.5×TP2_R >= 1.5
```
`min_rr: 1.8` legacy gate olarak dosyada kalır (targeting açıkken kullanılmaz).

**D4. Korunan invariantlar:** TP1 yanlış-taraf reddi, `_enforce_tp2_beyond_tp1`, blended R:R gate, single-TP modu (tp2=None → lifecycle full close), TP kaynak telemetrisi (`tp1_source`/`tp2_source` — RANGE_EQ/LIQ_MTF etiketleri eklenir).

**Örnek (mid, LONG, range 100–110, entry 102.0, SL 100.7, risk 1.3):**
- Eski: TP1 = en yakın 12h yapısı ≥1.8R (örn. 108.5 → 5.0R) → çoğu zaman vurulamıyor.
- Yeni: EQ=105.0 → 2.3R, ilk geçerli blok → **TP1=105.0 (RANGE_EQ)**; TP2 = range_hi 110.0 (6.2R); blended 4.25 ≥ 1.5 ✓; TP1 vurulunca %50 kapanır + SL→BE.

**Pine senkron notu:** `pine/PINE_SPEC.md`'ye §-not eklenir: RANGE_EQ + MTF-likidite kaynakları Pine `calcTp` zincirine bir sonraki Pine oturumunda porte edilecek (bu spec referans).

## Bölüm 3 — Doğrulanmış Kritik Buglar ve Fixler

4 paralel review ajanı + manuel doğrulama. Sadece kod üzerinde doğrulananlar fixleniyor; geri kalanı Bölüm 4'te.

| # | Yer | Bulgu (doğrulandı) | Fix |
|---|-----|--------------------|-----|
| F1 | `engine/safe_orchestrator.py:933-941` | Leblep gate hiçbir yerde var olmayan root-level `RISK_OPS_APPROVED`/`LEBLEP_*` key'lerini okuyor → **v1 sinyal→emir yolu her deployda ölü** | Gate yalnız `bot_v2.enabled` veya `leblep_enabled` true iken uygulanır; nested `leblep.*` + env override + legacy uppercase fallback okur |
| F2 | `engine/safe_orchestrator.py:2294-2307` | Canlı v2 open `lifecycle`'a YAZILMIYOR → duplicate/exposure/max_open guard'ları v2 pozisyonlarına kör + v2 kapanışları breaker'a rapor edilmiyor (STEP 5 lifecycle üzerinden döner) | v1 pattern'i (satır 1595) aynen: başarılı canlı v2 open sonrası `lifecycle.open_position` mirror |
| F3 | `exchange/__init__.py:1654` | BE-SL taşımada `_retry_tp_order`'ın truthy `"UNREACHABLE"` sentineli gerçek order id gibi saklanıyor → kalan yarım pozisyon **stopsuz** ve repair kalıcı devre dışı | `_is_real_oid` ile ayrıştır; sentinel = fiyat zaten BE'nin gerisinde → kalan pozisyonu market-close (fail-closed) |
| F4 | `exchange/__init__.py:828` | SL_REPAIR aynı sentinel bugı — fiyat SL'yi geçmişken pozisyon korumasız kalıyor | Sentinel = stop koşulu zaten gerçekleşmiş → pozisyonu market-close |
| F5 | `exchange/__init__.py:2126-2137` | `_fallback_close` başarısız market-close'u yutup SL/TP iptal ediyor + tracking düşürüyor → çıplak izlenmeyen pozisyon | Close başarısızsa ABORT: sibling iptali yok, kayıt düşürme yok, False döner |
| F6 | `exchange/__init__.py:2127` | Fallback/manual close her zaman full `pos.size` gönderiyor; TP1 sonrası yarım pozisyonda reduceOnly reddedilir (-2022) → F5 zinciriyle çıplak pozisyon | `tp1_hit` ise kalan miktar (size/2, precision-rounded) gönder |
| F7 | `exchange/__init__.py:1026-1096` | TP1/TP2 miktarları bağımsız truncate ediliyor → step-uyumsuz boyutlarda dust kalıntısı, pozisyon hiç tam kapanmıyor | Önce `size`'ı step-round et, `tp1 = round(size/2)`, `tp2 = size - tp1` |
| F8 | `engine/safe_orchestrator.py:1519-1532` | `pause_new_entries` kontrolü reverse-close'dan SONRA → pause "yalnız yeni giriş" derken mevcut pozisyonu flatten ediyor | Pause kontrolü reverse dalından ÖNCE değerlendirilir |
| F9 | `engine/safe_orchestrator.py:1567` | Exchange open başarısızlığında dedup kaydı kalıyor → sinyal 1h sessizce yutuluyor (reverse yolu 1512'de pop'luyor, open yolu değil) | `exchange_ok=False` dalında `_processed_signals.pop` + persist |
| F10 | `pine/efloud_strategy.pine:598` + `efloud_strategy_v1.pine:503` | `strategy.position_size == 0` reset'i entry emrinin verildiği barda SL/TP state'ini siliyor (fill script sonrası) → pozisyonlar exitsiz | Reset'i open→flat geçişine bağla: `position_size == 0 and position_size[1] != 0` |
| F11 | `backtest/engine.py:165-173` | HTF/MTF/1d dilimleri forming bar'ı final OHLC ile içeriyor → **look-ahead**, backtest sonuçları iyimser | Kapanmamış (open_ts + tf > now) son HTF/MTF/1d barını dilimden düşür |
| F12 | `engine/journal.py:129-140` | Tek bozuk JSONL satırı tüm sonraki trade'leri cache'ten düşürüyor; sonraki `_persist` kalıcı siliyor | Satır-başına try/except + bilinmeyen alanları filtrele |
| F13 | `engine/smc_v2/sl_calc.py:49-64` | NaN `atr_15m` → NaN SL emir yoluna sızıyor | Finite-olmayan ATR'de setup reddi (None dön) |
| F14 | `preflight.py:181` | `dualSidePosition` string `"true"/"false"` normalize edilmiyor → yanlış hedge-mode uyarısı/preflight fail | `str(v).lower() == "true"` |
| F15 | `exchange/__init__.py:2191` + `engine/safety/orphan_protection.py:209` | `reduceOnly` + `positionSide` birlikte → Binance -1106, orphan close/SL her zaman başarısız (hedge modda) | XOR pattern (repo'nun kalanıyla aynı) |
| F16 | `engine/safe_orchestrator.py:1693` | STEP 7 scenario pyramid canlıda exchange emri olmadan `lifecycle.add_to_position` → hayalet boyut | `order_manager is not None` iken pyramid atlanır (log + warn) |
| F17 | `.gitignore` | `.env.production` ignore edilmiyor — secret sızdırma riski | `.env.production` + `.env.*` pattern'i ekle (içerik commit edilmez) |

## Bölüm 4 — Bilinen, Bu Batch'te BİLİNÇLİ Dokunulmayanlar

Review'da bulundu, davranış değişikliği/kapsam gereği ayrı operatör kararı istiyor (`docs/reviews/2026-07-11-full-repo-review-findings.md`'de tam liste):
ölü volatile-tighten-stops gate (SO-6), ölü weakness-momentum dalı (intent.py:199), breaker `record_trade_correction` tail-recompute (default-OFF özellik), OrderManager thread-lock (mimari), lease release try/finally kapsamlı refactor'u (F9 ile kısmen hafifler), backtest slippage/metric kalemleri (BT-4,7,9,10,12,15), dedup fiyat quantize (SO-9), Pine satellite dosya senkronları (publish/v1/wave1), scenario planner pyramid'in exchange-order'lı gerçek implementasyonu.

## Bölüm 5 — Test Stratejisi (TDD)

Her fix önce failing test:
- `tests/engine/test_tp_entry_anchored.py` — RANGE_EQ TP1 (LONG/SHORT), MTF bloğu HTF'den yakınsa seçilir, blended gate korunur, bayrak kapalıyken legacy bit-bit aynı (regresyon), tp2=None single-TP yolu.
- `tests/engine/test_leblep_gate_fix.py` — default config → gate izinli; `bot_v2.enabled`+unapproved → red; approved+limit aşımı → red; env override.
- `tests/engine/test_v2_lifecycle_mirror.py` — canlı v2 open sonrası lifecycle'da pozisyon var; guard duplicate'i görüyor.
- `tests/test_sentinel_sl_close.py` — BE-SL/SL_REPAIR sentinel → market-close çağrısı; `_fallback_close` başarısızlıkta tracking korunur; TP1 sonrası kalan-miktar close; TP dust split.
- `tests/engine/test_orchestrator_flow_fixes.py` — pause reverse'ten önce; open-fail dedup pop.
- `tests/test_journal_robust_load.py`, `tests/engine/test_sl_calc_nan.py`, `tests/test_preflight_dualside.py` — F12/F13/F14.
- F10 (Pine) TradingView derleyicisi olmadan test edilemez → kod fix + PINE_SPEC changelog notu; F11 için mevcut backtest testlerine forming-bar testi eklenir.

## Bölüm 6 — Rollout

1. Commit'ler mantıksal parçalar halinde master'a (repo pratiği), origin'e push.
2. Canlı etki `configs/config.phase2_1k.yaml` + kod → **VPS container recreate gerektirir** (`docker compose up -d`): operatör (Utku) aksiyonu.
3. Backtest gate: F11 fixi sonrası mevcut cache verisiyle mid-profil smoke backtest koşulur (yeni TP mantığı sinyal üretmeye devam ediyor mu + hiçbir crash yok). NET-cost tam edge ölçümü ayrı oturum (Bölüm 4 kapsam notu).
