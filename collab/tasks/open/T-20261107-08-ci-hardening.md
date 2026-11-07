---
id: T-20261107-08
title: CI sertleştirme — reviewer'ı base branch'ten çalıştır, SDK pin, input env, gitleaks baseline manuel
from: claude-code
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: T-20261106-06
created: 2026-11-07
touches_live: false
---

## Amaç
Güvenlik denetimi (T-20261106-06) fix #4. Repo PUBLIC; CI'da üç zayıflık.

## Değişiklik
1. `claude-review.yml` — `ANTHROPIC_API_KEY` taşıyan job'lar artık **yalnız `pull_request_target`**
   ile çalışır: workflow tanımı + checkout **base branch'ten** gelir (önceden `pull_request`'te
   PR kendi workflow kopyasını düzenleyip anahtarı sızdırabilirdi). PR kodu hiç checkout
   edilmez/çalıştırılmaz; diff `gh pr diff` ile **veri** olarak okunur. Fork PR'ları atlanır
   (`head.repo.full_name == github.repository`; önceden de review almıyorlardı).
   `anthropic==0.117.0` (= `constraints.txt`), `dorny/paths-filter` commit SHA'sına sabit (v3.0.4),
   `PR_NUMBER`/`GH_REPO` env ile. `scripts/ci/claude_review.py`: diff alınamazsa (API çok büyük
   diff'i 406 ile reddeder) job düşmez, "manual review required" yorumu bırakır.
2. `hermes-review.yml` — `issue_number` girdileri shell'e satır içi `${{ }}` yerine env ile.
3. `scheduled-review.yml` — gitleaks auto-baseline yalnız manuel `workflow_dispatch`'te; PR
   başlığı/gövdesi "her birini rotate etmeden merge etme" diyor.

## Beklenen çıktı (Definition of Done)
- [x] `tests/ci/test_workflow_hardening.py` — 3 tur RED→GREEN, son hali 10 passed
- [x] Tüm workflow YAML'ları parse ediliyor
- [x] Review (security-reviewer: tur 1 CHANGES — workflow dosyası PR'dan okunuyordu → `pull_request_target`'a geçildi; tur 2 APPROVE_WITH_NITS → nit'ler uygulandı)

## Kısıtlar
- Yalnız 3 workflow + `scripts/ci/claude_review.py` + yeni test + collab dosyaları.
- Takip (önceden var olan, kapsam dışı, işaretlendi): `hermes-review.yml` "Close resolved tracking
  issue" adımının son satırı tanımsız `$ISSUE_NUM`'a yorum atıyor (birleştirme artığı gibi).
- Takip (LOW): diğer action'lar tag ile (`actions/*@v4/v5`; secret'lı job'daki `dorny/paths-filter` artık SHA'ya sabit),
  `ruff bandit pip-audit` sürümsüz, gitleaks image tag ile — SHA/digest pin + Dependabot ayrı iş.

## Log
- 2026-11-07 claude-code: tur 1 (base-ref script) → review CHANGES → tur 2 `pull_request_target` + API diff → APPROVE_WITH_NITS → nit'ler; 10 test geçti, YAML OK.
- Merge sonrası doğrula: risk/SMC yollarına dokunan ilk aynı-repo PR'ında iki review job'u yorum bırakıyor mu (paths-filter + `gh pr diff`).

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
