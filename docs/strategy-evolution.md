# Strategy Evolution — efloud-bot config history

Üç ana yapılandırma evrimi: `phase2_1k` (ilk live) → `H2-A2` (Faz 2 magnitude) →
`aggressive_v1` (current, daily-action focus). Her aşama Phase A backtest verisiyle
desteklendi; H2-A2 ve aggressive_v1 production'a deploy edildi.

---

## Side-by-side comparison (deploy edilen tüm configler)

| Parametre | **phase2_1k** (initial baseline) | **H2-A2** (deployed 2026-05-05) | **aggressive_v1** (deployed 2026-05-08, **current**) |
|---|---|---|---|
| **Strategy** | Conservative entry-level | Quality-first magnitude push | Daily-action focused, tier-based |
| `min_confluence` (global) | 50 | 80 | **70** (with per-symbol overrides) |
| `symbol_confluence_overrides` | — (yoktu) | — (yoktu) | **6 sym** (5 mid@80, 1 selective@85) |
| `risk_per_trade_pct` | 1.0% | **2.0%** | 2.0% |
| `max_open_positions` | 10 (declared, **gate yoktu**) | 10 (declared, **gate yoktu**) | **5 (gate ENFORCED**, commit 20c6ccd) |
| `max_position_notional_pct` | 2.0% | 6.0% | **10.0%** |
| `leverage` | 5x | 5x | 5x |
| `margin_mode` | ISOLATED | ISOLATED | ISOLATED |
| `daily_loss_limit_pct` | 10.0% | 10.0% | 10.0% |
| `weekly_drawdown_limit_pct` | 15.0% | 15.0% | 15.0% |
| `emergency_balance_threshold` | $1800 (90%) | $1800 (90%) | **$1700 (85%)** |
| **Universe size** | 10 sym (BTC, ETH, XRP, DOGE, SOL, BNB, TRX, LINK, BCH, ADA) | 10 sym (same as baseline) | **10 sym (curated):** ETH, SOL, FIL, RENDER, SUI, ADA, OP, LTC, BTC, XRP |
| **Per-trade notional max** ($2k wallet × pct × 5x) | $200 | $600 | **$1,000** |
| **Total parallel exposure** ($2k × max_pos × notional × 5x) | $2k (theoretical 10×$200) | $2k (theoretical 10×$600 capped by max_total_exposure 1.0) | $5k (5×$1k = max_total_exposure'a bağlı) |

---

## Backtest validation (365-day Phase A on $2000 wallet)

### Confluence sweep — H1 sweep family (Epic 6, on phase2_1k base, no override, all 10 sym)

| Variant | Trades | Win % | Return % | Max DD % | PF | Karar |
|---|---:|---:|---:|---:|---:|---|
| H1a (conf=60) | 1361 | 45.5% | **-34.32%** | 34.64% | 1.31 | ❌ Çok gevşek, DD katastrofik |
| H1b (conf=70) | 680 | 54.7% | +4.89% | 7.17% | 1.95 | ⚠️ Borderline, marjinal kar |
| **H1c (conf=80)** | 213 | **62.4%** | **+11.29%** | **2.83%** | **3.50** | ✅ **Yeni baseline — sweet spot** |

**Bulgu:** confluence 60→80 arasında DD 12x düştü (34% → 2.8%), PF 2.7x arttı.
conf=80 quality threshold sweet-spot olarak kanıtlandı.

### Magnitude push — H2 family (on H1c base)

| Variant | Trades | Win % | Return % | Max DD % | PF | Karar |
|---|---:|---:|---:|---:|---:|---|
| H1c baseline | 213 | 62.4% | +11.29% | 2.83% | 3.50 | OK |
| **H2-A2** (conf=80 + risk 2% + notional 6%) | 206 | **65.0%** | **+42.48%** | 5.47% | **3.64** | ✅ **Production'a promote (2026-05-05)** |

**Bulgu:** Aynı sinyal kalitesinde (conf=80) per-trade büyüklüğünü 2x risk + 3x
notional yapmak return'ü 4x çıkardı, DD'yi sadece 2x büyüttü. Magnitude
problem solved.

### Daily-action push — aggressive_v1 (Phase A 2.0)

21-coin candidate universe → 9-sym tier-ranked, sonra user XRP'yi geri ekleyince 10.

**Step 3 (raw 21-sym, conf=70 floor, no overrides) — sadece scouting:**
- Per-sym data toplandı (8 pozitif, 13 negatif), 1267 toplam trade
- Portfolio mode HALTED on weekly DD 15.1% (12 zayıf coin balance'ı çekti)

**Step 5 (tuned 10-sym, current production):**

| Variant | Trades | Win % | Return % | Max DD % | PF | Karar |
|---|---:|---:|---:|---:|---:|---|
| H2-A2 (önceki prod) | 206 | 65.0% | +42.48% | 5.47% | 3.64 | (baseline) |
| **aggressive_v1** (current prod) | **364** | 58.0% | **+49.12%** | **11.49%** | 2.44 | ✅ **Production (2026-05-08)** |

**Bulgu:**
- Trade volume **+77%** (206 → 364, daily action hedef tutturuldu)
- Return **+6.64 pp** (42.48 → 49.12)
- DD **+6.02 pp** (5.47 → 11.49) — "kaliteden ölçülü kayıp" kabul edilen trade-off
- Sharpe-like 0.53 → 0.38 (risk-adjusted return düştü ama mutlak return arttı)

---

## Per-symbol performance under aggressive_v1 (Step 5 final)

```
Top tier (conf=70 default):
  ETH/USDT     +20.47%  DD 5.79%   PF 2.74   89 trades
  SOL/USDT     +22.76%  DD 6.74%   PF 3.41   76 trades
  FIL/USDT     +6.77%   DD 11.49%  PF 2.78   64 trades
  RENDER/USDT  +11.34%  DD 9.83%   PF 3.54   67 trades

Mid tier (conf=80 override):
  SUI/USDT     +12.40%  DD 4.90%   PF 3.46   27 trades
  ADA/USDT     -0.44%   DD 3.99%   PF 17.9    8 trades
  OP/USDT      -0.68%   DD 7.73%   PF 1.71   16 trades
  LTC/USDT     +1.49%   DD 3.74%   PF 1.37   17 trades
  BTC/USDT     +5.60%   DD 1.81%   PF 3.97   24 trades

Selective tier (conf=85 override, user-requested re-add):
  XRP/USDT     -6.63% (Phase A 2.0 conf=70 perf — selective threshold mitigates)

Dropped (12 sym, all negative @ conf=70 in Phase A 2.0):
  TRX, BNB, AVAX, DOGE, LINK, APT, NEAR, DOT, BCH, ATOM, ARB
```

---

## Engine-level changes shipped with aggressive_v1

Aggressive_v1 sadece config değişikliği değil — engine'de iki gate eklendi:

1. **`max_open_positions` enforcement** (commit `20c6ccd`)
   - Önceden config'te declared ama hiçbir yerde enforce edilmiyordu
   - PositionGuard'a yeni gate (`open_count >= max → reject`)
   - Tests: 6 unit case
   - Etki: bu olmadan max=5 ayarı meaningless olurdu

2. **Per-symbol confluence override** (commit `0019170`)
   - `min_confluence` artık per-symbol lookup yapabiliyor
   - `resolve_min_confluence(symbol, global_min, overrides)` helper
   - Tests: 7 unit case (normalize, fallback, edge cases)
   - Etki: aggressive_v1'in tier sistemini mümkün kıldı

Bu engine değişiklikleri **back-compat** — eski H2-A2 config (override yok, max
declared'a güvenir) hâlâ çalışır. Yeni gate'ler sadece config'te tanımlı olduğunda
aktive olur.

---

## Live deployment timeline

| Tarih | Commit | Action |
|---|---|---|
| ~2026-04-30 | (initial) | İlk Hetzner deploy: `phase2_1k` baseline |
| 2026-05-05 | `26c810c` | H2-A2 promotion to master (conf=80, risk 2%, notional 6%) |
| 2026-05-05 | (deploy) | H2-A2 production'a deploy |
| 2026-05-07 | `20c6ccd` | `max_open_positions` enforcement gate |
| 2026-05-07 | `0019170` | Per-symbol confluence override |
| 2026-05-07 | `109a459` → `2634833` | aggressive_v1 config (21→9 tier-ranked) |
| **2026-05-08** | **`726b668` (PR #4)** | **aggressive_v1 production'a deploy** |
| 2026-05-08 | `7a06a20` (PR #5) | XRP @ conf=85 re-add → 10 sym universe |

---

## Beklenen davranış (aggressive_v1 production'da)

- **Trade frequency:** ~1 trade/gün (H2-A2'de ~0.56/gün, %77 artış)
- **Telegram alert:** günde 0-2 `📈 Trade opened` (özellikle ETH/SOL)
- **Daily email:** her sabah 08:00 UTC (09:00 SEAST) günlük özet mailı
- **Win rate:** ~58% (H2-A2: 65%, biraz düştü)
- **Aylık return projeksiyonu:** ~+4% (annualized +49% / 12)
- **Max DD beklenti:** günlük rare 5-8%, weekly worst-case 11-12% (15% halt'tan altında)
- **30-day decision points:**
  - XRP yeterli kalitede signal üretti mi (≥5 win)? → conf=80'e çek veya tut
  - Mid tier ADA/OP marjinal-negatif kaldı mı? → drop'ı düşün
  - Top 4 (ETH/SOL/FIL/RENDER) yeniden +50% yıllık ekledi mi? → korumalı

---

## Rollback path (aggressive_v1 → H2-A2)

Eğer aggressive_v1 production'da yeterli performans göstermezse:

```bash
ssh efloud@<VPS_IP> "cd /opt/efloud-bot && \
  cp .env.production.h2a2.bak .env.production && \
  bash deploy/deploy.sh"
```

~5 dakika içinde önceki H2-A2 config'e dönüş (engine değişiklikleri back-compat,
config swap yeterli).

---

## Reports & validation artifacts

- **H1 sweep:** `docs/results/2026-05-06-phase-A-validation-phase2_1k_h1a_conf60.md`
  ve `_h1b_conf70.md`, `_h1c_conf80.md` (backtest worktree)
- **H2-A2 magnitude:** `docs/results/2026-05-06-phase-A-validation-phase2_1k_h2a2_risk2_notional6.md`
- **aggressive_v1 raw 21-sym:** `reports/backtests/phase_a_2026-05-07_aggressive_v1_1fdea2/` (per-sym JSONs)
- **aggressive_v1 final 10-sym:** `docs/results/2026-05-07-aggressive-v1-final.md` (consolidated)
- **Spec docs:** `docs/superpowers/specs/2026-05-06-h2-magnitude-design.md`,
  `2026-05-07-h2-a2-magnitude-results.md`
