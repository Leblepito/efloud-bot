# LB-001 — Bot V2 Binance API-key permission posture (DECIDE)

| Alan | Değer |
|---|---|
| Mode | DECIDE |
| Requested-by | @claude |
| Date | 2026-06-20 |
| Status | LEBLEP_REQUESTED |

## Context (self-contained — Leblep repo'yu bilmiyor varsay)
efloud-bot, Hetzner tek-VPS'te (Ubuntu, docker) çalışan canlı bir Binance Futures trading botudur. İki paralel instance kurulacak: V1 (profile mid, ~$1035) + V2 (profile long, ~$1035, yeni Binance hesabı). Botun Binance API key'i **plaintext** olarak VPS'teki `.env.production` dosyasında durur (KMS/Vault yok; mitigantlar: `gitleaks` CI repo-tarama + dosya `chmod 600`). Bot order vermek için yalnızca **trade (futures) yetkisi**ne ihtiyaç duyar; para çekme/transfer botun çalışması için gerekli DEĞİLDİR. `preflight.py` canWithdraw=true ise **uyarır ama bloklamaz**.

**Operatör duruşu (2026-06-20):** "Bot V2'ye IP kısıtlaması koymayacağım; çekim (withdraw) ve transfer izni de açık olabilir, problem yok."

**Audit bulgusu (Track-A S1):** plaintext .env secret'ının TEK büyük mitigasyonu `canWithdraw=false`. Bu açılırsa, key sızması (VPS compromise, yanlış log, yedek sızıntısı) → saldırgan **fonu çekebilir/transfer edebilir** = toplam sermaye kaybı (sadece kötü trade değil). IP-whitelist ücretsiz + güçlü ikinci katman.

## Question / Task
Bot V2 (ve V1) Binance API key'i için **güvenlik duruşu** ne olmalı? Operatörün "withdraw+transfer açık + IP-whitelist yok" duruşu vs audit/risk-ops önerisi "canWithdraw=false + VPS-IP whitelist". Çok-model (GPT-5.5 + Minimax-M3 + DeepSeek-V4-Pro) ortak kararı + gerekçe. Tehdit modeli: plaintext .env, tek-VPS, ~$2070 toplam sermaye, bot withdraw'a ihtiyaç duymuyor.

## Hard constraints
- Bot order vermek için withdraw/transfer GEREKMEZ (sadece futures-trade yetkisi).
- Karar operatörün; bu bir **ikinci-görüş danışma** (Claude'un risk-ops görüşü: canWithdraw=false + IP-whitelist; ama operatör aksini istedi → çok-model adversarial check istiyoruz).
- Trade-path/kod değişmez; bu bir konfigürasyon/operasyon kararı.

## Output format (DECIDE)
- Tek net tavsiye (canWithdraw aç/kapa; IP-whitelist evet/hayır) + gerekçe.
- Reddedilen alternatif(ler) ve neden.
- Eğer "withdraw açık" savunulabilirse, hangi telafi edici kontroller (ek mitigant) şart.
- Beklenen-kayıp / saldırı-yüzeyi kıyası (kısa, niceliksel olabilir).

## Acceptance (@claude değerlendirmesi)
Claude yanıtı adversarial review eder: tehdit modeli gerçekçi mi, "withdraw kapalı + IP-whitelist" önerisini güçlü gerekçe olmadan reddediyorsa sorgular. Kabul edilen karar operatöre net tek-cümle tavsiye + gerekçeyle sunulur; operatör nihai kararı verir.
