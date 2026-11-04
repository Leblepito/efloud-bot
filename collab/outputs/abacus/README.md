# outputs/abacus

abacus'in ürettiği paylaşılabilir çıktılar (rapor, analiz özeti, tablo). Yalnız abacus yazar.

- Dosya adı: `YYYY-MM-DD-<slug>.md` (ya da task çıktısıysa task'ta belirtilen ad).
- Her dosyanın başında: kaynak (dosya@sha / private store yolu), üretim zamanı (UTC), ilgili task id.
- Ham/büyük/üçüncü-taraf veri burada DEĞİL → private store (`collab/README.md` §5).

| Dosya | Task | Özet |
| --- | --- | --- |
| `2026-11-05-data-fetch-cadence.md` | T-20261105-01 | 15m REST vs websocket: iddialar doğrulandı; öneri (b) WS uyarı + event_scan, temas girişi yalnız shadow + ölçüm |
