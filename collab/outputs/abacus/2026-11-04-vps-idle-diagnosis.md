# VPS "bot işlem açmıyor" teşhisi (salt okuma)

- **Kaynak:** `ssh efloud-bot` → `docker ps`, `docker logs`, `docker exec ... env|tail` (yazma yok). VPS saati 2026-11-04 ~20:20 UTC. VPS HEAD `b6c6bd1`, master `6bea1e4` (fark yalnız collab/test/doküman).
- **Son giriş:** `state_1k/trade_journal.jsonl` son satırı SOL LONG, 2026-11-03 06:45 UTC → ~37 saattir yeni giriş yok.

## Bulgular
1. **scalp ve long botlar boşta.** İkisinde `EFLOUD_AUTOSTART=0` ve son 30 dk'da 0 tarama döngüsü (yalnız `/healthz`). "healthy" yalnız HTTP sağlığıdır; döngü çalışmıyor. Claude'un T-20261104-07 bulgusuyla aynı. Başlatma canlı yazmadır → operatör.
2. **mid (`efloud-bot`) çalışıyor ve tarıyor** (15 dk'da bir, 10 sembol; `[lux] scan` satırları). Girmeme sebebi hata değil, politika/piyasa:
   - HTF (12h) çoğu sembolde BULL, fiyat geri çekilmeden yükseldi; bekleyen adaylar bölgesine dokunmuyor.
   - Son 24 saatte 22 aday `max_entry_dist_atr 12.0` kapısında düştü (19 LONG, 3 SHORT; örnekler 12.5–13.7 ATR uzakta, BTC/ETH LONG).
   - v1 sinyal yolu `R:R<1.8` ile reddediyor (max görülen 0.5–0.9).
   - TRX'te rejim `RANGING` → "Trading disabled".
3. **Gürültü:** `publishing_worker: DB pool not ready` her dakika (3 bot). İşlem etkisi yok görünüyor; sosyal yayın DB'si yoksa uyarıyı kısmak ayrı iş.
4. **VPS güncelliği:** master'daki fark yalnız `collab/**`, `tests/collab/**`, `AGENTS.md`/`HERMES.md` → runtime için deploy gerekmiyor. #275 (`engine/safe_orchestrator.py`, `ops/alerter/*`) henüz merge değil; merge sonrası deploy ticket + operatör onayı ister.

## Öneri (operatör kararı)
- scalp/long başlatma: T-20261104-07 (autostart kalıcı mı elle mi karar).
- `max_entry_dist_atr 12→?` ayarı NET-cost kanıtı olmadan değiştirilmemeli; T-20261104-09 sonucunu bekle.
- Not: Claude'un log girişleri 21:05 UTC yazıyor, VPS saati 20:20 → zaman damgaları tutarsız; doğrulanmadı.
