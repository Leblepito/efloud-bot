# M2 Chart-Export Manifest Consumer (P-002 M2)

## Amaç

Operatörün LOKAL makinesi (TV Desktop + CDP) M2 üretim yapar. VPS consumer
(`backend/social/tv_manifest.py`) sadece okur, validate eder, index'ler.

**Split:**
- Üretim (generate) → **operatör-lokal** (TV/CDP-bound, VPS'te browser yok)
- Tüketim (consume) → **VPS** (manifest oku, snapshot lookup, queue'ya besle)

## Senkron yöntemi

Operatör manifest dosyalarını VPS'e taşır:

```bash
# Lokalde üretildikten sonra (örnek):
# C:\tmp\m2-tv-export\manifests\2026-06-18_<runid>.json
# C:\tmp\m2-tv-export\manifests\latest.json          # alias

# VPS'e senkron (operatör tercih edilen yöntem):
# - scp/rsync
# - GitHub Releases asset upload
# - VPS-mount volume
# Default VPS path: /opt/efloud-bot/state/m2_manifests/
```

Override: `EFLOUD_M2_MANIFEST_DIR=/path/to/manifests`.

## Schema (tek item)

```json
{
  "symbol": "BTCUSDT",
  "tf": "15m",
  "ts": "2026-06-18T18:00:00Z",
  "snapshot_id": "K2GRzo5K",
  "share_url": "https://www.tradingview.com/x/K2GRzo5K/",
  "image_url": "https://s3.tradingview.com/snapshots/k/K2GRzo5K.png"
}
```

**`image_url`:** Anon TradingView CDN PNG, VPS'ten serbestçe embed edilebilir (GET 200 OK).
**`share_url`:** Public TradingView link, post footer'da "published on TradingView" notu.

## latest.json

Tüm aktif manifest'lerin array'i. Operatör üretim script'i her çalıştığında
günceller. Tüketim her zaman `latest.json`'ı okur (varsayılan).

```json
[
  { "symbol": "BTCUSDT", "tf": "15m", "...": "..." },
  { "symbol": "ETHUSDT",  "tf": "1h",  "...": "..." }
]
```

## VPS consumer API

```python
from backend.social.tv_manifest import (
    load_latest, build_index, resolve_chart_image, ManifestNotFoundError,
)

# 1. Yükle
try:
    snapshots = load_latest(manifest_dir=Path("/opt/efloud-bot/state/m2_manifests"))
except ManifestNotFoundError:
    snapshots = []  # manifest henüz düşmemiş

# 2. Index kur (latest-wins semantics)
idx = build_index(manifest_dir=Path("/opt/efloud-bot/state/m2_manifests"))

# 3. Renderer'a resolver olarak geç (DI)
from backend.social.tier2_renderers import render, pre_gate

rc = render(
    "signal_idea", "en",
    {
        "symbol": "BTCUSDT", "tf": "15m", "direction": "LONG",
        "structure": "OB retest",
        "entry": "64200", "sl": "63500", "tp1": "65400", "tp2": "66800",
        "rr": "1:2.6", "risk_pct": "1.1",
        # chart_img YOK → resolver otomatik çağrılır
    },
    chart_img_resolver=lambda s, t: resolve_chart_image(idx, s, t),
)

# 4. Pre-gate (her zaman)
violations = pre_gate(rc)
# boş liste == CLEAN → queue'ya enqueue
```

## Üretim tarafı (operatör-lokal)

Operatör production script'i:

1. TV Desktop + CDP ile login olur
2. Symbol+TF listesi için sırayla chart aç → snapshot share_url + image_url al
3. JSON manifest yazar:
   ```json
   [
     {"symbol": "BTCUSDT", "tf": "15m", "ts": "...", ...},
     {"symbol": "ETHUSDT", "tf": "1h",  "ts": "...", ...}
   ]
   ```
4. latest.json'ı overwrite eder
5. VPS'e sync (scp/git/release)
6. Image URL'lerin HTTP 200 olduğunu doğrular (verify_compliance.py gibi)

## Hata durumları

| Hata | Sebep | Çözüm |
|---|---|---|
| `ManifestNotFoundError` | latest.json yok | operatör üretim script'i çalıştırıp sync etsin |
| `ManifestSchemaError` (item) | required field eksik | üretim script'i validate etmeli (PR: schema gate) |
| `ManifestSchemaError` (top-level) | latest.json array değil | üretim script wrap edilmeli |
| `SnapshotNotFoundError` | (symbol, tf) lookup miss | latest.json'a ekle veya template'in symbol/tf'ini değiştir |
| Resolver raise | index.resolve fail | snapshot_id image_url 200 mü kontrol et |

## Tehlike sinyalleri

1. **Image URL 200 değil** → VPS'ten embed bozulur, TradingView snapshot silinmiş.
   Operatör yeniden export etmeli.
2. **Manifest 24 saatten eski** → eski snapshot, trade geçmiş olabilir.
   Operatör yeni manifest üretmeli.
3. **`snapshot_id` collision** → load_all dedupe yapıyor; latest-wins wins.
   Ama farklı (symbol, tf) → karışmaz.

## Test

```bash
python -m pytest backend/tests/test_tv_manifest.py -v       # 26 PASS
python -m pytest backend/tests/test_tier2_renderers.py -v    # 31 PASS (5 yeni integration)
python -m pytest backend/tests/ -q --tb=no                   # global regression
```

## Bilinmeyen / Bilinen TODO

- **Üretim script'i VPS'e konmaz** — operatör-lokal kalır (browser bağımlılığı).
- **Schema gate (PR ileride):** üretim script'inde manifest_schema validate etmeli,
  VPS consumer'a düşmeden hata vermeli.
- **Multi-source merge:** birden fazla üretici varsa load_all chronology'e göre
  dedupe yapar, latest-wins. Şu an tek üretici (operatör) varsayımı.
- **Image URL expiry:** TradingView CDN süresiz görünüyor (2024+ policy) ama
  takip edilmeli. Expired image → snapshot yeniden export.
