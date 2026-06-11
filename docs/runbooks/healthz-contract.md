# Runbook: /healthz Kontratı + Uptime Metriği Tasarımı (T-024 / P-003 W-R)

> **Amaç:** `/healthz`'nin mevcut (tasarım gereği DOĞRU) semantiğini harici monitörler ve
> uptime raporlaması için kontrata bağlamak. **Bu doküman healthz davranışını DEĞİŞTİRMEZ** —
> davranış `backend/healthz.py`'de tanımlı ve test edilmiştir; burası tüketici kontratıdır.
> **Tüketiciler:** T-021 (status page / external monitor — GÖREV E), T-012/T-014 (proof
> snapshot uptime alanı), autoheal, alerter.

## 1. Durum Matrisi (kaynak: `backend/healthz.py`)

| HTTP | `status` | `failures` | Anlamı | Autoheal | Monitör yorumu |
|---|---|---|---|---|---|
| 200 | `ok` | `[]` | Loop canlı (≤90s), exchange erişilebilir (≤60s), fatal exception yok | dokunmaz | **UP** |
| 200 | `suspended` | `["breaker_halted"]` | Circuit breaker HALTED — **kasıtlı** durdurma (örn. haftalık DD eşiği); yalnız operatör `manual_reset` çözer | dokunmaz (restart ÇÖZMEZ) | **DEGRADED** — "servis up, trading suspended". ASLA "operational" gösterme; ASLA "down" da değil |
| 200 | `suspended` | `["crash_loop_suspended"]` | 30dk'da ≥N crash → bot kendini askıya aldı; operatör müdahalesi gerekir (`docs/runbooks/crash-loop-recovery.md`) | dokunmaz | **DEGRADED** (üstteki gibi) |
| 503 | `unhealthy` | `loop_tick_never` / `loop_tick_stale(Nms)` | Ana döngü 90s'dir tick atmadı | **restart eder** (transient) | **DOWN** |
| 503 | `unhealthy` | `exchange_ping_never` / `exchange_ping_stale(Nms)` | Exchange bağlantısı 60s'dir doğrulanmadı | restart eder | **DOWN** |
| 503 | `unhealthy` | `fatal_exception` | Yakalanmamış cycle exception'ı | restart eder | **DOWN** |
| 503 | `unhealthy` | `healthz_not_configured` | Startup yarışı — endpoint wire-up'tan önce vuruldu | restart eder | **DOWN** (kısa süreli normal) |

**Tek cümlelik kontrat:** *HTTP koduna bakmak YETMEZ — 200 hem "ok" hem "suspended" dönebilir.
Monitör JSON `status` alanını parse ETMEK ZORUNDA; `suspended` ≠ up ve ≠ down: "degraded".*

Bu tasarım bilinçlidir (healthz.py docstring): HALTED'da 503 dönülseydi autoheal, restart'ın
çözemeyeceği bir durumda container'ı restart-loop'a sokardı. Alerter zaten `failures` alanını
okuyarak operatörü bilgilendirir.

## 2. T-021 Monitör/Status-Page Kontratı (GÖREV E girdisi)

1. Probe, body'deki `status` alanını keyword-match edebilen bir sağlayıcı olmalı
   (yalnız HTTP-code'a bakan sağlayıcı ELENİR — trading durmuşken "operational" gösterir).
2. Üç durum eşlemesi: `"status":"ok"` → Operational · `"status":"suspended"` → Degraded
   (açıklama: "trading suspended by safety system") · diğer her şey / timeout → Down.
3. **Exposure mekaniği:** bot container'ı portu host'a publish ETMEZ; dış erişim Caddy
   üzerinden. Public probe için iki seçenek (GÖREV E kararı):
   a. Caddy'de `/healthz`'i public path olarak aç — ama `failures`/`checks` alanları
      operasyonel detay sızdırır (eşik değerleri, crash durumu) → ÖNERİLMEZ;
   b. **Önerilen:** filtrelenmiş yüzey — yalnız `{"status": "..."}` döndüren küçük bir
      proxy path (Caddy response-rewrite veya T-014 statik snapshot'ından beslenen alan).
4. Bu kontrat dokümanı sağlayıcı konfigürasyonunda referans gösterilir (T-021 acceptance).

## 3. Uptime Metriği Tasarımı (T-012/T-014 besleme — UR-003 düzeltmesi uygulanmış hali)

**KULLANILMAYACAK kaynak:** `state/alerter_heartbeat.json` — tek timestamp'tir (yüzde
türetilemez) ve ALERTER sidecar'ının canlılığını ölçer, trading bot'un değil
(bot down + alerter up → heartbeat taze kalır).

**Tasarım — healthz-türevi sampling:**

1. `proof_export.py` cron'u (T-012) her koşuda `/healthz`'i localhost'tan örnekler.
2. Örnek `state/uptime_samples.jsonl`'a append edilir: `{"ts": ..., "status": "ok|suspended|unhealthy|unreachable"}`
   (unreachable = endpoint'e ulaşılamadı; append-only, T-020 backup kapsamına girer).
3. Pencere bazında (30/90 gün) İKİ ayrı metrik türetilir — birbirine KARIŞTIRILMAZ:
   - **`service_uptime_pct`** = (ok + suspended) / toplam — "servis ayakta mıydı"
   - **`trading_active_pct`** = ok / toplam — "trading fiilen açık mıydı"
4. Public yüzeyde (T-014) ikisi ayrı adlarla gösterilir; `suspended` dönemleri "safety
   suspension" olarak etiketlenir — bu bir hata değil, ürünün güvenlik özelliğidir
   (pazarlama açısından da doğru çerçeve).
5. Örnekleme cadence'i proof_export cron'una eşittir (≥günlük, G-P3-1 sınırı); daha sık
   örnekleme istenirse ayrı hafif cron — ama public YAYIN cadence'i yine G-P3-1'e tabidir.

## 4. Mevcut Tüketicilerin Doğru Davranışları (değişiklik YOK — referans)

- **autoheal** (`willfarrell/autoheal`, docker-compose.prod.yml): yalnız Docker healthcheck
  durumuna bakar; 200/suspended → healthy sayar → restart etmez. ✓ doğru.
- **alerter** (`ops/alerter/`): healthz'i 30s'de yoklar, `failures` alanını kurallarla
  eşler, Telegram'a bildirir. ✓ doğru.
- **Dashboard** (`frontend/`): `/api/status` üzerinden ayrı durum gösterir; healthz'e bağımlı değil.

## 5. Sınırlar

- Eşikler (90s loop / 60s ping) `backend/healthz.py` sabitleridir; değişiklik = kod PR'ı
  + risk-ops review (bu runbook'un kapsamı dışında).
- `healthz_not_configured` startup'ta birkaç saniye görülebilir — monitör 2-3 ardışık
  örnek üzerinden alarm üretmeli (tek örnekle flap etmemeli).
