# Session Handoff — 2026-06-07 (Bug-Hunt #14 + Lifecycle None-Safety Sweep)

> **Operatör/Hermes için kalıcı kayıt.** Tarih: 2026-06-07 (UTC).
> Önceki handoff: `docs/handoff/2026-06-07_quant_walkthrough_session.md` (Quant fixes + walkthrough deploy).
> Master HEAD: `c060812` (PR #171) | Branch: `fix/lifecycle-none-safety-sweep-bug-hunt-15` (PR bekliyor).
> Bot durumu: **CANLI**, loop alive, breaker tripped, 4 saat sonra otomatik resume.

---

## 1. TL;DR (30 saniye)

| Şey | Durum |
|---|---|
| **Master** | `c060812` (PR #171) — sen merge edersen |
| **VPS HEAD** | `40ae62d` (PR #170 deploy edilmiş, image baked-in rebuild başarılı) |
| **Bot** | Up, healthy, **`cycle failed: int + NoneType` = 0** (PR #170 etkili) |
| **Breaker** | TRIPPED, 4 saat sonra otomatik resume |
| **Book** | Flat (0 açık pozisyon) |
| **DB** | Supabase bağlantısı hâlâ kopuk (DNS propagation yavaş), file-based devam |
| **Piyasa** | Bekleme — sinyaller gelirse Conf >= 50, R:R >= 1.8 ile trade |

**3 PR, 1.5 saat, 1 root-cause fix**:
- **PR #168** (breaker.py) — yanlış yer, hata devam etti
- **PR #169** (exc_info=True) — debug PR, gerçek traceback aldık
- **PR #170** (lifecycle.py:163) — **gerçek fix**, `cycle failed = 0`
- **PR #171** (lifecycle.py sweep) — 4 ek None-arithmetic site, **proaktif önlem**

---

## 2. Bulgular (Sıralı)

### 2.1 DATABASE_URL yok (P28)

- `.env.production`'da DATABASE_URL yoktu (CLAUDE.md §3 ihmal etmiş)
- Bot 5dk'da bir migration çalıştırıyor, hata: `(ENOTFOUND) tenant/user postgres.kjaicqpwfwnfbioofdib not found`
- `db.py` gracefully no-op (file-based devam)
- Pooler 21 AWS region "tenant not found" → password yanlış veya proje DNS propagate olmamış
- **Aksiyon**: operatör Supabase SQL Editor'de `combined_migrations.sql` Run etti → migration tamam
- **Ama**: pooler hala `tenant not found` (Google DNS hâlâ propagate olmamış, Cloudflare çözüyor)

### 2.2 DNS propagation gecikmesi

- Windows local: `kjaicqpwfwnfbioofdib.supabase.co` → DNS FAIL
- Cloudflare 1.1.1.1: çözüyor
- Google 8.8.8.8: "Non-existent"
- Hetzner varsayılan Google → DNS fail
- **Çözüm**: Hetzner `/etc/resolv.conf` → `1.1.1.1` önce, `8.8.8.8` fallback (operatör)
- **Bekleme**: 30dk+ DNS propagation tamamlanacak

### 2.3 P29 — Image baked-in (HER İLERLEMEYİ ENGELLEDİ)

- Container `efloud-bot` **image baked-in** çalışıyor, /app source image içinde
- **Sadece state/logs/reports/content_jobs Docker volume mount** (doğrulandı: `docker inspect`)
- CLAUDE.md/HERMES.md'deki "bind-mount source" ifadesi **YANLIŞ** (P7 doğrulandı)
- **Her PR'da `docker compose build --no-cache efloud-bot` gerekli**
- Container restart YETMEZ, kod değişmez
- 2 kez yanlış deploy: PR #168 + PR #170 sonrası sadece restart, kod eski kaldı

### 2.4 Bug-hunt #14 — `int + NoneType` cycle crash

- **Semptom**: `cycle failed: unsupported operand type(s) for +: 'int' and 'NoneType'`
- **İlk yanlış tahmin (PR #168)**: breaker.py:174 daily_pnl sum
- **Gerçek kök neden (PR #169 + PR #170)**: `lifecycle.py:163` realized_pnl
- **Traceback** (PR #169 exc_info=True sayesinde):
  ```
  File "/app/engine/safe_orchestrator.py", line 944, in run_cycle
      self.breaker.record_trade(p.realized_pnl)
  File "/app/engine/lifecycle.py", line 163, in realized_pnl
      return sum(e.pnl for e in self.exits)
  TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'
  ```
- **Sebep**: PR #164 / PR #167 LOW batch remaining-inventory cost-basis math edge case → `pnl=None` exit
- **Fix**: `sum(e.pnl for e in self.exits if e.pnl is not None)`

### 2.5 Bug-hunt #15 — Aynı pattern, 4 ek site (PR #171)

`lifecycle.py`'de aynı None-arithmetic pattern, farklı yerler:
1. `total_size_entered` / `total_size_exited` (line 115/119) — `sum(e.size for e in ...)` crash if `e.size=None`
2. `avg_entry_price` — running weighted average (PR #164 line 152) — `cost += price * sz` crash
3. `avg_entry_price` — simple fallback (line 158) — `sum(e.price * e.size)` crash
4. `unrealized_pnl(current_price)` (line 174) — `(current_price - avg) * size` crash if `current_price=None`

**Tüm 4 site PR #171'de None-skip yapıldı**.

---

## 3. PR Timeline (Sıralı)

| PR | Branch | Ne yaptı | Durum |
|---|---|---|---|
| #168 | `fix/breaker-none-pnl-bug-hunt-13` | breaker.py:174 None-skip | ❌ Yanlış yer, hata devam |
| #169 | `fix/cycle-failed-exc-info` | bot_runner.py:511 exc_info=True | ✅ Debug PR, traceback aldık |
| #170 | `fix/lifecycle-realized-pnl-none-bug-hunt-14` | lifecycle.py:163 realized_pnl None-skip | ✅ **GERÇEK FIX**, deploy edildi |
| #171 | `fix/lifecycle-none-safety-sweep-bug-hunt-15` | lifecycle.py 4 ek site None-skip | ⏳ Sen merge et, sonra deploy |

**Toplam etki**: `cycle failed: int + NoneType` 30+ hata/saniye → **0**.

---

## 4. Mimari Kararlar

### 4.1 Image baked-in pattern (değişmedi, doğrulandı)

```
Hetzner docker inspect efloud-bot:
  /var/lib/docker/volumes/efloud-bot_efloud_state_1k/_data -> /app/state_1k (volume)
  /var/lib/docker/volumes/efloud-bot_efloud_logs/_data -> /app/logs (volume)
  ... (sadece state, logs, reports, content_jobs mount)
  /app/backend/bot_runner.py: IMAGE baked-in, container içinde eski kod
```

**YANLIŞ bilgi**: "Docker bind-mounts source, no image rebuild" (CLAUDE.md/HERMES.md)
**DOĞRU**: Her PR'da image rebuild gerek

### 4.2 None-safety pattern (PR #170 + #171)

- `sum(x.field for x in records)` → `sum(x.field for x in records if x.field is not None)`
- `function(None)` return type 0 (graceful degradation)
- Production'da journal entry None dönebilir (open in-flight, ws snapshot stale, edge case math)

### 4.3 Debug-first yaklaşım (PR #169)

- Hata mesajı semptom, **gerçek kök neden** için traceback şart
- `log.error(f"... {e}")` → `log.error(f"... {e}", exc_info=True)`
- 1 satır değişiklik, 1.5 saat kazandı

---

## 5. Deploy Recipe (Güncellenen, 2026-06-07 doğrulandı)

```bash
ssh root@efloud-bot
cd /opt/efloud-bot
git -c safe.directory=/opt/efloud-bot fetch origin
git -c safe.directory=/opt/efloud-bot reset --hard origin/master
docker compose -f docker-compose.prod.yml build --no-cache efloud-bot   # KRİTİK
docker compose -f docker-compose.prod.yml up -d
docker logs efloud-bot --tail 100
curl -s localhost:8080/healthz
```

**Image build 5-10dk sürer**. Eski container'lar recreate olur, yeni kod aktif.

**Pitfall**: Container restart (`docker compose restart`) YETMEZ. Image 4 saat önce build edildiyse 4 saat önceki kod çalışır. `docker inspect` ile doğrula.

---

## 6. Operatör Kararları (Beklemede)

### 6.1 Breaker tripped — 4 saat bekle

- 4 ardışık loss sonrası TRIPPED
- 4 saat sonra otomatik resume
- **Senin kararın**: bekle (güvenli)

### 6.2 Piyasa sinyali — Conf >= 50, R:R >= 1.8

- Bot loop alive, sinyal gelince Conf >= 50 ve R:R >= 1.8 gerekli
- Sinyal gelince trade girer, journal'a yazar
- DB bağlantısı yok → Supabase'a yazmaz, sadece file-based

### 6.3 DATABASE_URL — bekle veya restart

- Cloudflare DNS çözüyor, Google 8.8.8.8 hâlâ propagate olmamış
- 30dk daha beklemek gerekebilir
- **Şu an**: bot DB olmadan çalışıyor, journal kayıtları sağlam
- DB bağlantısı kurulunca trade'ler Supabase `trades` tablosuna yazılır, dashboard'da görünür

---

## 7. Memory / Skill Updates

### 7.1 Memory (tool eski, değiştirilemedi)

- `hermes memory` CLI sadece setup/status/off/reset destekliyor, **list/replace yok** (server-side)
- Yeni bilgi memory'ye eklenemedi
- **Elle düzeltme gerek** (operator on next session):
  - Entry 3: "Docker bind-mounts source, no image rebuild" → YANLIŞ, "Image baked-in, docker compose build --no-cache gerekli"

### 7.2 Skill (karpathy-guidelines)

- **P29** (image baked-in pitfall) — zaten ekliydi, detaylandırıldı
- **P30** (yanlış yere fix) — yeni eklendi (PR #170 deneyimi)
- **P31** (log f-string + exc_info) — yeni eklendi, 2 yere (line 928, 1952)

---

## 8. Test Coverage (PR #170 + #171)

| Test dosyası | Test sayısı | Kapsam |
|---|---|---|
| `tests/test_breaker_none_pnl.py` | 4 | breaker daily_pnl (PR #168, #170 yanlış tahmin) |
| `tests/test_lifecycle_none_pnl.py` | 5 | realized_pnl (PR #170 gerçek fix) |
| `tests/test_lifecycle_none_safety_sweep.py` | 11 | total_size, avg_entry_price, unrealized_pnl (PR #171) |

**Full suite**: 394 passed, 6 skipped, 0 failed.

---

## 9. Sıradaki (Sakin, Bekleme)

1. **PR #171 merge** (sen) → `https://github.com/Leblepito/efloud-bot/pull/new/fix/lifecycle-none-safety-sweep-bug-hunt-15`
2. **Hetzner deploy** (sen, image build 5-10dk):
   ```bash
   git reset --hard origin/master
   docker compose build --no-cache efloud-bot
   docker compose up -d
   ```
3. **Breaker tripped wait** (4 saat otomatik) veya piyasa sinyali
4. **DB bağlantısı** (DNS propagation bekle)
5. **Memory düzeltme** (tool çalışınca, elle)

**Sırada başka iş**:
- Memory entry 3 düzeltme (tool server-side eski)
- P32 skill (gerçek fix PR'da önce traceback al, sonra fix yaz) — zaten P31'de var
- Lane B consumer (P2/P19 — Lane A 0 emit, premature)

---

## 10. Referanslar

- `docs/handoff/2026-06-07_quant_walkthrough_session.md` — Quant fixes + walkthrough (önceki session)
- `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` — orijinal SMC spec
- PR #168, #169, #170, #171 commit'ler — bug-hunt zinciri
- `engine/lifecycle.py` (PR #170 + #171 hedef)
- `backend/bot_runner.py:511` (PR #169 — exc_info=True)
- `engine/safety/breaker.py:174` (PR #168 — yanlış yer, yine de zararsız)
