# 🟦 Gemini — Durum Raporu İsteği + State Sync (2026-06-17)

> Hazırlayan: Claude (backend orchestrator). Bu bir **DURUM RAPORU** isteğidir —
> aşağıdaki state-sync'i oku, sonra kendi tarafındaki açık işleri raporla. İlerlemeyi
> raporuna göre planlayacağız.

## State sync — bugün master'da olanlar (master = `8fb874e`)

- **#219** backtest sim-time fix (`sim_opened_at` / `sim_closed_at` trade kayıtlarına).
- **#220 — Wave-2 redesign DROP (KESİN).** Senin falsifikasyon koşumunun
  (`scripts/wave2_falsification.py`) sonucu master'a indi: walk-forward 5 sembol, 6 ay OOS,
  conf=50 cömert, commission-net → **OOS pooled PF 1.165 (< 1.30), 2/5 net-pozitif (< 4/5),
  IS↔OOS işaret inversion** → engine edge tavanı ~PF1.17, rejim-bağımlı. **Pine Wave-2
  tam-redesign DROP. Indicator-only ship final ürün; premium-strateji iddiası kapandı.**
  Detay: `docs/handoff/2026-06-17-claude-wave2-review-nogo.md`.
- **#216/#217/#218** v1.3.0 indicator görsel polish + premium gallery + wrapup.
- **#221** premium.html/quickstart.html "CHoCH/BOS" yanlış iddiası → gerçek **Breaker Block**
  düzeltmesi (indicator CHoCH/BOS değil OB-kırılınca BB çiziyor; quickstart 4 uydurma alert →
  gerçek 2: `u2algo SMC LONG`/`SMC SHORT`).
- **T-015 entitlements:** canlı prod (`kjaicqpqfwnfbioofdib`) **zaten uygulanmış + doğrulandı**
  (tablo + RLS service-role-only + advisor temiz). `.env.supabase` token'ı **geçersiz** + yanlış
  ref (`trytjrtqdpmeekgxhhdb`) — stale dosya, kullanılmıyor.

## Senden rapor istediğim konular

1. **`0a5baa7`** ("feat(backtest): implement SetupStateStore memory pruning and gating on persist
   flag", `experiment/entry-slippage-backtest` HEAD) = 2026-06-16 görevinin (backtest v2 perf)
   karşılığı. Bu commit **bitmiş + review'a hazır mı**, yoksa hâlâ WIP mi?
   - ⚠️ `engine/safe_orchestrator.py` (CANLI trade path) dokunuyor → PR body'sine **"CANLI no-op"
     kanıtı** (persist=True yolu byte-identical) yazman gerekecek; risk-ops review zorunlu.
   - Hazırsa: Claude izole worktree'de master'dan atomic ayıklar → risk-ops + code review → PR → merge.
     "Hazır" sinyalini ver, ben başlatırım.
2. `experiment/entry-slippage-backtest` working tree'sinde **commit'siz iş** var (`.mcp.json`,
   `progress_callback`'li `backtest/engine.py`, `skill_log.md`). Bunlar **kalıntı mı, devam eden iş mi**?
   Kalıntıysa temizleyebilirsin; devamsa ne olduğunu söyle.
3. **(Opsiyonel stretch)** `confirm_entry` O(n) rebuild (`engine/smc_v2/confirmation.py`) — ayrı PR
   olarak planlanmıştı. Başladın mı / planlıyor musun?
4. **Track-2 Wave-2 new-edge research** (#215 Faz-0 proposal merged): devam mı, operatör
   yönlendirmesi mi bekliyorsun? Hatırlatma: Wave-2 DROP'un **yeniden-açma koşulu** = engine'in
   KENDİSİ yeniden tasarım + Python OOS'ta PF≥1.30 + ≥4/5 robustluk. Research'in o sanctioned yol
   ama henüz keşif (Faz-0) aşamasında — operatör onayı olmadan büyük implementasyona girme.

## Kurallar (değişmedi)
Canlı mainnet bot → feature-branch + PR, atomic, secrets repo'ya **ASLA**, destructive-op yok.
Transfer: `git format-patch origin/master --stdout` + sha256 → operatör relay → Claude `git am` →
review → PR → merge.
