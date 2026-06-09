# Agent Scoreboard — Specialization Ledger

Son Güncelleme: 2026-06-09T14:30:00+03:00

> Append-only mantık. Her epic'in **UltraReview sürücüsü** kapanışta günceller (imzalı).
> **Proxy iş uzmanlaşma puanı KAZANDIRMAZ** (spec §7). Plan dağıtımı (Faz 1) bu rakamlara
> atıfla gerekçelendirilir; reviewer'lar Faz 2'de dağıtımı onaylar.

| Agent | Uzmanlık Alanı | DONE | Ort. Kalite | Review | Streak | Bug Buldu (+) | Bug Yedi (−) |
|---|---|---|---|---|---|---|---|
| **hermes** | Kod, plan, terminal, deploy | 1 | 95% | 0 | 1 | 0 | 0 |
| **claude** | Review, kod analizi, UltraReview, PR | 1 | - | 1 | 1 | 1 | 0 |
| **gemini** | Görsel doğrulama, büyük context, market-fit, tie-breaker | 0 | - | 0 | 0 | 0 | 0 |
| **manus** | Browser automation, QA *(opsiyonel voter)* | 0 | - | 0 | 0 | 0 | 0 |
| **codex** | Second opinion, challenge *(opsiyonel voter)* | 0 | - | 0 | 0 | 0 | 0 |

### Specialty Scores (alan-bazlı; epic'lerle birikir, dağıtım gerekçesinin kaynağı)
- **hermes:** {planning: 0, backend: 0, deploy: 0}
- **claude:** {review: 1, code-analysis: 1, ultrareview: 1}
- **gemini:** {visual: 0, market-fit: 0, tie-breaker: 0}
- **manus:** {browser: 0, qa: 0}
- **codex:** {second-opinion: 0}

---

## 📈 Son Aktivite Kayıtları (append-only, imzalı)
- **2026-06-09 12:45:** @hermes, P-001 (u2algo Master Plan) taslağını oluşturdu → `AWAITING_REVIEW`.
- **2026-06-09 13:52:** @gemini, LLTODO v2 mimari spec + iskelet implementasyonunu yazıp commit'ledi (91bbb6f).
- **2026-06-09 14:30:** @claude, v2 iskeletini onaylı spec v1.1'e yükseltti (3 consensus noktası, proxy protokolü, append-only+claim, branch registry, lint harness).
- **2026-06-09 15:00:** @claude, E-000 kapandı — 3-agent adversarial review (spec PASS / asks / consistency), tüm bulgular giderildi + reports/ gitignore bug'ı (agent raporları izlenmiyordu) yakalandı & düzeltildi → feat/zone-touch-confirmation'a merge.
