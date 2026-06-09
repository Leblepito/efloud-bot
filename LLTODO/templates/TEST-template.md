---
test_id: TEST-XXX-{tester}-tests-{testee}
plan_id: P-XXX
tester: hermes | claude | gemini
testee: hermes | claude | gemini
verdict: PASS | BUGS_FOUND
created: YYYY-MM-DDTHH:MM:SS+03:00
confirmed_by: null        # BUGS_FOUND, FIX'e dönüşmeden önce 2. bir agent onayı (3. consensus noktası)
---

# Cross-Test: {tester} → {testee}

## Test Edilen Görevler
| Task | Açıklama | Test Sonucu |
|------|---------|------------|
| T-XXX | ... | ✅ PASS |

## Bulunan Hatalar (yalnızca `confirmed_by` dolunca FIX'e dönüşür)
| # | Task | Hata | Severity | Fix Önerisi |
|---|------|------|---------|------------|
| 1 | ... | ... | MEDIUM | ... |

## Karar
[Karar gerekçesi: PASS | BUGS_FOUND]
