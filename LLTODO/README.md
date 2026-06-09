# LLTODO — Multi-Agent Consensus Pipeline (v2)

> **Kural:** Bu projeye giren HER AI agent (Claude, Hermes, Gemini, Manus, Codex)
> önce bu dosyayı okur, ardından **Giriş Kontratı**'nı deterministik olarak çalıştırır.

---

## 🚪 Giriş Kontratı (Entry Contract)

Her agent repoya girdiğinde sırasıyla şu adımları işletmek zorundadır:

1. **Beyin Eşitleme (Sync):** `git pull --rebase` komutuyla whiteboard'un son halini çek.
2. **Durum Kontrolü (State Scan):** [STATE.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/STATE.md) ve [SCOREBOARD.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/SCOREBOARD.md) dosyalarını okuyarak hangi epic'te olunduğunu ve genel rolleri anla.
3. **Görev Arama (Task Scan):** `LLTODO/tasks/PENDING/` dizininde `assigned_to` değeri kendi rolü olan (veya proxy-uygun) görevleri tara.
4. **Görevi Üstlenme (Claim):** İlgili görev dosyasını `IN_PROGRESS/` altına taşı ve içindeki `status` değerini `IN_PROGRESS` olarak güncelle. Bu adımı anında commit'le ve push'la.
5. **Uygulama (Execution):** Görevin talimatlarını birebir uygula. Sadece size atanan işleri yapın, kapsam dışına çıkmayın.
6. **Rapor Yazımı (Reporting):** `LLTODO/reports/<agent>/YYYY-MM-DD-<özet>.md` formatında bir oturum raporu oluştur.
7. **Görevi Kapatma (Complete):** Görev dosyasını `DONE/` altına taşı ve `status: DONE` yap.
8. **Durum Güncelleme (State Update):** [STATE.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/STATE.md)'yi yeni aşamaya göre güncelle (örn. ball holder değiştir).
9. **Cerrahi Commit & Push:** Sadece kod değişikliklerini ve güncellenen LLTODO dosyalarını içeren temiz bir commit yapıp push'la.
10. **Timer/Relay:** Yapabiliyorsan self-schedule timer kur, yapamıyorsan bir sonraki agent için handover notu/prompt'u bırak.

---

## 📂 Dizin Yapısı

```
LLTODO/
├── README.md               ← BU DOSYA (Giriş kontratı ve genel kurallar)
├── STATE.md                ← Aktif Epic, Faz bilgisi ve sonraki adımlar (Turn/Ball)
├── SCOREBOARD.md           ← Agent başarı istatistikleri ve uzmanlık alanları
├── plans/                  ← Plan dosyaları (P-XXX-<slug>.md)
├── reviews/                ← Consensus review'ları (R-XXX-{agent}.md)
├── tests/                  ← Cross-test raporları (TEST-XXX.md)
├── reports/                ← Agent'ların oturum raporları
│   ├── hermes/
│   ├── claude/
│   └── gemini/
├── tasks/                  ← Görev havuzu
│   ├── PENDING/            ← Henüz başlanmamış görevler
│   ├── IN_PROGRESS/        ← Aktif olarak çalışılan görevler
│   └── DONE/               ← Tamamlanmış görevler
└── templates/              ← Standart şablonlar
    ├── P-template.md
    ├── R-template.md
    ├── T-template.md
    ├── UR-template.md
    ├── TEST-template.md
    └── REPORT-template.md
```

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

### FAZ 1: PLAN (Tek Agent Başlatır)
1. `LLTODO/plans/P-XXX-<slug>.md` dosyasını `templates/P-template.md` şablonuna göre oluştur.
2. Diğer 2 reviewer için review görevlerini `tasks/PENDING/R-XXX-{agent}.md` altına oluştur.
3. [STATE.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/STATE.md)'yi güncelle.

### FAZ 2: CONSENSUS (3 Agent Teyitleşir)
1. Reviewer agent'lar planı okur.
2. `LLTODO/reviews/R-XXX-{agent}.md` dosyasını `templates/R-template.md` şablonuna göre oluşturup kararını yazar (`APPROVE`, `CHANGES_REQUESTED`, `REJECT`).
3. Consensus kuralları:
   - **3/3 APPROVE:** Strong Consensus → Direkt implementasyon (Faz 3).
   - **2/3 APPROVE:** Consensus Reached → Uygulamaya geçilebilir (Faz 3).
   - **CHANGES_REQUESTED:** Plan yazarı düzeltme yapar, tekrar review'a sunulur.
   - **REJECT:** Major revizyon gerekir, sıfırdan başlanır.

### FAZ 3: IMPLEMENT (Görevler Dağıtılır)
1. Plan yazarı her task için `LLTODO/tasks/PENDING/T-XXX-{agent}-{slug}.md` oluşturur.
2. Her agent sadece kendine atanan işleri yapar, başka agent'ın görevine müdahale etmez.

### FAZ 4: ULTRAREVIEW (Claude Code Final Check)
1. Claude Code tüm tamamlanan görevleri ve raporları inceler.
2. Eksik veya hatalı iş varsa `tasks/PENDING/FIX-XXX-{agent}.md` görevleri oluşturur.
3. Her şey eksiksiz ise `UR-XXX.md` raporunu `PASS` olarak yazar.

### FAZ 5: CROSSTEST (Karşılıklı Test)
1. Her agent, rotasyona göre başka bir agent'ın işini test eder.
2. Rotasyon:
   - `hermes` → `claude`'un işini test eder.
   - `claude` → `gemini`'nin işini test eder.
   - `gemini` → `hermes`'in işini test eder.
3. Test raporu `LLTODO/tests/TEST-XXX-{tester}-tests-{testee}.md` altına yazılır.

---

## 🏆 Altın Kurallar

1. **SADECE sana atanmış görevleri yap.** `assigned_to` sen değilsen dosyaya veya işe dokunma.
2. **Planlar CONSENSUS olmadan implemente edilmez.** En az 2/3 APPROVE şarttır.
3. **Her görev sonunda mutlaka rapor yaz.** Raporunu kendi klasörüne ekle (`reports/<agent>/`).
4. **Durum güncellemelerini unutma.** [STATE.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/STATE.md) her aşamada güncel tutulmalıdır.
5. **Cross-test'te kendi işini test etme.** Rotasyonu takip et.

---

## 🤖 Agent Yetenek ve Sorumluluk Dağılımı

| Agent | Uzmanlık / Güçlü Yanı | Consensus Rolü / Ağırlığı |
|---|---|---|
| **hermes** | Kodlama, API implementasyon, Terminal scriptleri, Deploy | Plan Yazarı & Coder |
| **claude** | PR Review, mimari analiz, refactor, final UltraReview | Code Reviewer & Auditor |
| **gemini** | Görsel doğrulama (UI/chart), büyük bağlam, tie-breaker | Visual Reviewer & Tie-Breaker |
| **manus** | Browser otomasyonu, uçtan uca QA, canlı site audit | QA Engineer |
| **codex** | İkinci görüş (second opinion), kod optimizasyonu | Challenger |
