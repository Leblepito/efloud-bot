# 🟦 Gemini — Sıradaki Görev: Backtest v2 Performans — setup_state persistence gating (2026-06-16)

> Hazırlayan: Claude (backend orchestrator). Bitince Claude review eder.
> Kurallar: canlı mainnet bot → feature-branch + PR, atomic, secrets repo'ya ASLA, destructive-op yok.
> ⚠️ Bu görev **CANLI TRADE PATH dosyasına** dokunur (`engine/safe_orchestrator.py`) → değişiklik
> CANLI davranışta **kesinlikle no-op** olmalı (sadece backtest hızlanır). risk-ops review zorunlu.
> **Transfer:** `git format-patch origin/master --stdout > /tmp/<ad>.patch` + sha256 → operatör scp →
> Claude `git am` → review → PR → merge.

## 0. Bağlam (bu oturumda kök-neden bulundu)
master = `e303e49`. Entry-slippage initiative **KAPANDI** (gate FAIL, `require_confirmation:true`
kalıyor). O koşumun ~saatler sürmesinin kök nedeni analiz edildi:

**SORUN:** `SafeOrchestrator.run_cycle` her cycle'da (her bar × her sembol) `setup_state_store.save()`
çağırıyor (`engine/safe_orchestrator.py:~1539`). Bu **atomik DİSK yazımı** (temp-file + rename).
Backtest'te orchestrator'a `persist=False` geçiliyor (`backtest/engine.py:~107`) AMA bu flag
`setup_state_store`'u **GATE'LEMİYOR** — o ayrı bir nesne. Sonuç: 180g × 10 sembol v2 backtest'te
**~172.800 disk yazımı/mod** → büyük wall-clock yavaşlık. Logging.ERROR'a çekmek I/O'nun bir kısmını
çözdü ama bunu çözmedi.

**EK NÜANS (dikkat):** in-memory CONFIRMED/EXPIRED pruning şu an SADECE `save()` içinde oluyor
(`engine/smc_v2/setup_state.py:~116`). save()'i komple atlarsan in-memory `candidates` listesi
budanmaz → her-bar `_advance_setup_state_tick` taraması büyür (DİĞER yavaşlık kaynağı). Yani fix
"disk yazımını atla" DEĞİL → **"in-memory prune'u disk-persist'ten AYIR"** olmalı.

## GÖREV — persist flag'ini setup_state save'ine bağla (CANLI no-op)
1. `engine/smc_v2/setup_state.py`: pruning'i diskten ayır — örn. `prune()` (sadece in-memory
   `candidates = [c for c in candidates if c.state in PERSISTED_STATES]`) + `save()` önce `prune()`
   çağırıp sonra atomik yazar. (Davranış aynen korunur.)
2. `engine/safe_orchestrator.py`: setup_state save() çağrı yerinde (~1539) persist flag'ini onurla:
   - `self.persist` (veya backtest'in geçtiği eşdeğer) **True** ise (CANLI) → bugünküyle BİREBİR aynı:
     `setup_state_store.save()` (prune + disk).
   - **False** ise (backtest) → `setup_state_store.prune()` (sadece in-memory budama, disk YOK).
   - "save() MUST remain above return" invariant'ı + gated try/except KORUNUR.
3. **CANLI no-op kanıtı:** persist=True yolu byte-identical davranır (disk yazımı + prune aynen). Yalnız
   persist=False (backtest) disk yazımını atlar.

## Test & Acceptance
- ✅ Yeni test: persist=False ile backtest `setup_candidates.json`'a **yazmaz** (temp dir'de dosya
   oluşmaz) AMA in-memory liste budanır (CONFIRMED/EXPIRED birikmez — per-symbol cap + prune ile sınırlı).
- ✅ persist=True (canlı) yol regresyonsuz: mevcut setup_state + safe_orchestrator testleri yeşil.
- ✅ Mevcut backtest engine suite (`backend/tests/test_backtest_engine_*.py`) yeşil + v2 backtest
   wall-clock **ölçülebilir düşer** (kısa bir profil/timing notu raporla).
- ✅ CANLI trade davranışı değişmez (risk-ops review için no-op kanıtını PR body'sine yaz).
- Çıktı: format-patch + sha256 → "review" sinyali.

## (Opsiyonel stretch, ayrı PR) confirm_entry O(n) rebuild
`engine/smc_v2/confirmation.py:confirm_entry` her çağrıda tüm `df_15m` üzerinden `timestamps_ms`
listesini yeniden kuruyor → Mode-A lingering adaylarda patlıyor. `since_ts` sonrası dar pencere
geçir / timestamps'i önbelleğe al. AYRI atomic PR; ana görev (1-3) önce.

> ⚠️ İlk koşumdaki rejim-etiketleme=0 ve liveness-stuck-şişme harness'a (`evaluate_slippage_backtest.py`
> monkeypatch'leri) özgüydü; initiative kapandığı için o harness'ı düzeltme — bu görev CORE backtest
> performansı (tüm backtest'lere fayda).
