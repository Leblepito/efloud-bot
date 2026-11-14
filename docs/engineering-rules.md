# Engineering rules — ECC common kurallarından efloud'da DEĞİŞENLER

> **Rol:** constitution. Yalnız farkları listeler; ECC'nin tamamını kopyalamaz. ECC common kuralları
> (`.claude/rules/ecc/common/*`) yerel kurulumdur: `.claude/` gitignore'dadır (`.gitignore:122`), bu yüzden
> repoyu paylaşan modeller için bağlayıcı metin bu dosyadır. Çatışmada sıra: operatör talimatı >
> Karpathy 4 ilke (`CLAUDE.md`, "Geliştirme Sözleşmesi") > ADR'ler (`docs/adr/README.md`) > bu tablo > ECC common.

| Konu | ECC common | efloud kuralı (geçerli olan) | Kaynak |
|---|---|---|---|
| Öncelik | ECC kuralları "MANDATORY" | Karpathy 4 ilke ECC'nin önündedir; ECC yalnız çelişmediği yerde uygulanır | `CLAUDE.md`; `.claude/rules/ecc/common/coding-style.md` |
| Dosya / fonksiyon boyutu | Dosya ≤800, fonksiyon <50 satır | Yalnız **yeni** kod için. Mevcut büyük dosyalar (ör. `engine/safe_orchestrator.py`) bu kural için refactor edilmez (Karpathy-3); refactor ayrı karar + risk-ops + regression ledger ister | `.claude/rules/ecc/common/coding-style.md`; `CLAUDE.md` ilke 3 |
| Ölü kod | Kaldır / temizle | İlgisiz ölü kod silinmez, işaretlenir; yalnız kendi değişikliğinin orphan'ları temizlenir | `CLAUDE.md` ilke 3 |
| Test kapısı | %80 coverage, unit + integration + E2E zorunlu | Coverage kapısı **yok**. Kapı = CI pytest + `python scripts/regression_ledger.py run --base origin/master` (etkilenen modüller) + `TESTS.md` TEST-ID kaydı | `.github/workflows/ci.yml`; `docs/adr/0010-generated-regression-ledger.md`; `TESTS.md`; `REGRESSION.md` |
| TDD | RED → GREEN → refactor | Bug fix → önce reprodüksiyon testi; edge/setup değişikliği → NET-cost gate; yeni davranış toggle'ı default OFF / fail-closed | `CLAUDE.md` ilke 4; `docs/adr/0003-risk-fixes-default-off-behind-gates.md`; `docs/adr/0011-edge-go-criteria.md`; `docs/runbooks/backtest-gate.md` |
| Immutability | "CRITICAL", hiçbir nesne mutate edilmez | Python'da idiomatic kullanım: değer nesneleri `@dataclass(frozen=True)` (ör. `engine/safety/position_guard.py:33-43`); mevcut mutable durum nesneleri bu kural için yeniden yazılmaz | `.claude/rules/ecc/common/coding-style.md`; `CLAUDE.md` ilke 3 |
| İsimlendirme | camelCase / PascalCase | Python'da **geçmez**: PEP 8 (`snake_case` fonksiyon/değişken, `PascalCase` sınıf, `UPPER_SNAKE` sabit); lint ayarı `pyproject.toml` `[tool.ruff]` | `.claude/rules/ecc/common/coding-style.md`; `pyproject.toml` |
| Commit biçimi | `<type>: <description>` | `<type>(<alan>): <özet> [<model>]`; harness'in `Co-Authored-By` satırı korunur | `collab/README.md` §2 |
| Push / PR | PR akışı önerilir | **master'a doğrudan push yok** (master deploy kaynağı); feature branch + PR; `git add -A` / `git add .` yasak; force-push ve history rewrite yasak; push öncesi `git pull --rebase origin master` | `collab/README.md` §2 |
| Agent zorunluluğu | planner / tdd-guide / code-reviewer her işte zorunlu | Bu agent'lar repoda tanımlı değil. Repo harness'i: desk rolleri `agents/`, CI reviewer'ları `scripts/ci/agents/`, plugin `.claude-plugin/plugin.json`, canlı yazma kapısı `hooks/live_write_gate.py`. Agent/skill çağrısı tetikleyiciye bağlıdır, her işte zorunlu değildir | `.claude/rules/ecc/common/agents.md`; `agents/`; `scripts/ci/agents/` |
| Araştırma adımı | Her yeni implementasyon öncesi GitHub/registry araması | Yalnız yeni modül veya yeni bağımlılık için; bug fix / config / doküman için gerekmez | `.claude/rules/ecc/common/development-workflow.md`; `CLAUDE.md` ilke 2 |
| Planlama artefaktı | PRD, architecture, system_design, tech_doc, task_list | Tek format: spec + plan `docs/superpowers/{specs,plans}`, görev `collab/tasks/`; ADR yalnız geri dönmesi zor kararlarda | `docs/superpowers/`; `collab/README.md` §3; `docs/adr/template.md` |
| Güvenlik | Secret hardcode etme, rotate et | Aynı + daha sıkı: repo PUBLIC; secret, ham veri, kişisel veri repoya girmez; CI gitleaks | `collab/README.md` §0; `.github/workflows/ci.yml` |
| Canlı sistem | — | Emri yalnız motor verir; canlı değişiklik ticket + risk PASS + operatör onayı; mainnet trade mantığı = ADR-0003 kapısı; guard zayıflatılmaz | `collab/README.md` §0; `docs/adr/0003-risk-fixes-default-off-behind-gates.md`; `CLAUDE.md` ilke 1 |
| Model seçimi / patterns | `.claude/rules/ecc/common/performance.md`, `.claude/rules/ecc/common/patterns.md` önerileri | Bağlayıcı değil. Runtime LLM katmanı ayrı konu ve yalnız danışmandır | `docs/adr/0002-llm-layer-is-advisory-only.md` |
