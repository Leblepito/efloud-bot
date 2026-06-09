# LLTODO — Multi-Agent Consensus Pipeline (v2)

> **Kural:** Bu projeye giren HER AI agent (Claude, Hermes, Gemini, Manus, Codex)
> önce bu dosyayı okur, ardından **Giriş Kontratı**'nı deterministik olarak çalıştırır.

---

## 🚪 Giriş Kontratı (Entry Contract)

Her agent repoya girdiğinde sırasıyla şu adımları işletmek zorundadır:

1. **Beyin Eşitleme (Sync):** `git pull --rebase` komutuyla whiteboard'un son halini çek.
2. **Durum Kontrolü (State Scan):** [STATE.md](STATE.md) ve [SCOREBOARD.md](SCOREBOARD.md) dosyalarını okuyarak hangi epic'te olunduğunu ve genel rolleri anla.
3. **Görev Arama (Task Scan):** `LLTODO/tasks/PENDING/` dizininde `assigned_to` değeri kendi rolü olan (veya proxy-uygun) görevleri tara.
4. **Görevi Üstlenme (Claim):** İlgili görev dosyasını `IN_PROGRESS/` altına taşı ve içindeki `status` değerini `IN_PROGRESS` olarak güncelle. Bu adımı anında commit'le ve push'la.
5. **Uygulama (Execution):** Görevin talimatlarını birebir uygula. Sadece size atanan işleri yapın, kapsam dışına çıkmayın.
6. **Rapor Yazımı (Reporting):** `LLTODO/reports/<agent>/YYYY-MM-DD-<özet>.md` formatında bir oturum raporu oluştur.
7. **Görevi Kapatma (Complete):** Görev dosyasını `DONE/` altına taşı ve `status: DONE` yap.
8. **Durum Güncelleme (State Update):** [STATE.md](STATE.md)'yi yeni aşamaya göre güncelle (örn. ball holder değiştir).
9. **Cerrahi Commit & Push:** Sadece kod değişikliklerini ve güncellenen LLTODO dosyalarını içeren temiz bir commit yapıp push'la.
10. **Self-schedule / Relay (agent'a göre — bkz. spec §9):**
    - **Claude** → işi ilerlettikten sonra LLTODO recheck'ini **OTOMATİK** planla (native `ScheduleWakeup`/cron/`/schedule`). Opsiyonel değil.
    - **Hermes** → kendi scheduler'ı veya operatör relay'i ile geri döner.
    - **Gemini** → scheduler YOK; tetikleyici = commit'lenmiş PENDING task + operatöre bırakılan hazır relay prompt'u.

---

## 📂 Dizin Yapısı

**Yerleşim (Gemini R1):** `[M]` = master'da yaşar (kalıcı/global, girişte okunur).
`[E]` = epic'in çalışma branch'inde yaşar (kodla birlikte), epic PR'ı ile master'a merge olur.

```
LLTODO/
├── README.md          [M]  ← BU DOSYA (Giriş kontratı ve genel kurallar)
├── STATE.md           [M]  ← Epic registry (girişte İLK okunur): epic→branch, faz, ball
├── SCOREBOARD.md      [M]  ← Agent uzmanlık defteri (epic'lerle birikir)
├── templates/         [M]  ← Standart şablonlar
│   ├── P-template.md         (Plan — ZORUNLU Dağıtım+gerekçe bölümü)
│   ├── R-template.md         (Review — proxy alanları + "Dağıtım Adil mi?" satırı)
│   ├── T-template.md         (Task — claim alanları)
│   ├── UR-template.md        (UltraReview — proxy alanları)
│   ├── TEST-template.md      (Cross-test — confirmed_by)
│   └── REPORT-template.md    (Oturum raporu)
├── PROMPT-claude.md   [M]  ← Genel onboarding (epic'e özel değil)
├── PROMPT-gemini.md   [M]
├── PROMPT-hermes.md   [M]
├── plans/             [E]  ← Plan dosyaları (P-XXX-<slug>.md)
├── reviews/           [E]  ← Consensus review'ları (R-XXX-{agent}.md, incl. -PROXY)
├── ultrareviews/      [E]  ← UltraReview raporları (UR-XXX.md, incl. -PROXY)
├── tests/             [E]  ← Cross-test raporları (TEST-XXX-{tester}-tests-{testee}.md)
├── reports/           [E]  ← Agent oturum raporları
│   ├── hermes/
│   ├── claude/
│   └── gemini/
└── tasks/             [E]  ← Görev havuzu
    ├── PENDING/             (Henüz başlanmamış: T-XXX / R-XXX / FIX-XXX)
    ├── IN_PROGRESS/         (Claim edilmiş, aktif çalışılan)
    └── DONE/                (Tamamlanmış)
```

> `[E]` boş dizinler `.gitkeep` ile tutulur (git boş dizin izlemez); claim/rapor adımları
> dizini hazır bulur. UltraReview raporları `ultrareviews/` altında (`UR-XXX.md`).

---

## 🔄 5-Faz Consensus Pipeline

Her büyük iş (yeni ürün, feature, refactor) bu 5 fazdan geçer:

```
PLAN ──→ CONSENSUS ──→ IMPLEMENT ──→ ULTRAREVIEW ──→ CROSSTEST
  │          │              │               │               │
  │    2/3 onay        görevler       Claude Code      agent'lar
  │    gerekli         dağıtılır      final review     birbirini
  │                                     + fix          test eder
```

> **3 consensus noktası (v2):** ① plan onayı (Faz 2) · ② dağıtım onayı (plan içinde, Faz 2) · ③ crosstest verdict teyidi (Faz 5). Hepsinde **en az 1 gerçek non-author APPROVE** şart.

### FAZ 1: PLAN (Tek Agent Başlatır)
1. `LLTODO/plans/P-XXX-<slug>.md` dosyasını `templates/P-template.md` şablonuna göre oluştur. **ZORUNLU:** plan, her task→agent satırı için SCOREBOARD'a atıfla **gerekçeli bir Dağıtım** bölümü içerir ("neden bu agent bu işi alıyor?" şeffaflığı — opak/tek-taraflı dağıtım yasak).
2. Diğer 2 reviewer için review görevlerini `tasks/PENDING/R-XXX-{agent}.md` altına oluştur.
3. [STATE.md](STATE.md)'yi güncelle.

### FAZ 2: CONSENSUS (3 Agent Teyitleşir — 2 teyit noktası)
1. Reviewer agent'lar planı okur (oy kümesi = yazar + 2 reviewer; yazar kendi planını örtük APPROVE eder).
2. `LLTODO/reviews/R-XXX-{agent}.md` dosyasını `templates/R-template.md` şablonuna göre yazar: `verdict` (`APPROVE`/`CHANGES_REQUESTED`/`REJECT`) **+ zorunlu "Dağıtım Adil mi?" satırı** (teyit-2: dağıtımı da onaylar/itiraz eder).
3. Consensus kuralları:
   - **3/3 APPROVE:** Strong Consensus → Direkt implementasyon (Faz 3).
   - **2/3 APPROVE:** Consensus Reached → Uygulamaya geçilebilir (Faz 3).
   - **CHANGES_REQUESTED:** Plan yazarı düzeltme yapar, tekrar review'a sunulur.
   - **REJECT:** Major revizyon gerekir, sıfırdan başlanır.
   - **Integrity guard:** En az **1 gerçek (non-author) APPROVE** şart — plan, yazarın self-approve'u + proxy oylarla ASLA geçemez.
   - **Eksik reviewer:** O an aktif değilse aktif agent **proxy review** yazabilir (bkz. §Proxy Oy); kimse kendi planını proxy'leyemez.

### FAZ 3: IMPLEMENT (Görevler Dağıtılır)
1. Plan yazarı her task için `LLTODO/tasks/PENDING/T-XXX-{agent}-{slug}.md` oluşturur.
2. Her agent sadece kendine atanan işleri yapar, başka agent'ın görevine müdahale etmez.

### FAZ 4: ULTRAREVIEW (Claude Code Final Check — proxy-escalable)
1. Claude Code tüm tamamlanan görevleri ve raporları inceler.
2. Eksik veya hatalı iş varsa `tasks/PENDING/FIX-XXX-{agent}.md` görevleri oluşturur (FIX > T önceliklidir).
3. Her şey eksiksiz ise `UR-XXX.md` raporunu `PASS` olarak yazar; SCOREBOARD'u günceller (append-only, imzalı).
4. **SPOF guard (R2):** Claude Faz-4 topunu STATE'teki SLA'yı (default 24h) aşana kadar tutarsa, başka bir çekirdek agent provisional `UR-XXX-PROXY` yazıp pipeline'ı açabilir; Claude dönünce gerçek raporu proxy'yi ezer (bkz. §Proxy Oy).

### FAZ 5: CROSSTEST (Karşılıklı Test)
1. Her agent, rotasyona göre başka bir agent'ın işini test eder.
2. Rotasyon:
   - `hermes` → `claude`'un işini test eder.
   - `claude` → `gemini`'nin işini test eder.
   - `gemini` → `hermes`'in işini test eder.
3. Test raporu `LLTODO/tests/TEST-XXX-{tester}-tests-{testee}.md` altına yazılır.
4. **Verdict teyidi (teyit-3):** Bir `BUGS_FOUND` verdict'i, **2. bir agent `confirmed_by` ile onaylamadan** FIX görevine dönüşmez (LLM yalancı-pozitif test raporunun pipeline'ı kilitlemesini engeller). Tüm cross-test PASS → epic DONE, STATE ilerler.

---

## 🔐 Proxy Oy Protokolü (eksik agent / Faz-4 SPOF)

Bir faz X'in oyunu beklerken X aktif değilse, aktif agent **izole-context** bağımsız bir
reviewer (ayrı subagent / ollama / farklı model) ile proxy üretir; dosya adına `-PROXY`
eklenir, frontmatter: `proxy: true, proxy_by: <agent>, proxy_engine: <...>, provisional: true`.
- Proxy quorum'a sayılır ama **PROVISIONAL**; gerçek agent gelince kendi oyu proxy'yi ezer.
- Proxy ASLA gerçek agent gibi sunulmaz. SCOREBOARD proxy işine **puan vermez**.
- **Integrity:** kimse kendi yazdığı artifact'ın oyunu proxy'leyemez; proxy tek başına bir
  consensus kapısını geçiremez (her zaman ≥1 gerçek non-author oy şart).
- Faz-4 UltraReview SPOF'u da bu mekanizmayla kapanır — yalnız STATE'teki SLA dolduktan sonra.

## 🧱 Çakışma-Güvenliği (Append-only + Claim)

1. **Namespace sahipliği:** agent yalnızca kendi dosyalarını CREATE/EDIT eder
   (`reports/<agent>/`, `R-XXX-<agent>.md`, `TEST-...-<agent>-...`). Paylaşılan dosyalar
   (STATE/SCOREBOARD/kendi yazdığın plan) per-agent bölüm halinde append-only; başkasının
   bölümüne dokunma.
2. **Claim = kilit:** PENDING → `IN_PROGRESS/` + `claimed_by`/`claimed_at` damgası + **hemen**
   commit/push. Yarışta ikinci agent pull'da claim'i görür, çekilir.
3. **Git disiplini:** her yazımdan önce `git pull --rebase`; sonra **`git add LLTODO/<spesifik>`
   (asla `git add -A` / `git add .`)**, scoped commit (`lltodo: <agent> <action> <id>`), push.
4. **YASAK:** `git reset --hard`, force-push, sahip olmadığın dosyada `checkout --`, başka
   agent'ın namespace'ini düzenlemek.

## 🌿 Şeffaf Dağıtım & Branch Modeli

- **Şeffaf dağıtım:** Faz-1 Dağıtım tablosu SCOREBOARD rakamlarını gerekçe gösterir; Faz-2
  reviewer'ları "Dağıtım Adil mi?" satırında onaylar/itiraz eder. Roller zamanla kanıtla evrilir.
- **Branch (R1):** kalıcı global dosyalar (`[M]`) master'da; her epic'in çalışma dosyaları (`[E]`)
  kendi epic branch'inde, kodla birlikte → çalışan agent task başına tek branch (sıfır switch).
  Epic bitince tek PR ile master'a merge. STATE registry epic→branch eşler.

---

## 🏆 Altın Kurallar

1. **SADECE sana atanmış görevleri yap.** `assigned_to` sen değilsen dosyaya veya işe dokunma.
2. **Planlar CONSENSUS olmadan implemente edilmez.** En az 2/3 APPROVE **+ ≥1 gerçek non-author onay** şarttır.
3. **Her görev sonunda mutlaka rapor yaz.** Raporunu kendi klasörüne ekle (`reports/<agent>/`).
4. **Durum güncellemelerini unutma.** [STATE.md](STATE.md) faz geçişlerinde güncel tutulmalıdır.
5. **Cross-test'te kendi işini test etme.** Rotasyonu takip et; `BUGS_FOUND` `confirmed_by` ister.
6. **`git add -A` YASAK** — yalnızca `LLTODO/<spesifik>` (append-only + claim güvenliği).
7. **Proxy oy şeffaf + geçici.** Kendi artifact'ını proxy'leme; proxy puan kazandırmaz.
8. **FIX > T** önceliklidir.

---

## 🤖 Agent Yetenek ve Sorumluluk Dağılımı

| Agent | Uzmanlık / Güçlü Yanı | Consensus Rolü / Ağırlığı |
|---|---|---|
| **hermes** | Kodlama, API implementasyon, Terminal scriptleri, Deploy | Plan Yazarı & Coder |
| **claude** | PR Review, mimari analiz, refactor, final UltraReview | Code Reviewer & Auditor |
| **gemini** | Görsel doğrulama (UI/chart), büyük bağlam, tie-breaker | Visual Reviewer & Tie-Breaker |
| **manus** | Browser otomasyonu, uçtan uca QA, canlı site audit | QA Engineer |
| **codex** | İkinci görüş (second opinion), kod optimizasyonu | Challenger |
