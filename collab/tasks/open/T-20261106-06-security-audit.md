---
id: T-20261106-06
title: Güvenlik denetimi — repo, git geçmişi, harness/CI, uygulama, deploy
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: T-20261106-04
created: 2026-11-06
touches_live: false
---

## Amaç
ECC skill backlog madde 2 (`T-20261106-04`). Repo PUBLIC olduğu için kapsamlı güvenlik
denetimi: sır taraması (güncel ağaç + tüm geçmiş), harness/CI/MCP, internete açık uygulama
yüzeyi, deploy ve bağımlılıklar. Bu PR yalnız denetim kaydıdır; düzeltmeler ayrı PR'lar.

## Girdi
- Ayrıntılı rapor: private store `~/efloud-collab-private/security-audit-2026-11-06/REPORT.md`
  (repo'ya girmez — istismar ayrıntısı public'e yazılmaz, `collab/README.md` §1/§5).
- Skill'ler: ecc-security-review, security-bounty-hunter, agent-security-hardening,
  mcp-dependency-review.

## Yöntem (özet)
- Sır taraması: regex tarayıcı (network yok) güncel ağaç + `git log -p --all` (1487 commit).
  Değerler hiçbir yere yazılmadı; yalnız parmak izi.
- Canlı doğrulama: sızmış değerlerin sha256 özetleri VPS'e gönderildi, 7 env dosyası +
  6 container env'i (229 anahtar/değer) ile karşılaştırıldı → **0 eşleşme** (rotasyonlu).
- Uygulama: route/auth haritası, statik servis, webhook, panel, CORS/çerez, tehlikeli sink grep.
- Deploy: dış portlar, UFW, sshd, container yetkileri, Caddy başlıkları; bağımlılık için CI'ın
  günlük pip-audit/npm-audit çıktısı.

## Sonuç (nötr özet)
| Alan | Durum |
|---|---|
| Sırlar | Geçmişte eski sırlar var; canlıda hiçbiri kullanılmıyor (doğrulandı). Güncel ağaçta 1 şüpheli test değeri → fix PR |
| Backend API | Sağlam: auth/rate-limit/çerez/CSRF/WS doğrulama yerinde; tehlikeli sink yok |
| u2algo-site | Statik servis kapsamı + waitlist rate-limit sertleştirilecek → fix PR |
| Panel | POST istek koruması + deneme limiti eklenecek (şu an deploy değil) → fix PR |
| Harness/CI | live-write gate kapsamı genişletilecek; CI'da sürüm pin + review script kaynağı → fix PR'lar |
| Deploy | Ağ dışa kapalı (yalnız 80/443/22, UFW); sshd ve container sertleştirme önerileri operatöre |
| Bağımlılık | Python temiz; frontend npm güncellemesi (prod statik export → etkisi sınırlı) → fix PR |

## Beklenen çıktı (Definition of Done)
- [x] Denetim + private rapor
- [x] Canlı sır kullanımı doğrulaması (0 eşleşme)
- [ ] Fix PR'ları (private rapordaki "Önerilen fix PR sırası" 1–7), her biri ayrı task/PR
- [ ] Operatör eylemleri (private rapordaki liste)

## Kısıtlar
- Bu PR'da kod/config değişikliği yok.
- Harici tarayıcı (gitleaks) indirmesi izin sınıflandırıcısı tarafından engellendi; CI'daki
  günlük gitleaks taraması ayrıca mevcut.

## Log
- 2026-11-06 claude-code: S1–S6 denetim tamamlandı; private rapor yazıldı; VPS özet karşılaştırması 0 eşleşme.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
