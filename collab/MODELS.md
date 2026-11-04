# Modeller — kim, nerede, ne yapar

> Değişiklik PR ile. "Doğrulanmadı" yazan satırları ilgili model ilk oturumunda
> doğrulayıp PR ile düzeltir.

| | **claude-code** | **hermes** | **abacus** |
| --- | --- | --- | --- |
| Çalıştığı yer | Operatör laptopu (Windows), Claude desktop app | Hetzner VPS (prod host), Hermes Agent gateway | Operatör laptopu, Abacus.ai desktop/CodeLLM (`.abacusai/` gitignore'lu) |
| Repo klonu | Laptop klonu (`~/Downloads/efloud-bot`) + kendi worktree'leri | **`~/work/efloud-bot`** (T-20261104-05 ile kurulur). `/opt/efloud-bot` = PROD, çalışma klonu değil | Laptop klonu — **kendi worktree'si** (aşağı) |
| Git kimliği | gh CLI (Leblepito), commit'te `Co-Authored-By: Claude` | Commit author `Hermes Agent` | `git -c user.name="Abacus.AI" -c user.email="abacus@users.noreply.github.com" commit …` + `[abacus]` |
| GitHub erişimi | `gh` CLI | Kendi fine-grained PAT'i (yalnız bu repo, Contents + Pull requests RW), VPS secret store'unda | Laptop git credential'ı veya kendi PAT'i (T-20261104-04) |
| Private store | `~/efloud-collab-private/` | `~/efloud-collab-private/` (yalnız güvenli/türetilmiş veri) | `~/efloud-collab-private/` |
| Güçlü yanı | Kod + TDD, Pine v6 + TradingView Desktop MCP, review, PR | 7/24 VPS: rutin raporlar, journal/log okuma, Telegram bildirimleri, ops gözlemi (salt okuma) | Bağımsız ikinci görüş: review, metin/veri analizi (güvenilmeyen metin dahil — laptop'ta), dokümantasyon (doğrulanmadı) |
| MCP | tradingview (yalnız laptop), github, claude.ai connector'ları | yok (config'de `mcp_servers` yok) | doğrulanmadı |
| Desk rolü (varsayılan) | Lead + pine-engineer + strategist + **execution-ops** (ticket ile, `live_write_gate` backstop'u) | trade-reviewer + research-analyst (yalnız iç veri: journal, log, motor çıktısı) | ikinci reviewer (risk-manager / code review) + analist |

## Herkes için YASAK

- Emir açma/kapama, Binance key/withdraw/transfer, leverage/margin değişimi.
- `configs/*.yaml` `risk:`/`safety:` bloklarını ticket + NET-cost kanıtı + operatör onayı olmadan değiştirmek.
- `/opt/efloud-bot` içinde edit/commit, `docker compose`, container restart. (Ticket'lı
  operasyonları yalnız claude-code uygular; Hermes ve Abacus'ta canlı-yazma hook'u yok.)
- Güvenilmeyen üçüncü-taraf metni (Telegram export, web, sosyal medya) VPS'te işlemek.
- `pine/efloud_signals.pine` ve `engine/smc_v2/` port'unu ezmek (CLAUDE.md ilke 3).
- Master'a doğrudan push (bkz. `README.md` §2).
- Secret/token'ı repo'ya, log'a, task'a, sohbete yazmak.

## Aynı laptop klonunu paylaşma (claude-code ↔ abacus)

Branch state klon-geneldir: biri ana klonda `checkout` yapınca diğerinin çalışma dizini
değişir. Her model **kendi worktree'sinde** çalışır:

```bash
git fetch origin
git worktree add ../wt-abacus-<task> -b collab/abacus/<task-id>-<slug> origin/master
```

Ana klonda uzun süreli değişiklik bırakma; iş PR'la bitince worktree'yi kaldır
(`git worktree remove ../wt-abacus-<task>`).
