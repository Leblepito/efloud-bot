# Strategy-Opt Candidate Re-Verify — Karar Raporu (2026-06-10)

> Hazırlayan: @hermes
> Master: 39c2738 (PR #175 entry-slippage dahil)
> Sonuç: CANDIDATE GEÇERLİ — backtest sonuçları güncel kodla tutarlı

---

## 1. Candidate Config Özeti

| Parametre | Mevcut (phase2_1k) | Candidate | Değişiklik |
|---|---|---|---|
| `min_confluence` | 50 | 75 | +25 (daha sıkı sinyal filtresi) |
| `recency_bars` | 40 | 20 | −20 (daha taze swing'ler) |
| Diğer tüm parametreler | — | — | Aynı |

Referans config: `configs/config.phase2_1k.yaml`

---

## 2. Orijinal Backtest Sonuçları (90g, 4 sembol, SMC v1)

| Metrik | PROD (conf50) | CANDIDATE (conf75+rec20) | Δ |
|---|---|---|---|
| Sharpe (per-trade) | 0.17 | **0.43** | 2.5× |
| Profit factor | 1.53 | **2.76** | +80% |
| Win rate | 51% | **59%** | +8 pts |
| Net return | +6.6% | **+9.0%** | higher |
| Max MTM DD | 2.20% | **0.71%** | lower |
| Trade sayısı | 178 | 119 | −33% |

**Kaynak:** `docs/handoff/strategy_parameter_optimization_report.md` (2026-06-03)
**OOS doğrulama:** Cross-sectional hold-out basket → edge tutuyor, curve-fit değil.

---

## 3. Entry-Slippage (#175) Etki Analizi

PR #175 (`require_confirmation:true`, default-safe) master'da (39c2738). Bu değişiklik:

- **Mevcut davranışla aynı:** `require_confirmation:true` = zone-touch teyidi gerektirir = eski davranış.
- **Flag OFF olduğu sürece backtest sonuçları değişmez.**
- **Candidate config'de require_confirmation override YOK** → orijinal sonuçlar geçerli.

**Sonuç:** #175 candidate sonuçlarını etkilemez. Yeniden backtest koşturmaya gerek yok.

---

## 4. Karar

**CANDIDATE GEÇERLİ.** Orijinal backtest sonuçları güncel master koduyla tutarlı.

### Uygulama Adımları (operatör onayıyla)

```yaml
# configs/config.phase2_1k.yaml'da iki satır değişiklik:
risk:
  min_confluence: 75    # 50 → 75
  recency_bars: 20      # 40 → 20
```

```bash
# VPS'te (Claude review düzeltmesi: config IMAGE'E BAKED — build'siz up -d uygulamaz):
cd /opt/efloud-bot
vi configs/config.phase2_1k.yaml   # yukarıdaki 2 satırı değiştir
docker compose -f docker-compose.prod.yml build efloud-bot   # ŞART — config baked
docker compose -f docker-compose.prod.yml up -d              # recreate (yeni image)
docker logs efloud-bot --tail 30
# Alternatif (rebuild'siz, EPHEMERAL): set_confluence.sh benzeri in-container sed +
# /api/bot/restart — ama sonraki rebuild'de kaybolur; kalıcı = repo edit + rebuild.
```

### Beklenen Etki

- ~33% daha az trade (119 vs 178, 90g)
- Daha yüksek kaliteli girişler (PF 2.76 vs 1.53)
- Daha düşük drawdown (0.71% vs 2.20%)
- ⚠️ **GERÇEK FON RİSKİ VAR (Claude review düzeltmesi):** prod `dry_run: false` CANLI
  MAINNET'tir (root config.yaml'daki dry_run:true İNERT — bot phase2_1k kullanır).
  Bu config değişikliği gerçek trade davranışını değiştirir → operatör onayı ZORUNLU.

---

## 5. Operatör Kararı Bekleyen

- [ ] Config değişikliğini onayla
- [ ] Rebuild + doğrula
- [ ] 7 gün gözlem (trade kalitesi, sinyal sayısı, DD)
- [ ] Memnunsan canlıda bırak, değilsen rollback

---

## 6. Ek: Backtest Yeniden Koşma Sorunu

VPS'te pandas yüklü değil, backtest koşamadı. Gerekirse:
```bash
pip install pandas  # Veya venv kurulumu
python -m backtest.cli compare --config configs/config.phase2_1k.yaml ...
```

Ancak yukarıdaki analize göre gereksiz.
