# outputs/claude-code

claude-code'in ürettiği paylaşılabilir çıktılar (rapor, analiz özeti, tablo). Yalnız claude-code yazar.

- Dosya adı: `YYYY-MM-DD-<slug>.md` (ya da task çıktısıysa task'ta belirtilen ad).
- Her dosyanın başında: kaynak (dosya@sha / private store yolu), üretim zamanı (UTC), ilgili task id.
- Ham/büyük/üçüncü-taraf veri burada DEĞİL → private store (`collab/README.md` §5).

| Dosya | Task | Özet |
| --- | --- | --- |
| `2026-11-04-lux-gate-counterfactual.md` | T-20261104-09 | 60 gün NET-cost: kapıları gevşetmek için kanıt yok; baz motor akışı −0.30 R/işlem (maliyet ~0.27 R); mitige OB retest +0.24 R (n=30, sınırda) |
| `2026-11-04-ob-entry-gap.md` | T-20261104-07/08/09 | Chart LuxAlgo OB'leri vs. motor: dokunuşların %78'inde aday yok (12h trend %45); erken uyarı önerisi |
| `2026-11-07-llm-agent-layer-audit.md` | T-20261107-16 | LLM'in işlem kararına giden tek yolu: sentiment ±5 giriş eşiğinden önce (A1) — prod'da yol uyuşmazlığıyla pasif (A2), operatör kararı; CRITICAL uyarılar LLM'le yeniden yazılıyor (A3/A4) |
| `2026-11-07-backend-db-llm-cost.md` | T-20261107-22 | Backend/DB sağlıklı (Supabase waitlist ready, CLAUDE.md bayat); yapı doğrulama LLM çağrısı 19 günde 23.085/23.085 fallback (sağlayıcı çözümleme hatası), alerter formatlayıcı da hep ham — etkinleştirme önerilmez |
| `2026-11-07-backtest-live-parity.md` | T-20261107-24 | Restored backtest on live logic: 8 of 10 live entries since 11-02 reproduced (same direction, one bar earlier, same outcome); 41 d × 10 symbols NET −0.91 % (PF 0.69); backtest breaker wall-clock bug fixed (live unchanged) |
