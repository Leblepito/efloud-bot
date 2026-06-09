# gstack → efloud-bot Entegrasyon Planı

> **For Hermes:** Execute task-by-task using subagent-driven-development skill.

**Goal:** gstack workflow framework'ünü efloud-bot projesine global kurulum + skill routing ile entegre et.

**Architecture:** gstack `~/.claude/skills/gstack/` altına global kurulacak (vendoring değil, team mode). efloud-bot'un mevcut CLAUDE.md/AGENTS.md/HERMES.md dosyalarına skill routing kuralları eklenecek. Kritik gstack workflow skill'leri Hermes formatına uyarlanıp `efloud-bot/.hermes/skills/` altına yerleştirilecek.

**Tech Stack:** Bun v1.0+, Git, Bash (MSYS on Windows), Hermes Agent skill framework

**Constraints:**
- Windows host (MSYS bash), Bun yüklü değil — ilk adım
- Claude Code yüklü değil (Hermes kullanıyoruz) — gstack skill'leri manuel/Hermes formatında kullanılacak
- gstack-reference skill #1 kural: "fikir ödünç al, direkt kurma" — ama kullanıcı bu oturumda "tam kurulum" seçti
- Mevcut Hermes skill'leriyle çakışma olmamalı (writing-plans, subagent-driven-development, requesting-code-review zaten var)

---

## Task 1: Bun kurulumu

**Objective:** gstack'in tek runtime bağımlılığı olan Bun'u Windows'a kur.

**Files:**
- Yok (system-wide install)

**Step 1: Bun'u PowerShell ile kur**

```powershell
powershell -c "irm bun.sh/install.ps1 | iex"
```

**Step 2: Doğrula**

```bash
bun --version
# Beklenen: >= 1.0.0
```

---

## Task 2: gstack'i global klonla

**Objective:** gstack repo'sunu `~/.claude/skills/gstack/` altına klonla.

**Files:**
- Create: `~/.claude/skills/gstack/` (dizin + tüm dosyalar)

**Step 1: Dizini oluştur ve klonla**

```bash
mkdir -p ~/.claude/skills
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
```

**Step 2: Doğrula**

```bash
ls ~/.claude/skills/gstack/VERSION
ls ~/.claude/skills/gstack/setup
```

---

## Task 3: gstack build + setup

**Objective:** gstack binary'lerini derle ve skill'leri kur.

**Files:**
- Modify: `~/.claude/skills/gstack/browse/dist/` (binary üretilecek)
- Modify: `~/.claude/skills/` (symlink/copy skill prefix)

**Step 1: Bağımlılıkları kur**

```bash
cd ~/.claude/skills/gstack
bun install
```

**Step 2: Build (docs + binary)**

```bash
cd ~/.claude/skills/gstack
bun run build
```

**Step 3: Setup team mode**

```bash
cd ~/.claude/skills/gstack
./setup --team --no-prefix
```

**Step 4: Doğrula**

```bash
~/.claude/skills/gstack/bin/gstack-config --help
ls ~/.claude/skills/gstack/browse/dist/browse
```

---

## Task 4: efloud-bot'a skill routing kuralları ekle

**Objective:** efloud-bot'un CLAUDE.md dosyasına gstack skill routing section'ı ekle.

**Files:**
- Modify: `C:\Users\utkuc\Downloads\efloud-bot\CLAUDE.md`

**Step 1: Mevcut CLAUDE.md sonuna skill routing ekle**

CLAUDE.md sonuna eklenecek:

```markdown

## Skill routing (gstack integration)

When the user's request matches an available gstack skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design review → invoke /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- Code review/diff check → invoke /review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Post-deploy monitoring → invoke /canary
- Author a spec/issue → invoke /spec
```

**Step 2: Aynısını AGENTS.md'ye de ekle** (varsa)

---

## Task 5: Hermes ↔ gstack köprüsü — kritik skill'leri uyarla

**Objective:** gstack'in en kritik 5 workflow skill'ini Hermes formatına çevirip `efloud-bot/.hermes/skills/` altına koy.

**Files:**
- Create: `C:\Users\utkuc\Downloads\efloud-bot\.hermes\skills\gstack-office-hours\SKILL.md`
- Create: `C:\Users\utkuc\Downloads\efloud-bot\.hermes\skills\gstack-context-save\SKILL.md`
- Create: `C:\Users\utkuc\Downloads\efloud-bot\.hermes\skills\gstack-canary\SKILL.md`
- Create: `C:\Users\utkuc\Downloads\efloud-bot\.hermes\skills\gstack-review\SKILL.md`
- Create: `C:\Users\utkuc\Downloads\efloud-bot\.hermes\skills\gstack-ship\SKILL.md`

Her Hermes skill'i:
1. gstack skill'inden özü (core workflow + forcing questions) alır
2. Claude Code'a özel preamble/bash bloklarını atlar
3. Hermes tool'larına (delegate_task, terminal, search_files, vs.) uyarlar
4. efloud-bot domain bilgisi ekler (trading bot, SMC, Binance, vs.)

---

## Task 6: Entegrasyonu doğrula

**Objective:** Tüm parçaların çalıştığını doğrula.

**Step 1: gstack binary çalışıyor mu?**

```bash
~/.claude/skills/gstack/bin/gstack-config get skill_prefix
```

**Step 2: Skill routing CLAUDE.md'de var mı?**

```bash
grep -c "Skill routing" /c/Users/utkuc/Downloads/efloud-bot/CLAUDE.md
```

**Step 3: Hermes skill'leri yüklendi mi?**

```bash
ls /c/Users/utkuc/Downloads/efloud-bot/.hermes/skills/gstack-*/SKILL.md
```

**Step 4: Hermes skills_list çıktısında görünüyor mu?**

```bash
hermes skills list | grep gstack
```

---

## Riskler

1. **Bun Windows'ta sorun çıkarabilir** — MSYS bash ile PowerShell karışımı. Fallback: `npm install -g bun` veya manual install.
2. **gstack setup Windows'ta tam çalışmayabilir** — gstack'in CLAUDE.md'si "Windows: curated subset" diyor. Browser binary çalışmayabilir.
3. **Claude Code yokluğu** — gstack skill'leri Claude Code `Skill` tool'una yazılmış. Hermes'te bu tool yok. Çözüm: skill içeriklerini manuel okuyup workflow'u Hermes komutlarıyla uygula.
4. **Mevcut Hermes skill'leriyle çakışma** — `review` ve `investigate` gibi isimler mevcut Hermes skill'leriyle çakışabilir. Prefix kullan: `gstack-review`, `gstack-investigate`.
