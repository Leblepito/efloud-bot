# 2026-06-04 facts to remember (memory tool arızalı, dosyaya yazıyorum)

Bu session'da memory tool'u 7+ denemede "old_text is required" döndü (parametre
gönderildi, JSON parse muhtemelen başarısız). Aşağıdaki bilgiler ileride
memory'ye veya skill'e taşınmalı:

1. **Master HEAD 2026-06-04: `304daea`.** Handoff 2026-06-03 "3fa88b8" diyordu
   ama arada 50+ PR merge edildi.

2. **PR #99 fix/sltp-delivery-reliability merged 2026-05-28 13:59:40 UTC.**
   Handoff "PR bekliyor" yazıyordu — yanlış, artık merged.

3. **Toplam 154 PR merge edildi** (handoff zamanı ~75'ti).

4. **Hetzner VPS HEAD'i doğrulanmadı.** Handoff "muhtemelen d03857c" diyordu.
   Production master ile senkron mu, yoksa hâlâ eski mi? `git -c safe.directory
   pull` sonrası değişir.

5. **HERMES.md içeriği stale.** "fix/sltp-delivery-reliability (YENİ — 2026-05-28,
   PR bekliyor)" yazıyor. Güncellenmeli veya "merged" yazmalı.

6. **u2algo-site Railway deploy hazırlığı tamamlandı (2026-06-04):**
   - Rehber: `docs/handoff/2026-06-03_railway_frontend_deploy_runbook.md`
   - Local smoke OK (Node 24.13.0, 42738 bytes, compliance gate passed)
   - Local healthz 200, waitlist health no-supabase → `database: "not_configured"`
   - Repo master=origin master (304daea), u2algo-site/ clean
   - Port 3099'da test server hâlâ çalışıyor (PID 46336, user öldürmedi)

7. **Memory tool bug** bu session'da raporlanmadı. Bir dahaki session'da test et.

## Eklenecek skill'ler (ileride)

- **railway-monorepo-deploy**: Monorepo'da alt dizin deploy etme (Root
  Directory, nixpacks.toml, env yönetimi)
