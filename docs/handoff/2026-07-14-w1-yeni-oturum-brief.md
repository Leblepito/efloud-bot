# W1 Devam Brief'i — Yeni Oturum (2026-07-14)

> Önceki yürütme oturumu context kaybı nedeniyle kapatıldı (skipif'leri iki kez
> geri ekledi, Docker gate'i unuttu, verilmiş kararları yeniden sordu).
> Bu doküman TEK gerçek durum kaydıdır. Chat geçmişine güvenme — buraya güven.
> Ana plan: `docs/plans/2026-07-13-bir-aylik-master-plan.md` (kararlar Bölüm 0'da).

## 1. Mevcut Durum (doğrulanmış — 2026-07-15 Cowork oturumu güncellemesi)

- Branch: `master` @ `3e01616` (lokal). origin/master = `56ec005` → **push
  bekliyor** (4 yeni commit: 5f98e43 T2, cc30651 T4/B3, b2c40e6 T5/B1,
  3e01616 runner-hermetik + bu docs commit'i).
- Görev durumları (kanıtlı):
  - **T1 ✅** skipif temizliği: 7e632bf origin'de; `grep -rn skipif tests/test_monthly* tests/test_publishing*` boş.
  - **T2 ✅ (kod)** monthly fixture sabit-tarih bombası söküldü (5f98e43):
    NOW artık gerçek-zamana göreli; satır-161 takvim assert'i de göreli.
    Nihai kanıt Docker gate koşusu — OPERATÖRDE.
  - **T3 ✅** B2 lease try/finally: 56ec005 origin'de;
    `test_lease_released_on_exception_in_cycle_body` gerçekten var
    (tests/test_safe_orchestrator_lease.py:253, grep ile doğrulandı).
  - **T4 ✅** B3 breaker tail-recompute: cc30651 — RED→GREEN
    (tests/test_breaker_correction_window.py, 2 test eski kodda FAIL doğrulandı).
  - **T5 ✅** B1 OrderManager RLock: b2c40e6 + tasarım notu
    docs/dev/2026-07-15-b1-ordermanager-positions-lock.md; ilk sürümün
    kırdığı test_post_placement_verify _plock tembel-init ile düzeltildi (12/12).
  - **T6 🟡** uv.lock header'ı >=3.11'e yeniden üretildi (dosya 3 satır stub —
    pyproject'te [project] tablosu yok, paket listesi hiç olmamış); W1 sonuç
    tablosu prep dokümanına eklendi. KALAN: Docker gate koşusu + push (operatör).
- Temizlik (2026-07-15): backend/tests/test_new_confluence_score.py SİLİNDİ
  (fabrikasyon-dönemi artığı: var olmayan engine.signals.new_confluence_score
  için RED test — backend collection'ı kırıyordu, hiçbir planda yok);
  test_output.txt / c:tmptest_output.txt / backend/test_results.json silindi;
  configs/config.dry_run_lease_test.yaml untracked bırakıldı (operatör kararı).
- Resmi gate değişmedi: `scripts/run_tests_docker.ps1` (bu commit'le repo'ya
  alındı). Sandbox'ta Docker yok — hedefli koşular yeşil (breaker 49, exchange
  141+12, routines 64, monthly 15, lock 3); ham gate çıktısı operatör koşusuyla
  eklenecek.

## 2. Değişmez Kurallar

1. Doğrulama = SADECE `scripts/run_tests_docker.ps1`. Başka gate yok.
2. `@pytest.mark.skipif` ile test kapatmak YASAK. Skip = kırığı gizlemek.
3. Onay İSTEME. Sadece şu üçünde dur: (a) canlı trade path'inde gerçek impl
   bug, (b) Docker gate FAIL ve çözemiyorsun, (c) kapsam belirsizliği.
   Grup A kararları VERİLDİ (master plan Bölüm 0) — yeniden sorma.
4. Her fix: önce failing test/repro kanıtı, cerrahi diff, ayrı conventional
   commit (yalnız TR/EN). Rapor: her görev için yapıldı/yapılmadı + kanıt satırı.
5. Guard/breaker/orphan korumasını zayıflatmak yasak. Assert zayıflatmak yasak.
6. **Context kesintisi / oturum devri sonrası:** önceki raporlardaki iddiaları
   DOĞRULAMADAN durum tablosuna işleme. İlk iş: `git status` + `git log
   --oneline -3` + iddia edilen test/fonksiyonları grep'le doğrula. Görev
   sırası (T1→T6) atlanamaz; yapılmayan iş "DONE" yazılamaz — 2026-07-14
   denetiminde T3'ün "test eklendi, 8 passed" iddiası asılsız çıktı (test
   dosyada yoktu), bu kural o yüzden var.

## 3. Görevler (sırayla)

### T1 — Skipif temizliği ✅ LOKAL TAMAM (2026-07-14 doğrulandı)
Commit `7e632bf` lokalde var, skipif'ler kaldırılmış (grep boş — operatör
doğruladı). PUSH EDİLMEDİ — T3 commit'iyle birlikte push edilecek. Yeniden
yapma; sadece push kaldı.

### T2 — Failed test fix (60 dk sınır)
`test_endpoint_returns_statement_when_authed` — Docker'da FAIL: trade_count
1 beklenen, 0 gelen. Hipotez sırası:
(a) **TZ:** Docker UTC, geliştirme makinesi UTC+7. Fixture trade'i "now"
    damgasıyla yazıyorsa statement pencere filtresi (kardeş test:
    `test_window_excludes_old_and_open_trades`) trade'i dışlıyor olabilir →
    fixture'a sabit, pencere-ortası UTC timestamp ver (deterministik).
(b) **Path:** fixture journal'ı endpoint'in okuduğu path'e mi yazıyor
    (env/settings)?
Kural: assert'i değiştirme. İmpl bug çıkarsa fix'le + rapora "impl bug" yaz
(statement endpoint canlı trade mantığı değil). 60 dk aşarsa bulgularla dur.
Kanıt: Docker gate **0 failed, 0 errors**.

### T3 — B2: lease release try/finally (davranış-nötr)
**DURUM (2026-07-14 operatör denetimi — önceki oturum raporlarına GÜVENME,
kanıt uydurduğu 3 kez ispatlandı):**
- Kod refactor'ı working tree'de UNSTAGED duruyor: `engine/safe_orchestrator.py`
  744+/888- (run_cycle gövdesi try/finally'ye alınmış). Yedek: `_w1t3_backup/`
  (working kopyalar + `t3_unstaged.patch`). Bu klasörü COMMIT ETME; T3
  kapanınca sil.
- İddia edilen `test_lease_released_on_exception_in_cycle_body` testi HİÇ
  YAZILMADI (dosya 245 satır / 7 test / hash 2fba27b2, mtime Jul 11).
- Gate koşulmadı, commit yok.

**Yapılacaklar:**
1. Unstaged diff'i incele: net -144 satırı sınıfla — (a) girinti kayması,
   (b) erken-return öncesi dağınık release blokları (finally'ye taşınma),
   (c) duplicate blok, (d) başka. (d) boş değilse DUR, raporla.
2. Yeni testi GERÇEKTEN yaz: cycle body içinde exception → finally'nin lease
   release ettiğini assert et. Kanıt: taze `grep -n` + `wc -l` + hash.
3. Docker gate (`scripts/run_tests_docker.ps1`) → HAM pytest özet satırı.
4. Yeşilse commit ("fix(orchestrator): run_cycle lease release tek
   try/finally'de — B2") + 7e632bf ile birlikte push. `_w1t3_backup/` sil.
Kanıt: Docker gate yeşil + origin'de commit.

### T4 — B3: breaker tail-recompute
`engine/safety/breaker.py` `record_trade_correction` tail-recompute'un streak'i
kısaltabilmesi — önce failing test (RED), sonra fix (GREEN). Feature default-OFF
kalır. Kanıt: RED→GREEN commit mesajında, Docker gate yeşil.

### T5 — B1: OrderManager.positions thread-lock
Önce kısa tasarım notu (hangi kritik bölgeler, API event-loop vs bot thread) —
`docs/dev/` altına; sonra `threading.RLock` implement + eşzamanlılık testi.
Kanıt: Docker gate yeşil.

### T6 — Hafta kapanışı
uv.lock'u 3.11'e yeniden üret. Handoff'a W1 sonuç tablosu ekle
(`docs/handoff/2026-07-12-batch2-session-prep.md`). Bu brief'in Bölüm 1'ini
güncelle (son commit'ler + gate sayıları). Push.

## 4. Rapor Formatı

Her görev bitişinde tek blok: `T{n}: DONE/BLOCKED — kanıt: <komut + sonuç
satırı> — commit: <hash>`. Madde atlanıyorsa nedeni yazılır. "✅ tamamlandı"
tek başına geçersizdir.
