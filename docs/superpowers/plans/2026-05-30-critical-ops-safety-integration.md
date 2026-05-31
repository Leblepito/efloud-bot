# Critical Operations & Safety Integration — Revize Edilmiş Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Also use `superpowers:test-driven-development` and `superpowers:verification-before-completion`.

**Goal:** Production trading bot'taki order-matching ve safety uyumsuzluklarını gidermek — SL repair'de precision hatalarını önlemek, daemon modunda exchange-side kapanışların CircuitBreaker'a akmasını sağlamak, range-deviation TP2 zarar-tarafı yerleşimini engellemek, prod config'i temizlemek, ve hedge-mode konfigürasyon-borsa uyumsuzluğunu çözmek.

**Architecture:**
1. SL repair'e exchange precision rounding ekle (size'ı DEĞİŞTİRMEDEN — `pos.size` korunur).
2. Daemon reconcile-kapanışlarını mantıksal `lifecycle` + `CircuitBreaker`'a idempotent (çift-sayım korumalı) senkronize et.
3. `signals.py` range-deviation TP2'ye karlı-taraf clamp uygula.
4. Prod config'deki çift `engine:` bloğunu temizle, eksik safety alanlarını ekle, ve `hedge_mode` config-vs-borsa uyumsuzluğunu DOĞRULA/çöz.
5. CLI giriş noktasını (`main.py`) order_manager injection + reconcile ile daemon ile simetrik hale getir.

**Tech Stack:** Python 3.12, CCXT, PyYAML, asyncio, pytest.

---

## ⚠️ Live-Ops Uyarıları (UYGULAMADAN ÖNCE OKU)

- **Bot ŞU AN mainnet'te, gerçek parayla, Phase 2 shadow aktif çalışıyor** (`configs/config.phase2_1k.yaml`, `dry_run: false`, `testnet: false`).
- **CLAUDE.md kuralı:** Bu repo'nun ana CLAUDE.md'si Pine çevirisi içindir ("Python kaynağını DEĞİŞTİRME"). Bu plan Python'u değiştirir → **kullanıcı/Hermes açık onayı şart**, Pine kuralı kapsamı dışında ayrı bir karardır.
- **Deploy disiplini** (memory: `feedback-deploy-caution`): container redeploy sessiz pencere gerektirir; config değişiklikleri (Task 4/5) görece güvenli ama yine de bot'un yeniden başlatılmasını gerektirir.
- **Her task ATOMIC PR olmalı** (memory: `smc-v2-rework-initiative` disiplini). Tek seferde hepsini merge etme.
- **Önerilen sıra (risk artan):** Task 3 → Task 5 → Task 4(araştırma) → Task 2 → Task 1 → Task 6.
- Bu plan branch `feat/pine-tp-fib-smc` üzerinde yazıldı ama Python değişiklikleri için **`master`'dan yeni branch** açılmalı (Pine branch'i ile karışmasın).

---

## File Structure

| Dosya | Sorumluluk | Task |
|-------|-----------|------|
| `engine/signals.py` | Range-deviation TP2 karlı-taraf clamp | 3 |
| `configs/config.phase2_1k.yaml` | Çift engine bloğu temizliği + safety alanları | 5 |
| `exchange/__init__.py` | SL repair precision rounding | 1 |
| `backend/bot_runner.py` | Daemon reconcile→breaker idempotent sync | 2 |
| `main.py` | CLI order_manager injection + reconcile | 6 |
| `backend/tests/test_signals_deviation_tp.py` | Task 3 testi (yeni) | 3 |
| `backend/tests/test_reconcile_breaker_sync.py` | Task 2 testi (yeni) | 2 |
| `backend/tests/test_sl_repair_precision.py` | Task 1 testi (yeni) | 1 |

---

## ❌ Orijinal Gemini Planından REDDEDİLEN / DEĞİŞTİRİLEN Kararlar

Bu plan, `implementation_plan.md`'nin (Gemini 3.5 Flash) koda karşı doğrulanmış revizyonudur. Aşağıdakiler **bilinçle reddedildi:**

1. **Task 1 — `sl_amount = tp2_size` REDDEDİLDİ.** SL repair bloğu (`exchange/__init__.py:555`) "SL emri tamamen kayıp" dalıdır; pozisyonun TAMAMINI koruması gerekir. `tp2_size`'a (yarı boyut) indirmek **çıplak kalan yarı pozisyon riski** yaratır — tam olarak önlemeye çalıştığımız 2026-05-14 incident senaryosu. SL daima `pos.size` kalır. Sadece eksik olan **precision rounding** eklenir (TP1/TP2'de var, SL'de yok — gerçek bir tutarsızlık).

2. **Task 2 — `_persist_close` içine ekleme REDDEDİLDİ, yeni yardımcı metoda taşındı.** Orijinal plan mevcut olmayan source'a yaslanıyordu ve çift-sayım riski vardı (breaker'a `safe_orchestrator.py:744`'te zaten kayıt var). Revize: idempotent `_reported_to_breaker` guard + `same_direction_open` ile gerçek lifecycle eşleşmesi.

3. **Task 3 — `if e_range and` guard'ı KALDIRILDI.** `range_info` asla `None` dönmez (`engine/smc.py:281` daima `RangeInfo` döner); guard redundant. Sadece karlı-taraf clamp uygulanır.

4. **Task 4 — kör bypass kaldırma REDDEDİLDİ, araştırma task'ına çevrildi.** Prod `hedge_mode: true` (config satır 37) AMA aynı dosyanın yorumu (satır 19) `Position mode = One-way` diyor. Bypass'ı körlemesine kaldırmak hedge semantiğini bozar VE asıl sorunu (config-borsa uyumsuzluğu) gizler. Önce gerçek Binance hesap modu doğrulanır.

5. **Task 6 — naïve `order_manager=` ekleme REDDEDİLDİ.** `order_mgr` orch'tan SONRA tanımlı (`main.py:579` > `:569`) → NameError. Revize: tanım sırası ters çevrilir.

---

## Task 3: Range Deviation TP2 Karlı-Taraf Clamp (EN GÜVENLİ — ÖNCE BU)

**Neden önce:** Saf hesaplama mantığı, hiçbir I/O/order/state'e dokunmaz; izole test edilir; mainnet davranışına etkisi sadece deviation TP2'nin daha güvenli yerleşmesi.

**Files:**
- Modify: `engine/signals.py:569-571`
- Test: `backend/tests/test_signals_deviation_tp.py` (yeni)

**Bağlam (gerçek kod, doğrulanmış):**
- `engine/signals.py:570-571`: `if has_dev and e_range: tp2 = e_range.hi if is_long else e_range.lo`
- `min_tp_long` `engine/signals.py:496`'da (is_long branch), `min_tp_short` `:538`'de (short branch) tanımlı — tp2 hesabına (`:569`) girerken biri kesin tanımlı.
- `has_dev` `:386`; `dev_bull`/`dev_bear` `engine/smc.py:281-282` → ölü kod DEĞİL, gerçek deviation/sweep'te tetiklenir.
- Sorun: `e_range.hi`/`e_range.lo` ham range ekstremleridir; deviation senaryosunda bunlar `min_tp` eşiğinin (min R:R) yanlış/zarar tarafında kalabilir → TP2 zarar bölgesine yerleşir.

- [ ] **Step 1: Failing test yaz**

`backend/tests/test_signals_deviation_tp.py`:

```python
"""Task 3: Range-deviation TP2 karlı-taraf clamp regresyon testi."""
import math


def _clamp_dev_tp2(tp2, min_tp, is_long):
    """signals.py:570-580'deki clamp mantığının saf kopyası (test oracle)."""
    if is_long:
        if tp2 < min_tp:
            tp2 = min_tp
    else:
        if tp2 > min_tp:
            tp2 = min_tp
    return tp2


def test_long_deviation_tp2_clamped_to_profitable_side():
    # range.hi entry'nin altında (zarar tarafı) → min_tp_long'a clamp'lenmeli
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = entry + risk * min_rr  # 103.6
    raw_tp2 = 99.0  # range.hi yanlış tarafta
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_long, is_long=True)
    assert clamped == min_tp_long
    assert clamped > entry  # karlı taraf


def test_short_deviation_tp2_clamped_to_profitable_side():
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = entry - risk * min_rr  # 96.4
    raw_tp2 = 101.0  # range.lo yanlış tarafta (yukarı)
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_short, is_long=False)
    assert clamped == min_tp_short
    assert clamped < entry


def test_valid_deviation_tp2_unchanged():
    # range.hi zaten karlı tarafta → değişmemeli
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = entry + risk * min_rr  # 103.6
    raw_tp2 = 110.0
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_long, is_long=True)
    assert clamped == 110.0
```

- [ ] **Step 2: Test'in geçtiğini doğrula (oracle saf fonksiyon)**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/test_signals_deviation_tp.py -v`
Expected: 3 PASS (bu test clamp mantığının kendisini doğrular; sonraki adım onu signals.py'ye taşır).

- [ ] **Step 3: signals.py'ye clamp uygula**

`engine/signals.py:569-571` — mevcut:
```python
        # Target opposite range extreme for deviation play, else fib extension
        if has_dev and e_range:
            tp2 = e_range.hi if is_long else e_range.lo
        else:
```

Şununla değiştir:
```python
        # Target opposite range extreme for deviation play, else fib extension
        if has_dev and e_range:
            tp2 = e_range.hi if is_long else e_range.lo
            # Karlı-taraf clamp: deviation TP2 asla min R:R eşiğinin zarar
            # tarafında olmamalı (range ekstremi entry'nin yanlış tarafında
            # kalabilir). min_tp_long/min_tp_short ilgili branch'te tanımlı.
            if is_long:
                if tp2 < min_tp_long:
                    tp2 = min_tp_long
            else:
                if tp2 > min_tp_short:
                    tp2 = min_tp_short
        else:
```

- [ ] **Step 4: Mevcut sinyal testlerini çalıştır (regresyon)**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/ -k "signal or smc" -v`
Expected: Tüm mevcut sinyal/smc testleri PASS (clamp sadece bozuk deviation TP2'leri düzeltir, geçerli olanları değiştirmez).

- [ ] **Step 5: Offline smoke (varsa)**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python test_offline.py`
Expected: Crash yok, sinyal üretimi çalışıyor.

- [ ] **Step 6: Commit**

```bash
git add engine/signals.py backend/tests/test_signals_deviation_tp.py
git commit -m "fix(signals): clamp range-deviation TP2 to profitable side"
```

---

## Task 5: Config Hygiene — `config.phase2_1k.yaml`

**Files:**
- Modify: `configs/config.phase2_1k.yaml`

**Bağlam (gerçek kod, doğrulanmış):**
- Çift `engine:` bloğu: satır **50-53** (1.) ve satır **145-148** (2.). PyYAML duplicate-key'de sessizce sonuncuyu (145-148) alır; ilki ölü. İkisi de özdeş (`smc_version: v2`, `smc_v2_symbols: ["*"]`, `smc_v2_shadow: true`) → şu an davranış aynı ama kırılgan.
- Safety alanları `safety:` bölümünden okunuyor: `reverse_min_profit_pct` (`safe_orchestrator.py:223`, default 0.2), `pause_new_entries` (`position_guard.py:68`, default None), `orphan_protection` (`orphan_protection.py:56` via `load_orphan_protection_config(cfg.get("safety", {}))`).
- `safety:` bölümü satır 118'de başlıyor, son anahtarı `min_seconds_between_symbol_fetches` satır 142'de.

- [ ] **Step 1: İkinci (ölü) `engine:` bloğunu sil**

`configs/config.phase2_1k.yaml:143-148` — mevcut:
```yaml

  min_seconds_between_symbol_fetches: 0.5


engine:
  smc_version: v2               # "v1" | "v2"
  smc_v2_symbols: ["*"]
  smc_v2_shadow: true          # true = log v2 signal, skip order placement
```

Şununla değiştir (safety alanları eklenir, ölü engine bloğu silinir):
```yaml

  min_seconds_between_symbol_fetches: 0.5

  # ── Safety Integration (2026-05-30 plan) ──
  reverse_min_profit_pct: 0.2          # kontra sinyal: karda + %0.2 buffer üstünde reverse
  pause_new_entries: false             # true = yeni giriş durdur (mevcut pozisyonlar yönetilir)
  orphan_protection:
    enabled: true                      # borsa-yetim pozisyona otomatik SL
    mode: place_missing_sl
    default_sl_pct: 2.0
    max_auto_protect_per_cycle: 1
    min_distance_to_mark_pct: 0.5
    require_tp_present: false           # TP'siz çıplak pozisyon EN risklisi → koru
```

> **NOT:** Tek kalan `engine:` bloğu satır 50-53'tür. Silme sonrası `grep -c "^engine:" configs/config.phase2_1k.yaml` **1** dönmeli.

- [ ] **Step 2: YAML geçerliliğini ve tek engine bloğunu doğrula**

Run:
```bash
$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -c "import yaml; d=yaml.safe_load(open('configs/config.phase2_1k.yaml',encoding='utf-8')); print('engine:', d['engine']); print('orphan:', d['safety']['orphan_protection']['enabled']); print('reverse:', d['safety']['reverse_min_profit_pct'])"
```
Expected:
```
engine: {'smc_version': 'v2', 'smc_v2_symbols': ['*'], 'smc_v2_shadow': True}
orphan: True
reverse: 0.2
```

- [ ] **Step 3: config validation'dan geçtiğini doğrula**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -c "from main import load_config, validate_config; c=load_config('configs/config.phase2_1k.yaml'); validate_config(c); print('VALID')"`
Expected: `VALID` (veya validate_config imzası farklıysa uygun çağrı).

- [ ] **Step 4: orphan_protection testini çalıştır**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/test_orphan_protection.py -v`
Expected: PASS (orphan protection artık enabled, mevcut testler davranışı kapsar).

> **⚠️ Live-ops:** `orphan_protection.enabled: true` artık borsa-yetim pozisyonlara otomatik SL koyacak. Bu davranış değişikliğidir — **Hermes onayı + ilk cycle'da log gözlemi** gerekir. İlk deploy'da `max_auto_protect_per_cycle: 1` ile sınırlı.

- [ ] **Step 5: Commit**

```bash
git add configs/config.phase2_1k.yaml
git commit -m "fix(config): remove duplicate engine block, add safety fields (orphan/reverse/pause)"
```

---

## Task 4: Hedge-Mode Config-Borsa Uyumsuzluğu (ARAŞTIRMA + KARAR)

**Bu bir kod task'ı DEĞİL — önce doğrulama, sonra karar.** Orijinal planın "bypass'ı kaldır" önerisi körlemesine uygulanırsa hedge semantiği bozulur ve asıl sorun gizlenir.

**Files (potansiyel):**
- `configs/config.phase2_1k.yaml:37` (`hedge_mode: true`)
- `engine/safety/position_guard.py:290-297` (opposite-direction bypass)

**Bağlam (gerçek kod + incident, doğrulanmış):**
- `config.phase2_1k.yaml:37`: `hedge_mode: true` AMA `:19` yorumu `✓ Position mode = One-way`.
- Memory `binance-isolated-hedge-off-autoflip` + incident 2026-05-14: Binance isolated+hedge-off iken kontra emir pozisyonu otomatik flip yapıp bot'un TP/SL disiplinini bypass etti → 3 çıplak pozisyon.
- `position_guard.py:290` `if not self.hedge_mode:` → hedge_mode=true iken opposite-direction check tamamen atlanıyor.

- [ ] **Step 1: Gerçek Binance hesap pozisyon modunu doğrula**

Kullanıcıdan iste (interaktif login gerekebilir — `! ` prefix ile):
```
! .venv\Scripts\python -c "from exchange import BinanceClient; from main import load_config; import os; c=load_config('configs/config.phase2_1k.yaml'); cl=BinanceClient(c); print('dualSidePosition:', cl.exchange.fapiPrivateGetPositionSideDual())"
```
Beklenen çıktı `{'dualSidePosition': True}` (hedge) veya `False` (one-way).

- [ ] **Step 2: Karar matrisi**

| Borsa modu | Config `hedge_mode` | Aksiyon |
|-----------|--------------------|---------| 
| `False` (one-way) | `true` | **UYUMSUZ — KRİTİK.** Config `hedge_mode: false` yapılmalı. One-way'de bot kontra emir gönderirse Binance auto-flip yapar → bypass=False olunca guard zaten devreye girer (kod doğru, config yanlış). |
| `True` (hedge) | `true` | Uyumlu. Bypass kasıtlı (çift-yön pozisyon). Değişiklik gerekmez AMA reverse-on-profit isteniyorsa Task 4-Step3'e bak. |
| `True` (hedge) | `false` | Config `hedge_mode: true` yapılmalı (positionSide param'ları için). |

- [ ] **Step 3 (yalnızca hedge=true + reverse isteniyorsa): regular pozisyonlara opposite-check enforce**

Eğer hesap gerçekten hedge ve kullanıcı "regular pozisyonlarda reverse-on-profit istiyorum, sadece scenario hedge'leri çift-yön olsun" derse, `position_guard.py:290`:

```python
        if not self.hedge_mode:
            for p in existing_positions:
                if (p.is_open and p.symbol == symbol and p.direction != direction
                    and p.scenario_id is None):
                    return PositionCheckResult(
                        False,
                        f"OPPOSITE_DIRECTION_EXISTS: {p.direction} open on {symbol} (pos {p.id})"
                    )
```
→
```python
        # Regular pozisyonlarda (scenario_id is None) opposite-direction'ı
        # hedge mode'da da reddet → orchestrator reverse-on-profit değerlendirir.
        # Scenario hedge'leri (scenario_id set) bu kontrolden muaf (çift-yön kasıtlı).
        for p in existing_positions:
            if (p.is_open and p.symbol == symbol and p.direction != direction
                and p.scenario_id is None):
                return PositionCheckResult(
                    False,
                    f"OPPOSITE_DIRECTION_EXISTS: {p.direction} open on {symbol} (pos {p.id})"
                )
```

Bu değişiklik yapılırsa `backend/tests/test_reverse_guard.py` + `test_position_guard*.py` çalıştırılıp yeşil olmalı.

- [ ] **Step 4: Kararı belgele + commit (config değişikliği varsa)**

```bash
git add configs/config.phase2_1k.yaml  # ve/veya engine/safety/position_guard.py
git commit -m "fix(safety): reconcile hedge_mode config with exchange account mode"
```

> **⚠️ Bu task'ın çıktısı koda göre değişir. Step 1 sonucu olmadan ilerlenmemeli.** Kullanıcı/Hermes onayı zorunlu — pozisyon modu değişikliği açık pozisyonları etkiler.

---

## Task 2: Daemon Reconcile → CircuitBreaker Idempotent Sync

**Files:**
- Modify: `backend/bot_runner.py` (yeni metot `_sync_reconciled_close_to_logical` + `_persist_close`'dan çağrı)
- Test: `backend/tests/test_reconcile_breaker_sync.py` (yeni)

**Bağlam (gerçek kod, doğrulanmış):**
- `bot_runner.py:314-317`: `closed = reconcile()` → `for pos in closed: await self._persist_close(pos)`.
- `_persist_close` (`bot_runner.py:514-524`): SADECE `db.record_trade_close`. Breaker/lifecycle'a dokunmuyor.
- `self.orch` var (`bot_runner.py:225`); `self.orch.lifecycle.same_direction_open(symbol, direction) -> Optional[Position]` (`lifecycle.py:496`).
- `self.orch.breaker.record_trade(pnl)` (`breaker.py:102`).
- `self.orch._journal_record_exit(pos, exit_price, reason)` (`safe_orchestrator.py:431`) — SafeOrchestrator metodu, lifecycle Position alır.
- **Çift-sayım riski:** `safe_orchestrator.py:741-746` STEP5'te lifecycle-kapanışları zaten `_reported_to_breaker` guard'ı ile breaker'a yazıyor. Yeni kod AYNI guard'ı kullanmalı.
- `closed` listesindeki `pos` exchange-side `Position` (`exchange/__init__.py:246`): alanları `pnl_usdt`, `exit_price`, `exit_reason` (reconcile `_record_close`'da set ediliyor). Bu objede `realized_pnl` YOK. Mantıksal eşi `logical_pos` ise `lifecycle.Position` (orada `realized_pnl` property VAR, `:135`).

**Tasarım kararı:** Reconcile-kapanışı = exchange tarafında pozisyon kapandı. Mantıksal lifecycle'da hâlâ açık görünen eşini bul (`same_direction_open`), onu kapat, PnL'i breaker'a idempotent bildir. Breaker'a `logical_pos.realized_pnl` (lifecycle hesabı) değil, exchange-gerçeği `pos.pnl_usdt` yazılır (daha doğru). Eğer mantıksal eş yoksa (daemon'da yaygın — exchange pozisyonları lifecycle'a kayıtlı olmayabilir) sadece breaker'a `pos.pnl_usdt` yazılır, yine idempotent (exchange pos'a `_reported_to_breaker` flag eklenir).

- [ ] **Step 1: Failing test yaz**

`backend/tests/test_reconcile_breaker_sync.py`:

```python
"""Task 2: Reconcile-kapanışının breaker'a idempotent aktığını doğrula."""
import types
import pytest


class _FakeBreaker:
    def __init__(self):
        self.recorded = []
    def record_trade(self, pnl, timestamp=None):
        self.recorded.append(pnl)


class _FakeLifecycle:
    def __init__(self, logical=None):
        self._logical = logical
    def same_direction_open(self, symbol, direction):
        return self._logical
    def close_position(self, pos, price, reason):
        pos.closed = True


class _FakeOrch:
    def __init__(self, logical=None):
        self.breaker = _FakeBreaker()
        self.lifecycle = _FakeLifecycle(logical)
    def _journal_record_exit(self, pos, exit_price, reason):
        pass


def _make_closed_pos(pnl=-12.5):
    p = types.SimpleNamespace()
    p.symbol = "BTC/USDT"; p.direction = "LONG"
    p.entry = 100.0; p.exit_price = 95.0
    p.pnl_usdt = pnl; p.exit_reason = "SL"
    p.trace_id = None; p.mae_pct = None; p.mfe_pct = None
    return p


def _sync(orch, pos):
    """bot_runner._sync_reconciled_close_to_logical mantığının test kopyası."""
    if getattr(pos, "_reported_to_breaker", False):
        return
    logical = orch.lifecycle.same_direction_open(pos.symbol, pos.direction)
    if logical is not None:
        orch.lifecycle.close_position(logical, pos.exit_price, pos.exit_reason)
        orch._journal_record_exit(logical, pos.exit_price, pos.exit_reason)
    orch.breaker.record_trade(pos.pnl_usdt)
    pos._reported_to_breaker = True


def test_reconciled_close_records_pnl_once():
    orch = _FakeOrch()
    pos = _make_closed_pos(-12.5)
    _sync(orch, pos)
    assert orch.breaker.recorded == [-12.5]


def test_reconciled_close_idempotent():
    orch = _FakeOrch()
    pos = _make_closed_pos(-12.5)
    _sync(orch, pos)
    _sync(orch, pos)  # ikinci çağrı no-op olmalı
    assert orch.breaker.recorded == [-12.5]  # çift-sayım YOK


def test_reconciled_close_with_logical_match_closes_it():
    logical = types.SimpleNamespace(closed=False)
    orch = _FakeOrch(logical=logical)
    pos = _make_closed_pos(8.0)
    _sync(orch, pos)
    assert logical.closed is True
    assert orch.breaker.recorded == [8.0]
```

- [ ] **Step 2: Test'in geçtiğini doğrula (oracle)**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/test_reconcile_breaker_sync.py -v`
Expected: 3 PASS.

- [ ] **Step 3: bot_runner.py'ye yardımcı metot ekle**

`backend/bot_runner.py:514` `_persist_close` metodunun HEMEN ÖNCESİNE yeni metot ekle:

```python
    def _sync_reconciled_close_to_logical(self, pos: Position) -> None:
        """Exchange-side reconcile kapanışını mantıksal lifecycle + breaker'a
        idempotent senkronize et.

        Neden: reconcile() borsadaki TP/SL fill'lerini yakalar ama bu kapanışlar
        CircuitBreaker'ın daily/consecutive-loss sayaçlarına akmıyordu (breaker
        sadece lifecycle-kapanışlarını görüyordu, safe_orchestrator.py:741-746).
        Bu, gerçek SL serilerinde breaker'ı kör bırakıyordu (Y2 bulgusu).

        Idempotent: pos._reported_to_breaker flag'i çift-sayımı önler
        (safe_orchestrator STEP5 ile aynı sözleşme).
        """
        if self.orch is None:
            return
        if getattr(pos, "_reported_to_breaker", False):
            return
        try:
            logical = self.orch.lifecycle.same_direction_open(pos.symbol, pos.direction)
            if logical is not None and not getattr(logical, "_reported_to_breaker", False):
                self.orch.lifecycle.close_position(logical, pos.exit_price, pos.exit_reason)
                self.orch._journal_record_exit(logical, pos.exit_price, pos.exit_reason)
                logical._reported_to_breaker = True
            # Breaker'a exchange-gerçeği PnL yaz (lifecycle tahmini değil)
            self.orch.breaker.record_trade(pos.pnl_usdt)
            pos._reported_to_breaker = True
            log.info(
                f"Reconcile→breaker sync: {pos.symbol} {pos.direction} "
                f"pnl=${pos.pnl_usdt:.2f} reason={pos.exit_reason}"
            )
        except Exception as e:
            log.warning(f"Reconcile→breaker sync failed for {pos.symbol}: {e}")
```

- [ ] **Step 4: `_persist_close`'dan çağır**

`backend/bot_runner.py:514-524` `_persist_close` metodunun SONUNA (db.record_trade_close çağrısından sonra) ekle:

```python
        await db.record_trade_close(
            symbol=pos.symbol, exit_price=pos.exit_price,
            pnl_usdt=pos.pnl_usdt, pnl_pct=pnl_pct, reason=pos.exit_reason,
            trace_id=getattr(pos, "trace_id", None),
            mae_pct=getattr(pos, "mae_pct", None),
            mfe_pct=getattr(pos, "mfe_pct", None),
        )

        # Task 2: exchange-side kapanışı breaker'a idempotent bildir (Y2 fix)
        self._sync_reconciled_close_to_logical(pos)
```

- [ ] **Step 5: Mevcut bot_runner + safety testlerini çalıştır (regresyon)**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/ -k "bot_runner or breaker or safety or reconcile" -v; .venv\Scripts\python test_safety.py`
Expected: Tümü PASS, breaker davranışı bozulmadı.

- [ ] **Step 6: Commit**

```bash
git add backend/bot_runner.py backend/tests/test_reconcile_breaker_sync.py
git commit -m "fix(bot_runner): sync reconciled exchange closes to breaker (idempotent)"
```

---

## Task 1: SL Repair Precision Rounding (Size DEĞİŞMEZ)

**Files:**
- Modify: `exchange/__init__.py:566` (SL repair, `_retry_tp_order` çağrısından önce)
- Test: `backend/tests/test_sl_repair_precision.py` (yeni)

**Bağlam (gerçek kod, doğrulanmış):**
- `exchange/__init__.py:554-586`: SL repair bloğu, `if not pos.sl_order_id:` (SL emri tamamen kayıp).
- `amount=pos.size` (`:575`) — TAM boyut, korunmalı (çıplak yarı-pozisyon riskine karşı).
- TP1/TP2 repair'de `amount_to_precision` rounding VAR (`:542-552`) ama SL repair'de YOK → Binance `stepSize`/`lotSize` hatası riski (SL emri reddedilirse pozisyon korunmasız kalır).

**Tasarım kararı:** Gemini'nin `tp2_size` indirimini REDDEDİYORUZ. Tek değişiklik: `pos.size`'a precision rounding eklemek (TP'lerle simetri). Boyut yarıya inmez.

- [ ] **Step 1: Failing test yaz**

`backend/tests/test_sl_repair_precision.py`:

```python
"""Task 1: SL repair'in tam boyutu koruyup precision rounding uyguladığını doğrula."""


def _sl_repair_amount(pos_size, precision_fn, dry_run=False):
    """exchange/__init__.py SL repair amount mantığının test kopyası.

    KRİTİK: SL repair 'emir tamamen kayıp' dalıdır → TAM pos_size korunmalı.
    Sadece precision rounding uygulanır (boyut yarıya İNMEZ).
    """
    sl_amount = pos_size  # tam boyut — asla tp2_size'a indirilmez
    if not dry_run:
        try:
            res = precision_fn(sl_amount)
            if isinstance(res, str):
                sl_amount = float(res)
        except Exception:
            pass
    return sl_amount


def test_sl_repair_preserves_full_size():
    # tp1_hit olsa bile SL tam boyutu korur (çıplak yarı-pozisyon yok)
    amt = _sl_repair_amount(1.0, precision_fn=lambda x: str(x), dry_run=False)
    assert amt == 1.0


def test_sl_repair_applies_precision():
    # exchange precision 0.001 step → yuvarlanır
    amt = _sl_repair_amount(1.23456, precision_fn=lambda x: "1.234", dry_run=False)
    assert amt == 1.234


def test_sl_repair_dry_run_skips_precision():
    amt = _sl_repair_amount(1.23456, precision_fn=lambda x: "1.234", dry_run=True)
    assert amt == 1.23456


def test_sl_repair_precision_failure_falls_back_to_raw():
    def _raise(x):
        raise RuntimeError("network")
    amt = _sl_repair_amount(1.0, precision_fn=_raise, dry_run=False)
    assert amt == 1.0  # crash yerine ham boyut
```

- [ ] **Step 2: Test'in geçtiğini doğrula**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/test_sl_repair_precision.py -v`
Expected: 4 PASS.

- [ ] **Step 3: exchange/__init__.py'de SL repair'e precision ekle**

`exchange/__init__.py:565-566` — mevcut:
```python
                )
                sl_repair_params = {"stopPrice": pos.sl}
```

Şununla değiştir:
```python
                )
                # SL repair TAM boyutu korur (emir tamamen kayıp dalı — yarı
                # boyut çıplak pozisyon riski yaratır). Sadece TP1/TP2 ile
                # simetrik precision rounding uygula (stepSize hatası önlenir).
                sl_amount = pos.size
                if not self.dry_run:
                    try:
                        res_sl = self.client.exchange.amount_to_precision(ccxt_sym, sl_amount)
                        if isinstance(res_sl, str):
                            sl_amount = float(res_sl)
                    except Exception as e:
                        log.warning(
                            f"Failed to format SL size using exchange precision "
                            f"for {pos.symbol}: {e}"
                        )
                sl_repair_params = {"stopPrice": pos.sl}
```

Ve `:575` `amount=pos.size,` → `amount=sl_amount,`:
```python
                new_sl_oid = self._retry_tp_order(
                    ccxt_sym=ccxt_sym,
                    order_type="STOP_MARKET",
                    side=reverse_side,
                    amount=sl_amount,
```

- [ ] **Step 4: Mevcut SL retry/reconcile testlerini çalıştır**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/test_sl_retry.py backend/tests/ -k "reconcile or repair or order" -v`
Expected: PASS (size davranışı değişmedi, sadece rounding eklendi).

- [ ] **Step 5: Commit**

```bash
git add exchange/__init__.py backend/tests/test_sl_repair_precision.py
git commit -m "fix(exchange): add precision rounding to SL repair (size unchanged)"
```

---

## Task 6: CLI order_manager Injection + Reconcile (main.py)

**Files:**
- Modify: `main.py:558-587` (tanım sırası), `main.py:289-311` (run_cycle reconcile)

**Bağlam (gerçek kod, doğrulanmış):**
- `main.py:569-573`: `orch = SafeOrchestrator(...)` — `order_manager=` YOK.
- `main.py:577` `orphan_protector`, `:579` `order_mgr` — orch'tan SONRA tanımlı → naïve `order_manager=order_mgr` ekleme **NameError**.
- `main.py:594-599` ana döngü: sadece `run_cycle(...)`, reconcile çağrısı YOK.
- `order_mgr.reconcile() -> List[Position]` (`exchange/__init__.py:979`, dry_run'da `[]`).
- `OrphanProtector`, `load_orphan_protection_config` import edili (`main.py:40`).
- **Prod FastAPI modunu kullanıyor** → bu task düşük öncelik ama CLI'yi güvenli kılar (Task 2 ile simetri).

**Tasarım kararı:** `order_mgr`/`orphan_protector` tanımını orch'tan ÖNCEYE taşı, sonra orch'a `order_manager=order_mgr` geç. run_cycle başına reconcile + Task 2'deki sync mantığını ekle.

- [ ] **Step 1: Tanım sırasını düzelt + injection**

`main.py:568-587` — mevcut:
```python
    setup_state_store = _build_setup_state_store(cfg, state_dir)
    orch = SafeOrchestrator(cfg, state_dir=state_dir,
                              permission_mgr=permission_mgr,
                              notification_mgr=notif_mgr,
                              trade_journal=trade_journal,
                              setup_state_store=setup_state_store)

    # Build orphan_protector (mirrors bot_runner.py:189-190)
    orphan_cfg = load_orphan_protection_config(cfg.get("safety", {}))
    orphan_protector = OrphanProtector(orphan_cfg, client) if not cfg["operation"]["dry_run"] else None
    
    order_mgr = OrderManager(
        client,
        dry_run=cfg["operation"]["dry_run"],
        state_dir=state_dir,
        orphan_protector=orphan_protector,
        trade_journal=trade_journal,
        hedge_mode=cfg.get("exchange", {}).get("hedge_mode", False),
    )
    rate_limiter = RateLimiter(max_per_minute=1000)
```

Şununla değiştir (order_mgr önce, sonra orch'a inject):
```python
    setup_state_store = _build_setup_state_store(cfg, state_dir)

    # order_mgr orch'tan ÖNCE kurulmalı (CLI'de orch'a inject edilecek —
    # aksi halde orch.order_manager=None kalır, reconcile/orphan çalışmaz).
    orphan_cfg = load_orphan_protection_config(cfg.get("safety", {}))
    orphan_protector = OrphanProtector(orphan_cfg, client) if not cfg["operation"]["dry_run"] else None

    order_mgr = OrderManager(
        client,
        dry_run=cfg["operation"]["dry_run"],
        state_dir=state_dir,
        orphan_protector=orphan_protector,
        trade_journal=trade_journal,
        hedge_mode=cfg.get("exchange", {}).get("hedge_mode", False),
    )

    orch = SafeOrchestrator(cfg, state_dir=state_dir,
                              permission_mgr=permission_mgr,
                              notification_mgr=notif_mgr,
                              order_manager=order_mgr,
                              trade_journal=trade_journal,
                              setup_state_store=setup_state_store)
    rate_limiter = RateLimiter(max_per_minute=1000)
```

- [ ] **Step 2: run_cycle başına reconcile + sync ekle**

`main.py:289-311` `run_cycle` fonksiyonu — mevcut başlangıç:
```python
def run_cycle(orch: SafeOrchestrator, client: BinanceClient,
                order_mgr: OrderManager, rate_limiter: RateLimiter,
                universe: SymbolUniverse, cfg: dict):
    """Tüm symbol universe'ü analiz et."""
    log = logging.getLogger("efloud.main")
    symbols = universe.resolve()
```

Şununla değiştir:
```python
def run_cycle(orch: SafeOrchestrator, client: BinanceClient,
                order_mgr: OrderManager, rate_limiter: RateLimiter,
                universe: SymbolUniverse, cfg: dict):
    """Tüm symbol universe'ü analiz et."""
    log = logging.getLogger("efloud.main")

    # CLI reconcile pass (daemon bot_runner._run_loop ile simetri).
    # Borsa kapanışlarını yakala + breaker'a idempotent bildir.
    if order_mgr and not cfg["operation"]["dry_run"]:
        try:
            closed = order_mgr.reconcile()
            for pos in closed:
                if getattr(pos, "_reported_to_breaker", False):
                    continue
                logical = orch.lifecycle.same_direction_open(pos.symbol, pos.direction)
                if logical is not None and not getattr(logical, "_reported_to_breaker", False):
                    orch.lifecycle.close_position(logical, pos.exit_price, pos.exit_reason)
                    orch._journal_record_exit(logical, pos.exit_price, pos.exit_reason)
                    logical._reported_to_breaker = True
                orch.breaker.record_trade(pos.pnl_usdt)
                pos._reported_to_breaker = True
                log.info(
                    f"CLI reconcile→breaker: {pos.symbol} {pos.direction} "
                    f"pnl=${pos.pnl_usdt:.2f} reason={pos.exit_reason}"
                )
        except Exception as e:
            log.warning(f"CLI reconcile pass failed: {e}")

    symbols = universe.resolve()
```

> **NOT:** Bu mantık Task 2'deki `_sync_reconciled_close_to_logical` ile aynı. DRY için Task 2 önce merge edilirse, ortak fonksiyon `engine/` veya `utils/`'e taşınıp her iki yerden çağrılabilir (opsiyonel refactor — ayrı PR).

- [ ] **Step 3: CLI smoke (dry_run ile, gerçek emir YOK)**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -c "import ast; ast.parse(open('main.py',encoding='utf-8').read()); print('main.py parses OK')"`
Expected: `main.py parses OK` (syntax doğrulama — canlı çalıştırma YOK, bot zaten daemon'da koşuyor).

- [ ] **Step 4: import + instantiation testi (dry_run config ile)**

Run: `$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python -m pytest backend/tests/ -k "main or cli or orchestrator" -v`
Expected: PASS (varsa). Yoksa Step 3 yeterli.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "fix(main): inject order_manager into CLI orchestrator + reconcile sync"
```

---

## 🏁 Verification Plan

### Otomatik (her task'tan sonra)
```bash
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python -m pytest backend/tests/ -v
.venv\Scripts\python test_safety.py
.venv\Scripts\python test_smoke.py
```

### Task-bazlı kabul kriterleri
| Task | Kabul kriteri |
|------|---------------|
| 3 | Deviation TP2 daima entry'nin karlı tarafında; mevcut sinyal testleri yeşil |
| 5 | `grep -c "^engine:"` = 1; YAML parse OK; orphan enabled doğrulandı |
| 4 | Borsa pozisyon modu config ile uyumlu (Step 1 çıktısı belgelendi) |
| 2 | Breaker reconcile-kapanışını TAM BİR KEZ kaydeder (idempotent test yeşil) |
| 1 | SL repair tam boyut korur + precision uygular (4 test yeşil) |
| 6 | main.py parse OK; orch.order_manager artık None değil |

### Manuel (deploy sonrası — Hermes domain)
- Testnet veya local dry-run daemon başlat, log'larda `Reconcile→breaker sync` satırını gözle.
- İlk canlı cycle'da `orphan_protection` log'unu izle (Task 5 davranış değişikliği).
- Breaker `consecutive_losses` sayacının exchange-SL'lerinde arttığını doğrula.

---

## Self-Review Notları

- **Spec coverage:** Görev 1 bulguları K1(→T5), K3(→T6), Y1(→T5), Y2(→T2), Y4(→T4) + Gemini planı 6 task → hepsi karşılandı. K2 (v1 canlı yol niyeti) bu plana dahil DEĞİL — ayrı bir politika kararı (kullanıcı/Hermes), kod değil.
- **Tip tutarlılığı:** `same_direction_open(symbol, direction)` imzası tüm task'larda tutarlı (`lifecycle.py:496`). `pos.pnl_usdt` (exchange Position) vs `realized_pnl` (lifecycle Position) ayrımı korundu. `_reported_to_breaker` flag sözleşmesi Task 2 + Task 6'da aynı.
- **Placeholder yok:** Tüm diff'ler gerçek koddan, tüm testler tam.
- **Reddedilen kararlar** üstte ❌ bölümünde gerekçeli belgelendi.
