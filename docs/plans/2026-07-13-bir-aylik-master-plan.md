# EFloud-Bot — 5 Haftalık Master Plan (Batch-2 → Test → Security)

> **Hazırlayan:** Claude Fable 5 (planlama oturumu, 2026-07-13)
> **Yürütücüler:** Kilo Code (ana implementasyon, Windows/VS Code) + Abacus.ai (review/analiz) + Operatör (Utku)
> **Kaynaklar:** `docs/handoff/2026-07-12-batch2-session-prep.md`,
> `docs/reviews/2026-07-11-full-repo-review-findings.md`, `CLAUDE.md`,
> `docs/dev/karpathy-guidelines.md`
> **Süre:** 13 Temmuz – 18 Ağustos 2026 (5 hafta + kapanış)

---

## 0. Operatör Kararları (prep dokümanı Bölüm 3 — DOLDURULDU)

Bu kararlar 2026-07-13 planlama oturumunda, prep dokümanındaki önerilere dayanarak
operatör adına verildi. Operatör itiraz ederse ilgili kalem başlamadan bu tablo güncellenir.

| # | Soru | Karar | Gerekçe |
|---|------|-------|---------|
| 1 | A1 tighten-stops | **KALDIR** — ölü gate silinir, findings'e "bilinçli yok" notu düşülür; "exchange SL-amend altyapısı" ayrı backlog issue olarak açılır | Amend altyapısı büyük iş + canlı SL yönetimine dokunur. Ölü kod karmaşıklıktır (Simplicity First). 30 dk vs günlerce iş |
| 2 | A2 intent weakness | **Flag'le canlandır:** `intent_weakness_exit: false` default-OFF + **shadow-log modu** (yalnız loglar, emir GÖNDERMEZ). 30 gün veri → ~1 Eylül'de ON/OFF kararı | Davranış verisi olmadan de-risk agresifleştirme kararı verilemez |
| 3 | A3 dedup quantize | **ONAY** — tick-size-relative quantize, `dedup_tick_quantize: false` default-OFF flag + önce/sonra sinyal sayısı backtest raporu. Tolerans: sinyal artışı ≤ **+%15** VE NET-cost metriklerde kötüleşme yok | Sub-$1 coin dedup kaçağı gerçek risk; kontrollü açılır |
| 4 | Backtest gate eşikleri | **Edge Measurement Core (PR #227) NET-cost kriterleri; confluence 50 baz** (canlı prod parity), 55 ikincil rapor olarak | Gate canlı davranışı temsil etmeli; 50 canlıda koşan değer (`configs/config.phase2_1k.yaml`) |
| 5 | Cache tazeleme | **Operatör**, her backtest haftası Pazartesi + her gate koşusu öncesi Windows'ta: `python -m scripts.prefetch_data`. BT-15 stale-cache uyarısı ikinci güvenlik ağı | |
| 6 | Grup A kapsamı | **Tek batch DEĞİL** — Dalga 1: A1+A4 (düşük risk), Dalga 2: A3+A2 (flag'li), Dalga 3: A5 (önce etki audit'i) | Her kalem ayrı risk-ops review'lu cerrahi PR |

---

## 1. Doldurulmuş Batch-2 Açılış Promptu (yapıştır-kullan)

İlk yürütme oturumunda (Kilo Code veya Claude) aynen yapıştır:

```
efloud-bot Batch-2 oturumu. Önce şu üç dokümanı oku:
docs/handoff/2026-07-12-batch2-session-prep.md (grup tanımları),
docs/reviews/2026-07-11-full-repo-review-findings.md (bulgular),
docs/plans/2026-07-13-bir-aylik-master-plan.md (kararlar + haftalık sıra).
Dev sözleşmesi: CLAUDE.md + docs/dev/karpathy-guidelines.md — her fix önce
failing test, cerrahi diff, davranış toggle'ları default-OFF, canlı trade
mantığına dokunan her şey risk-ops review + operatör onayı ister.

KARARLARIM:
- A1: ölü tighten-stops gate'ini KALDIR; findings'e "bilinçli yok" notu;
  "exchange SL-amend altyapısı" ayrı backlog issue olarak aç.
- A2: default-OFF flag `intent_weakness_exit: false` ile canlandır +
  shadow-log modu (yalnız log, emir yok); 30 gün veri, sonra karar.
- A3: ONAY — tick-size-relative dedup quantize, `dedup_tick_quantize: false`
  default-OFF flag + önce/sonra sinyal sayısı raporu (tolerans: artış ≤ +%15
  ve NET-cost kötüleşmesi yok).
- Gate eşikleri: Edge Measurement Core (PR #227) NET-cost kriterleri,
  confluence 50 baz (55 ikincil rapor).
- Cache: her gate koşusu öncesi operatör `python -m scripts.prefetch_data`
  koşmuş olacak; BT-15 stale-cache uyarısı görürsen DUR ve operatöre bildir.
- Grup A: Dalga 1 = A1+A4, Dalga 2 = A3+A2, Dalga 3 = A5 (önce etki audit'i).

KAPSAM (bu oturum): F2 (tests/test_publishing_worker.py 6 kırık +
tests/test_monthly_statement.py 1 kırık → DÜZELT) + Grup B sırayla:
B2 (lease try/finally) → B3 (breaker tail-recompute, failing test önce) →
B1 (OrderManager.positions RLock — önce kısa tasarım notu).
Sonraki oturumlar master plan sırasıyla: Grup C → Grup A → D1 → E1 (ayrı
Pine oturumu). Bu oturumda C/A/D/E kalemlerine DOKUNMA.

Cowork sandbox'ta çalışıyorsan ZORUNLU ortam kuralları (hafıza:
efloud-bot-cowork-mount-workarounds): oturum-özel /tmp yolları
(PYTHONPYCACHEPREFIX=/tmp/pyc_<oturum>, GIT_INDEX_FILE=/tmp/gitidx_<oturum>),
mevcut dosya edit'i git-show+str.replace+cp pipeline'ı ile, test suite'leri
≤42s parçalarla, 1000-bar full-engine testleri sandbox'ta KOŞULAMAZ (bana
Windows komutu bırak), commit'ler read-tree/write-tree/commit-tree + doğrudan
ref yazımı, PUSH YAPMA. Windows'ta (Kilo Code) çalışıyorsan bu paragraf
geçersiz; normal git akışı + push serbest.

Doğrulama: python3 -m pytest tests/ -q --deselect
tests/engine/test_regime_train.py::test_run_auto_train + değişen alanların
backend/tests karşılıkları. Backtest-gate gereken kalemlerde v1-v2 comparison
harness (backtest/comparison.py) kullan. Çıktı: mantıksal commit'ler +
findings tablosu güncellemesi + kısa Türkçe rapor.
```

---

## 2. Roller ve Yetki Matrisi

| Rol | Araç | Sorumluluk | Yetki sınırı |
|-----|------|-----------|--------------|
| Planlama | Fable 5 (bu doküman) | Kararlar, sıra, gate tanımları | Kod yazmaz |
| Ana implementasyon | **Kilo Code** (VS Code, Windows) | TDD, cerrahi diff, full suite + 1000-bar testler, commit + push | Mainnet config'e operatör onayı olmadan dokunamaz |
| İkinci göz | **Abacus.ai** (DeepAgent/ChatLLM) | Risk-ops review draft'ları, backtest rapor analizi, security bulgu triage, tasarım notları | Repo'ya yazmaz — yalnız rapor/draft üretir |
| Operatör | **Utku** | Risk-ops onayı, prefetch koşuları, VPS deploy (`docker compose up -d`), key rotasyonu, mainnet kararları | — |
| Pine oturumu | Claude (Cowork + TradingView MCP) | E1 Pine senkron (compile döngüsü) | Python kaynağına dokunmaz |

**Zincir kuralı:** Kilo Code'un canlı mantığa (`engine/safety/`, `engine/risk/`,
`engine/lifecycle.py`, `exchange/`, config `safety:`/`risk:` blokları) dokunan her
diff'i → Abacus.ai review draft'ı → operatör onayı → merge → VPS deploy.
Hiçbir adım atlanamaz (CLAUDE.md Karpathy sözleşmesi md. 1).

---

## 3. Haftalık Plan

### Hafta 1 (13–19 Tem) — Stabilizasyon + Grup B (davranış-nötr)

| ID | İş | Sahip | Done kriteri |
|----|-----|-------|--------------|
| W1.0 | Çalışma alanı doğrulama: Windows'ta `git status` — Cowork sandbox'ının gösterdiği MM/D dosyalar mount artefaktı mı gerçek mi ayrıştır; gerçek işler commit'lenir, artefaktlar restore edilir | Operatör + Kilo | Temiz working tree, `git status` boş |
| W1.1 | **F2:** `tests/test_publishing_worker.py` (6) + `tests/test_monthly_statement.py` (1) kırıklarını düzelt | Kilo | Full suite yeşil — artık "bilinen kırık" istisnası YOK |
| W1.2 | **B2:** `engine/safe_orchestrator.py` run_cycle gövdesini tek try/finally'ye al (lease release erken return'lerde garanti) — davranış-nötr refactor | Kilo | Mevcut lease testleri + yeni erken-return path testi geçer |
| W1.3 | **B3:** `engine/safety/breaker.py` record_trade_correction tail-recompute streak kısaltması — önce failing test, sonra fix (feature default-OFF kalır) | Kilo | RED→GREEN kanıtı commit mesajında |
| W1.4 | **B1:** exchange OrderManager.positions thread-lock — Abacus kısa tasarım notu (kritik bölge envanteri) → Kilo `threading.RLock` implement | Abacus → Kilo | Envanter dokümante + eşzamanlılık testi |

**Hafta gate:** `python -m pytest tests/ backend/tests -q` (deselect: test_run_auto_train) tamamen yeşil.

### Hafta 2 (20–26 Tem) — Grup C (sinyal doğruluğu) + D1

| ID | İş | Sahip | Done kriteri |
|----|-----|-------|--------------|
| W2.0 | Cache tazele: `python -m scripts.prefetch_data` (Pazartesi) | Operatör | BT-15 uyarısı yok |
| W2.1 | **C1:** `engine/smc_v2/triggers.py:109` trigger_idx LTF↔HTF eksen düzeltmesi — failing test → fix → v1-v2 comparison harness gate | Kilo | NET-cost gate geçer; SL seçimi değişimi raporlanır |
| W2.2 | **C2:** `engine/smc_v2/confirmation.py:59` stale engulfing → yalnız son kapanmış bar onayı — backtest gate | Kilo | NET-cost gate geçer |
| W2.3 | **D1:** `data/fetcher` bar trim + gap detection + cache re-validation + manifest sha yenileme | Kilo | Prefetch sonrası manifest tutarlı; gap testi |
| W2.4 | Önce/sonra backtest karşılaştırma raporu (Türkçe özet, comparison çıktılarından) | Abacus | `docs/results/` altına rapor |

**Hafta gate:** Edge Measurement Core NET-cost kriterleri (confluence 50) + comparison
harness negatif-v1 işaretli delta incelenmiş. Uyarı: BT-4/BT-9 sonrası sonuçlar eski
baseline'lardan sistematik kötü görünür — SADECE Batch-1 sonrası baseline ile karşılaştır.

### Hafta 3 (27 Tem – 2 Ağu) — Grup A (canlı davranış, dalgalı)

| ID | İş | Sahip | Done kriteri |
|----|-----|-------|--------------|
| W3.1 | **A1 (Dalga 1):** ölü tighten-stops gate'ini kaldır (`safe_orchestrator:~1129`) + findings notu + "SL-amend infra" backlog issue | Kilo | Cerrahi diff; guard'lara dokunulmadı |
| W3.2 | **A4 (Dalga 1):** BE-SL boyutu `pos.size/2` → reconcile edilmiş `bn_size` (`exchange:1623`) — failing test önce | Kilo | RED→GREEN; F3 fail-closed yolu bozulmadı testi |
| W3.3 | **A3 (Dalga 2):** tick-size-relative dedup quantize, `dedup_tick_quantize: false` default-OFF + önce/sonra sinyal sayısı raporu | Kilo + Abacus | Sinyal artışı ≤ +%15, NET-cost kötüleşmesi yok |
| W3.4 | **A2 (Dalga 2):** `intent_weakness_exit: false` flag + shadow-log modu (emir yok, yalnız log) → **30 günlük veri toplama başlar** | Kilo | Flag OFF'ken davranış birebir testi; shadow-log satırları doğrulanır |
| W3.5 | **A5 (Dalga 3):** tp1_hit sonrası fallback PnL tek-leg tahmini — önce breaker'a etki audit'i (Abacus), sonra leg-bazlı muhasebe fix (flag'li) | Abacus → Kilo | Audit raporu + fix; breaker input'ları regresyon testi |

**Hafta gate:** Her kalem için Abacus risk-ops review draft + operatör onayı.
Hafta sonu: merge → VPS `docker compose up -d` (container recreate) → healthz + 24h log takibi.

### Hafta 4 (3–9 Ağu) — Pine senkron (E1) + test sertleştirme

| ID | İş | Sahip | Done kriteri |
|----|-----|-------|--------------|
| W4.1 | **E1:** Pine satellites (publish/v1/wave1) senkron — PINE_SPEC §19; TradingView MCP döngüsü: `pine_set_source` → `pine_smart_compile` → `pine_get_errors` (0 hataya kadar) → `pine_save`. Pine v6 zorunlu; indikatör+strategy input isimleri SENKRON | Claude (Cowork, TV MCP) | Sıfır compile hatası; PINE_SPEC güncellendi |
| W4.2 | Coverage ölçümü: `pytest --cov` — kritik modüllerde (`engine/safety/`, `exchange/`, `engine/smc_v2/`) %80 hedefi; boşluklara test yaz | Kilo | Coverage raporu `docs/results/` altında |
| W4.3 | 1000-bar full-engine regression (Windows'ta — sandbox'ta KOŞULAMAZ) | Kilo | Geçer; süre/bellek notu |
| W4.4 | 48–72h shadow koşusu VPS'te: A grubu flag'leri OFF, A2 shadow-log ON | Operatör | Breaker tetiklenmedi, orphan yok, yeni ERROR log yok |

**Hafta gate:** Coverage ≥ %80 (kritik modüller) + shadow koşusu temiz raporu.

### Hafta 5 (10–16 Ağu) — Security Hardening (final faz)

| ID | İş | Sahip | Done kriteri |
|----|-----|-------|--------------|
| W5.1 | **Secrets audit:** gitleaks/trufflehog ile repo TARİHİ taraması (F17 .env.production devamı); bulunan her secret → ROTASYON | Kilo tarar → Operatör rotasyon | Tarama raporu; sızmış key kalmadı |
| W5.2 | **Dependency audit:** `pip-audit` (bot + backend), `npm audit` (u2algo-site); kritik CVE → upgrade PR | Kilo | CRITICAL/HIGH CVE = 0 |
| W5.3 | **Exchange API key sertleştirme:** withdrawal izni OFF doğrula, VPS IP whitelist, dashboard için ayrı READ-ONLY key | Operatör | Binance key ayarları ekran kanıtı |
| W5.4 | **VPS + dashboard:** `bot.ualgotrade.com` auth (token/basic) + TLS doğrula + rate limiting; SSH key-only + ufw + fail2ban | Kilo (config) + Operatör (uygulama) | Anonim erişim testi başarısız (401); nmap temiz |
| W5.5 | **Statik tarama:** `bandit` + `semgrep` (Python); webhook/API endpoint'lerinde input validation kontrolü | Kilo + Abacus (triage) | Bulgu tablosu: CRITICAL 0, HIGH 0 |
| W5.6 | **Log hijyeni:** loglarda secret/PII taraması; gerekli maskeleme | Kilo | Grep taraması temiz |
| W5.7 | **Incident runbook:** `docs/runbooks/` altına trading-özel senaryolar — key sızıntısı, exchange hesap compromise, breaker manuel devreye alma (mevcut disaster-recovery.md + on-call-playbook.md'yi genişletir) | Abacus draft → Operatör onay | Runbook merge'lendi |

**Hafta gate:** `.claude/rules/ecc/common/security.md` checklist'inin TÜM maddeleri ✓
+ security bulgu tablosu (CRITICAL 0, HIGH 0) + rotasyonlar tamam.

### Kapanış (17–18 Ağu)

- Retro + findings tablosu final güncelleme + master plan durum işaretleme.
- A2 shadow-log **ara rapor** (≈14 günlük veri; final karar ~1 Eylül).
- Kalan/taşan işler için Batch-3 backlog dokümanı.

---

## 4. Gate Tanımları

1. **TDD gate:** Her fix önce failing test (RED) → minimal fix (GREEN) → refactor.
   Commit mesajında RED→GREEN kanıtı.
2. **Backtest gate:** Taze cache (prefetch + BT-15 temiz) → `backtest/comparison.py`
   v1-v2 harness → Edge Measurement Core NET-cost kriterleri, confluence 50 (55 ikincil).
   Negatif-v1 işaretli delta yorumlanmadan gate geçilmez.
3. **Risk-ops gate:** Canlı mantığa dokunan her diff → Abacus review draft
   (checklist: guard zayıflatılmadı, fail-closed korundu, yeni flag default-OFF,
   config diff'i incelendi) → operatör onayı.
4. **Deploy gate:** merge → VPS `docker compose up -d` → healthz OK → ilk 24h log takibi.

## 5. Test Stratejisi

- **Full suite:** `python -m pytest tests/ -q --deselect tests/engine/test_regime_train.py::test_run_auto_train` + `backend/tests` karşılıkları. Hafta 1 sonrası "bilinen kırık" istisnası kalkar; yeni kırık çıkarmak merge engelidir.
- **1000-bar full-engine:** yalnız Windows (Kilo Code). Cowork sandbox'ta koşulamaz.
- **Coverage:** kritik modüllerde (`engine/safety/`, `exchange/`, `engine/smc_v2/`) %80 (repo kuralı); W4'te ölçülür ve kapatılır.
- **Shadow/testnet:** W4.4'te 48–72h; Grup A deploy'undan sonra zorunlu.

## 6. Hazır Görev Promptları

### 6.1 Kilo Code — haftalık oturum promptu (şablon)

```
efloud-bot, Hafta {N} yürütmesi. Oku: docs/plans/2026-07-13-bir-aylik-master-plan.md
(Hafta {N} tablosu + Bölüm 0 kararları), docs/reviews/2026-07-11-full-repo-review-findings.md,
CLAUDE.md, docs/dev/karpathy-guidelines.md.
Kurallar: her fix önce failing test; cerrahi diff (ilgisiz satıra dokunma);
yeni davranış flag'i default-OFF; guard/breaker/orphan korumasını ASLA zayıflatma;
Python kaynak mantığı = tek gerçek, Pine'a bu oturumda dokunma.
Bu haftanın kalemleri: {W{N}.x listesi}. Sırayla, her kalem ayrı mantıksal commit.
Doğrulama: python -m pytest tests/ -q --deselect
tests/engine/test_regime_train.py::test_run_auto_train + backend/tests.
Canlı mantığa dokunan diff'leri merge ETME — "review bekliyor" olarak işaretle,
diff'i rapora koy. Çıktı: commit listesi + kısa Türkçe rapor + (varsa) review
bekleyen diff'ler.
```

### 6.2 Abacus.ai — risk-ops review promptu (şablon)

```
efloud-bot risk-ops review. Ekte bir diff var. Bağlam: Multi-TF SMC trading botu,
mainnet'te canlı; CLAUDE.md Karpathy sözleşmesi geçerli.
Kontrol listesi — her madde için AÇIK evet/hayır + kanıt satırı:
1. Safety guard / breaker / orphan koruması zayıflatılmış mı?
2. Fail-closed davranış korunmuş mu (hata yolunda pozisyon korumasız kalabilir mi)?
3. Yeni davranış toggle'ı default-OFF mu? Config diff'i var mı?
4. Diff cerrahi mi — istekle izlenemeyen satır var mı?
5. Test: failing-test-önce kanıtı var mı? Edge case'ler (kısmi fill, restart,
   API hatası, NaN/0 değer) kapsanmış mı?
6. Eşzamanlılık: bot thread vs API event-loop etkileşimi değişiyor mu?
Sonuç: ONAY / KOŞULLU ONAY (koşullar) / RED (gerekçe). Türkçe, kısa.
```

### 6.3 Abacus.ai — backtest analiz promptu (şablon)

```
efloud-bot backtest karşılaştırma analizi. Ekte v1-v2 comparison harness çıktısı
(önce/sonra) var. Kriterler: Edge Measurement Core NET-cost, confluence 50.
Rapor et: (1) sinyal sayısı değişimi (%), (2) NET-cost PnL/MDD/win-rate delta,
(3) negatif-v1 işaretli satırların yorumu, (4) stop_hunt_rate değişimi,
(5) gate SONUCU: GEÇTİ/KALDI + gerekçe. Uyarı: BT-4/BT-9 sonrası mutlak değerler
eski koşulardan kötü görünür — yalnız aynı-baseline delta yorumla. Türkçe, tablo ağırlıklı.
```

---

## 7. Riskler

| Risk | Etki | Önlem |
|------|------|-------|
| Cowork mount/git korupsiyonu | Kayıp iş, bozuk index | Kilo Code (Windows) ana yürütücü; Cowork yalnız doküman + Pine oturumu; memory kuralları (`efloud-bot-cowork-mount-workarounds`) |
| Bayat cache ile backtest gate false-pass | Yanlış canlı davranış onayı | Prefetch zorunlu + BT-15 uyarısında DUR kuralı |
| Grup A flag'i yanlışlıkla ON deploy'u | Canlı davranış değişimi | Default-OFF + config diff'i risk-ops checklist maddesi + deploy sonrası config doğrulama |
| TradingView MCP erişimi yok (E1) | Pine senkron gecikir | Desktop debug portu açık Cowork oturumu planla; alternatif: manuel Pine Editor + Kilo hazırlar |
| Kapsam kayması | Ay taşar | Hafta gate'i geçilmeden sonraki gruba geçilmez; taşan iş Batch-3 backlog'a |
| Secret rotasyonu sırasında canlı kesinti | Bot durur | Rotasyon bakım penceresinde (düşük volatilite saati) + rollback planı |

## 8. Ay Sonu "Done" Tanımı

1. Grup B, C, D1 kapalı; Grup A Dalga 1–2 kapalı, A5 fix'li (flag korumalı); E1 senkron.
2. Full suite yeşil, kritik modül coverage ≥ %80, 1000-bar regression geçer.
3. Security: checklist ✓, CRITICAL/HIGH bulgu 0, secret rotasyonları yapılmış,
   dashboard auth'lu, exchange key'leri sertleştirilmiş.
4. VPS'te deploy edilmiş, 48–72h shadow koşusu temiz.
5. A2 shadow-log veri topluyor (final karar ~1 Eylül, plan dışı).
6. Batch-3 backlog dokümanı yazılmış.
