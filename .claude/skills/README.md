# efloud-bot — Skills Rehberi

Bu klasör (`.claude/skills/`) repoya checked-in edilmiş **proje-yerel Claude Code skill'lerini** barındırır.
Skill = Claude'a belirli bir görevi *nasıl* yapacağını anlatan, tetiklenince context'e
yüklenen talimat dosyası. Repoda olduğu için takımdaki herkes (ve CI) aynı skill'leri kullanır.

## Skill nasıl çağrılır?

Claude Code üç yoldan skill çalıştırır:

1. **Otomatik (önerilen):** Doğal dilde iste — Claude skill'in `description` alanındaki
   tetikleyiciyi görüp `Skill` tool'u ile kendi çağırır.
   Örn: *"BTC-USD için kronos çalıştır"* → `kronos` skill'i otomatik tetiklenir.
2. **Slash komutu:** `name` alanı slash komutu olur. Örn: `/kronos BTC-USD 3mo 4h 48`.
3. **Açık istek:** *"efloud-deploy-safety skill'ini kullan"* dersen Claude o skill'i yükler.

> Skill dosyalarını **`Read` tool'u ile açma** — `Skill` tool'u ile çağır. `Read`, skill'i
> sadece metin olarak gösterir; `Skill` ise talimatları aktif hale getirir.

`settings.json` → `skills` bloğunda açıkça register edilen skill'ler (writing-plans,
claude-automation-recommender, kronos) ek olarak listelenir; `.md` / `SKILL.md` dosyaları
ayrıca otomatik keşfedilir.

## Bu repodaki skill'ler

| Skill | Ne zaman | Çıktı |
|-------|----------|-------|
| **kronos** | "kronos çalıştır", "X için teknik analiz", fiyat tahmini | Kronos foundation model ile fiyat tahmini + güven aralığı (araştırma, yatırım tavsiyesi değil). [Detay](kronos/SKILL.md) |
| **efloud-bugfix-workflow** | Bug raporu, log hatası, prod incident | repro → localize → fix → test → review → PR adımları |
| **efloud-deploy-safety** | Deploy, restart, env değişimi, migration planı/uygulaması | Hetzner / `docker-compose.prod.yml` deploy guardrail'ları (Hermes/Utku onayı şart) |
| **efloud-trading-risk-checklist** | `config.yaml` `risk:`/`safety:`, leverage, sizing, confluence değişimi | Canlı PnL'i etkileyen parametre değişikliği öncesi zorunlu checklist |
| **efloud-forex-adapter-research** | Forex adapter (MT5/OANDA/cTrader) seçimi ÖNCESİ | Karar dokümanı (implementasyon değil) |
| **efloud-uiux-audit** | Dashboard UI/UX analizi / redesign öncesi | Araştırma dokümanı (kod değişikliği değil) |
| **writing-plans** | Çok adımlı görev için spec → plan | 2-5 dk'lık task'lara bölünmüş implementasyon planı |
| **claude-automation-recommender** | Claude Code setup'ı optimize et | Hook/subagent/skill/plugin/MCP önerileri |

> Yukarıdakiler **proje-yerel** skill'ler. Ek olarak global `superpowers:*` skill'leri
> (brainstorming, test-driven-development, systematic-debugging, vb.) ve plugin skill'leri
> her oturumda kullanılabilir — onlar bu klasörde değil, kullanıcı/plugin seviyesinde tanımlı.

## Yeni skill ekleme

İki format desteklenir:
- **Tek dosya:** `.claude/skills/<isim>.md` — frontmatter (`name`, `description`) + talimat gövdesi.
- **Klasör:** `.claude/skills/<isim>/SKILL.md` (+ yardımcı `scripts/`, `requirements.txt`).
  Kronos bu formatı kullanır.

Adımlar:
1. `name` (kebab-case) ve net bir `description` (tetikleyici cümleleri içersin) yaz.
2. İsteğe bağlı: `settings.json` → `skills` bloğuna açık kaydını ekle.
3. Heavy/üretilen dosyaları (venv, model ağırlıkları, clone'lar) skill içi `.gitignore` ile dışla
   — repoya sadece kaynak dosyalar girsin.

## Notlar

- **kronos** ilk çalıştırmada `_kronos/` repo clone'u, `.venv/` ve ~500MB model ağırlığı indirir;
  bunlar `.claude/skills/kronos/.gitignore` ile git'ten dışlanır — repoya yalnızca `SKILL.md`,
  `README.md`, `requirements.txt`, `scripts/` girer.
- Skill kullanım disiplini için kullanıcı tercihi: gereksiz skill çağırma = token israfı;
  her skill'in net bir tetikleyicisi olmalı.
