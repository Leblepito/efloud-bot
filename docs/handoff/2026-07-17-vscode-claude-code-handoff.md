# 2026-07-17 Cowork → VS Code (Claude Code) Handoff

> Cowork cloud oturumu 2026-07-17'de iki turda 27 bug/iyileştirme uyguladı ve
> **7 commit** üretti. İlk 4'ü (d7219cc..4b480c7) operatör oturum sırasında
> push'ladı; kalan 3 (bf09522/872ee27/b3823ba + bu doküman commit'i) LOKAL —
> sandbox'ta credential yok. GÜNCEL sayıyı her zaman `git log --oneline
> origin/master..HEAD` belirler. Bu doküman TEK devir kaydıdır. Kanıt standardı:
> her iddia `git log` / grep / test çıktısıyla doğrulanabilir durumda.

## 1. Mevcut Durum (doğrulanmış)

- Branch: `master`, origin/master'ın **7 commit önünde**:
  - `d7219cc` fix(routines+alerting) — R-1/R-3/R-4/R-6/R-7/R-8/R-9/R-10/R-12 + ccxt/pandas drift
  - `2a307d0` fix(exchange+engine) — **B-1 TP-stacking guard**, E-1/E-2/E-3/E-4/E-5(drain)/E-6
  - `2888ac2` fix(backend) — B-2/B-3/B-4/B-6/B-8/B-11
  - `4b480c7` docs(reviews) — bulgu tablosu
  - +3 yeni (bu oturumun 2. turu): fix(routines+backend) R-2 tamamlama + B-9/B-10/R-11/R-14 + compose `EFLOUD_STATE_DIR`; chore(deps+deploy) constraints.txt + Dockerfile pin + B-5 proxy-headers; docs(handoff) bu doküman.
- Test kanıtı (cloud, python 3.11): `tests/` **628 passed** / `backend/tests`
  **1550 passed**, 0 failed — hem serbest ortamda hem `constraints.txt`'in
  pinlediği sürümlerle temiz venv'de birebir aynı sonuç.
- Bulgu detayları: `docs/reviews/2026-07-17-full-repo-review-findings.md`.
- Working tree'de bazı dosyalar `git status`'ta "M" görünebilir — **yalnız CRLF**
  (mount artefaktı). Doğrulama: `git diff --ignore-cr-at-eol HEAD` boş olmalı.
  Bunları COMMIT'leme; sadece push yeterli.

## 2. Claude Code Görevleri (sırayla)

### T1 — Push (5 dk)
```
git log --oneline origin/master..HEAD   # kalan commit'leri doğrula (yazım anında 3)
git diff --ignore-cr-at-eol HEAD --stat # boş/CRLF-only olmalı — yeni commit ATMA
git push origin master
```

### T2 — Docker gate (resmi doğrulama)
`.\scripts\run_tests_docker.ps1` → beklenen: **0 failed** (sayı eski 605'ten
yüksek olacak; bu oturum +28 test ekledi). Ek olarak `python -m pytest
backend/tests -q` → 1550 passed beklenir. Herhangi bir FAIL çıkarsa DUR,
kırığı raporla — cloud'da her ikisi de yeşildi; fark ortamsal demektir.

### T3 — VPS deploy (image REBUILD zorunlu)
Dockerfile değişti (constraints pin + uvicorn `--proxy-headers`) → sadece
`up -d` yetmez:
```
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```
`routines-watcher`/`routines-scheduled` recreate olmalı (yeni
`EFLOUD_STATE_DIR=/app/state_1k` env'i — breaker/position audit'in canlı
state'i görmesi buna bağlı). Deploy sonrası 24h gözlem listesi:
1. Breaker alarm zinciri: `efloud-routines` loglarında breaker_watch artık
   `state_1k/breaker.json`'ı okuyor mu (rapor: `reports/breaker_watch.md`
   Current State alanı OPEN göstermeli, N/A değil).
2. position_audit false "Position Drift"/"Bare Position" CRITICAL'leri durdu mu.
3. `/api/login` rate-limit: operatör girişi normal; loglarda 429 fırtınası yok.
4. Dashboard WS event gecikmesi düştü mü (pozisyon aç/kapa anında yansımalı).

### T4 — Kalan işler (Cowork'un YAPMADIKLARI — tasarım/karar veya Windows gerekli)
| # | İş | Neden devredildi |
|---|-----|------------------|
| B-7 | `backend/pubsub_consumer._dispatch_signal` orchestrator gate'lerini (breaker/max-pos/confluence) bypass ediyor + size 0 "auto-sizing" yorumu asılsız | Şu an inert (pubsub disabled) ama tasarım kararı ister: orchestrator üzerinden route mu, minimal breaker+size guard mı — operatöre sor |
| R-13 | `ops/overseer/rules.py` 3 kural hiç emit edilmeyen event'leri eşliyor (`cycle_start` vb.), `ts`'i int sanıyor (ISO string), compose journal path'i emekli aggressive instance'a bakıyor | Bot loop'una structured event emit etmek canlı log yüzeyini değiştirir; kurallarla birlikte tek PR olmalı |
| E-5 | breaker `record_trade_correction` ledger eşleşmesi float-value ile — trade_id-match'e geçirilmeli (ledger dict'lerine id alanı) | Feature default-OFF; açılmadan önce yapılmalı, breaker'a dokunur → risk-ops review |
| R-12+ | Rutin import hatası artık loud-log; bir de tek-seferlik Telegram startup alert'i eklenebilir | Küçük; alert fırtınası tasarımıyla birlikte |
| W2 | Master plan Hafta-2: Pazartesi `python -m scripts.prefetch_data` + C1/C2 (smc_v2 eksen + stale engulfing) backtest-gate'li fix'ler | Gate + 1000-bar koşuları Windows ister |
| W5 | gitleaks TARİH taraması, pip-audit/npm audit, exchange key sertleştirme, bandit/semgrep, log hijyeni | Plan Hafta-5; secrets rotasyonu operatör işi |

### T5 — Kurallar (değişmedi)
Dev sözleşmesi: `CLAUDE.md` Karpathy maddeleri + `docs/dev/karpathy-guidelines.md`.
Önce failing test; cerrahi diff; `@pytest.mark.skipif` YASAK; guard/breaker/orphan
zayıflatma YASAK; canlı mantık diff'i → risk-ops review + operatör onayı.
Windows'ta normal git akışı serbest (Cowork mount kuralları orada geçersiz).

## 3. Yapıştır-kullan prompt (VS Code Claude Code)

```
efloud-bot devir oturumu. Önce şu iki dokümanı oku:
docs/handoff/2026-07-17-vscode-claude-code-handoff.md (görev sırası) ve
docs/reviews/2026-07-17-full-repo-review-findings.md (ne değişti).
Dev sözleşmesi: CLAUDE.md + docs/dev/karpathy-guidelines.md.

GÖREVLER (sırayla, her biri kanıtla raporlanır):
T1: git log --oneline origin/master..HEAD ile KALAN commit'leri doğrula;
    git diff --ignore-cr-at-eol HEAD boş mu bak (CRLF artefaktı commit'leme);
    git push origin master.
T2: .\scripts\run_tests_docker.ps1 koş → HAM özet satırını rapora koy
    (0 failed bekleniyor). Ardından python -m pytest backend/tests -q →
    1550 passed bekleniyor. FAIL varsa DUR ve raporla.
T3: VPS'te: docker compose -f docker-compose.prod.yml build && up -d
    (Dockerfile değişti — rebuild ZORUNLU). Sonra handoff Bölüm T3'teki
    4 maddelik 24h gözlem listesini kontrol et ve raporla.
T4: Kalan işlerden YALNIZ operatörün seçtiklerine başla (B-7 ve R-13 önce
    kısa tasarım notu ister; E-5 risk-ops review'lu). Kapsam dışına çıkma.
Kanıt formatı: T{n}: DONE/BLOCKED — komut + ham sonuç satırı — commit hash.
"✅ tamamlandı" tek başına geçersiz.
```
