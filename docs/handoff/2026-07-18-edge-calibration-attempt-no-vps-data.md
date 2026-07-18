# 2026-07-18 — C4/M1/M2 Kalibrasyon Denemesi: VPS VERİSİNE ERİŞİLEMEDİ → kalibrasyon başlatılmadı

**Oturum:** Zamanlanmış görev `edge-c4-m1-m2-calibration` (Cowork, otomatik/katılımsız run, 2026-07-18 ~09:00 UTC+7)
**Sonuç:** Veri yeterliliği DOĞRULANAMADI → görev kuralı gereği kalibrasyon başlatılmadı. Görev 2026-07-22 09:00'a kaydırıldı. Kod değişikliği YOK; bu doküman tek çıktıdır.

---

## 1. Neden veri yok (kanıt)

| Deneme | Sonuç |
|---|---|
| `ssh efloud-bot "…"` (sandbox) | `ssh: Could not resolve hostname efloud-bot` — alias + anahtarlar yalnız Windows'ta; Cowork sandbox'ında `~/.ssh` boş |
| Repo içi yerel kopya | `state_1k/` mevcut ama `signal_ledger.jsonl` YOK (breaker.json, trade_journal.jsonl, positions*.json var); `reports/` klasörü hiç yok; `find`: yalnız `engine/signal_ledger.py` |

Katılımsız run'da operatör de yoktu → SSH komutları çalıştırılamadı. Ledger yalnız VPS'te (`/opt/efloud-bot/state_1k/signal_ledger.jsonl`).

## 2. Operatör: 5 dakikalık veri adımı (bir sonraki run'dan ÖNCE)

```powershell
# 1) Hızlı bakış
ssh efloud-bot "cat /opt/efloud-bot/reports/edge_report.md"
ssh efloud-bot "wc -l /opt/efloud-bot/state_1k/signal_ledger.jsonl"
# (container içinden gerekirse)
ssh efloud-bot "cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml exec efloud-bot sh -c 'wc -l /app/state_1k/signal_ledger.jsonl; cat /app/reports/edge_report.md'"

# 2) SENKRON — bir sonraki zamanlanmış run'ın offline tamamlayabilmesi için:
scp efloud-bot:/opt/efloud-bot/state_1k/signal_ledger.jsonl C:\Users\utkuc\Downloads\efloud-bot\state_1k\
mkdir C:\Users\utkuc\Downloads\efloud-bot\reports 2>$null
scp efloud-bot:/opt/efloud-bot/reports/edge_report.md C:\Users\utkuc\Downloads\efloud-bot\reports\
```

> `signal_ledger.jsonl` VERİ dosyasıdır — COMMIT'LEME (gerekirse `.gitignore`'a ekle). Senkron sadece analiz içindir.
> Ayrıca VPS'te `EFLOUD_SIGNAL_LEDGER_ENABLED=1` gerçekten aktif mi teyit et — repo default'u `enabled: false` (configs/config.phase2_1k.yaml `signal_ledger:` bloğu); ledger 2026-07-04'ten beri yazmıyorsa bu görevin tüm takvimi kayar.

## 3. Veri geldiğinde karar matrisi (edge_metrics.py:45 eşikleri)

| Durum | Karar |
|---|---|
| `INSUFFICIENT EVIDENCE` veya resolved n < 30 (`min_n_print`) | Kalibrasyon YOK — görevi 1-2 hafta kaydır |
| 30 ≤ n < 100 (`underpowered`) | Sweep/atribüsyonu ÇALIŞTIR ama yalnız yön okuması; eşik/toggle KARARI verme |
| n ≥ 100 (`min_n_claim`, `ok`) + `edge_sign_stable` | C4/M1 kararları masaya gelir (operatör onayıyla) |

`NO VERDICT — edge sign unstable` çıkarsa timeout-marking üç panelde işaret tutmuyor demektir → önce timeout oranını incele, karar verme.

## 4. Bu oturumda DOĞRULANAN repo gerçekleri (kalibrasyonu şekillendirir)

1. **master = 567764b = origin/master** (push temiz; 2026-07-17 handoff'taki "3 lokal commit" bilgisi güncellenmiş durumda — hepsi push'lu).
2. **M1 fix'i ZATEN master'da, default-OFF:** `engine/signals.py:459` `fix_discovery_classification: bool = False`; mantık `:897-906` (`is_discovery = tp1_is_synthetic`); eski davranış byte-parite korunuyor. **Eksik olanlar:** (a) parametre config'e/lifecycle'a plumbing edilmemiş — hiçbir çağıran True geçmiyor, (b) toggle'a özel test yok, (c) etkilenen bucket'ın (ranging + gerçek-likidite TP1) NET etkisi ölçülmemiş. Yani M1'de "fix taslağı" işi bitmiş; kalan iş test + plumbing + VERİ + operatör kararı. **Yeniden implemente ETME.**
3. **Ledger post-gate kayıt yapıyor:** `engine/safe_orchestrator.py:1406-1414` — kayıt, `generate_signals` içindeki `min_confluence` gate'inden GEÇEN sinyaller için atılıyor (prod conf=50, configs/config.phase2_1k.yaml:129). **Sonuç: C4 sweep yalnız YUKARI yönde (50→55→…→80) yapılabilir; 50 altı counterfactual veri YOK.** Eşiği düşürme senaryosu istenirse önce "gate-öncesi kayıt" değişikliği gerekir (ayrı, default-OFF, risk-ops'lu iş).
4. **M2 için hammadde ledger'da var:** `SignalRecord.reasons` (bileşen listesi) + `confluence` + `hypo_r_net`. Ayrı araç yazmaya gerek kalmadan offline atribüsyon yapılabilir.
5. **Rapor üretici:** `scripts/routines/edge_report.py` (`INSUFFICIENT EVIDENCE` metni :9); breakdown bantları `edge_metrics.py:56-57` (55-65 / 65-75 / 75+); breakdown hücreleri UNCORRECTED (BH-FDR yok) — hücreden karar YASAK, primary = pooled NET.
6. **feat/audit-remediation (c0d6c60; C1-C3/H2-H4/M3-M4, default-OFF) master'a MERGE EDİLMEMİŞ** — C4/M1/M2 zaten bilinçli olarak veri-gate'li bırakılan üçlü. Bu branch'in merge kararı ayrı bir operatör konusu.

## 5. Veri gelince uygulanacak hazır analiz planı

**C4 — eşik sweep (yalnız yukarı yön):** ledger'ı `confluence ≥ T` için T ∈ {50,55,60,65,70,75,80} filtrele; her T için NET E[R], PF, Wilson CI, n ve sinyal/ay hızı. Karar önerisi çift koşul: (i) pooled NET E[R] anlamlı iyileşme, (ii) sinyal/ay operasyonel taban üstünde. `structural_score` telemetrisi (signals.py:656, H1) varsa sweep'i hem final hem structural skorla tekrarla — H1 bonus-floor etkisi ayrışır.

**M1 — sıra:** (1) failing test: ranging (htf_bias_original=UNDEF) + gerçek-likidite TP1 senaryosunda toggle=True → TP2=fib_ext beklenir, toggle=False → 2.618R (mevcut davranış parite testi); (2) plumbing: config `signals.fix_discovery_classification: false` → lifecycle → `generate_signals`; (3) ledger'dan etkilenen bucket payı + o bucket'ta TP2'ye ulaşma oranı (2.618R hedefi range'de gerçekleşiyor mu?); (4) risk-ops özeti + operatör ON kararı.

**M2 — atribüsyon:** `reasons` → 8 bileşen dummy'si (HTF-align, FVG, OTE, MTF-conf, SFP, OB[+near-swing/+EQ tek faktör olarak birleştir], zone, deviation) + bonus katmanı (sentiment/daily/level/stacked). Çıktılar: (a) bileşen-var/yok NET E[R] farkı + CI, (b) Spearman korelasyon matrisi, (c) OB üçlü-sayımının (+10/+5/+3=+18) tek-konsept katkısı. Amaç: NET katkısız bileşeni işaretlemek (Simplicity First) — skoru değiştirmek DEĞİL; skor değişikliği ancak sweep + operatör onayıyla.

## 6. Sözleşme hatırlatması (değişmedi)

NET-cost gate olmadan merge yok · trade path diff'i = risk-ops review + operatör onayı · önce failing test · toggle'lar default OFF · ledger/edge kodu trade path'ini bloklamaz (best-effort) kalır.

## 7. Sonraki run

Görev `fireAt=2026-07-22T09:00+07:00`'a kaydırıldı ve prompt'una yerel senkron fallback'i eklendi (Bölüm 2'deki scp adımı yapılmışsa katılımsız run kalibrasyonu offline tamamlar; yapılmamışsa yine bu duruma düşer ve tekrar kayar).
