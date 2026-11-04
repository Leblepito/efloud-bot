# MCP kaydı — hangi sunucu, kimde, nasıl

> Secret yok: yalnız **env var adı**. Değerleri her model kendi secret store'unda tutar.
> Yeni sunucu eklerken: güvenlik notu (yazma yetkisi var mı?) + hangi modelin kullanabileceği zorunlu.

| Sunucu | Ne yapar | Nerede çalışır | Kim kullanır | Yazma riski | Config |
| --- | --- | --- | --- | --- | --- |
| **tradingview** (`tradesdontlie/tradingview-mcp` @ `c05b8f5`; lokal klonda çözülmemiş `package-lock.json` stash çakışması var → T-20261104-04) | TradingView Desktop'ı CDP ile okur/yönetir: chart, Pine compile, OHLCV, replay | Yalnız operatör laptopu (`~/tradingview-mcp`, CDP `127.0.0.1:9222`) | claude-code (abacus aynı laptopta config'lenebilir) | YÜKSEK: `ui_evaluate`/`ui_click`/`ui_keyboard`/`tv_update` → deny; `pine_save`/`alert_*` → ask | `~/.claude.json` (user scope). Deny listesi + kurulum: `skills/tradingview-mcp/SKILL.md` |
| **github** | Issue/PR/dosya | Her yerde | hepsi | Orta (repo yazma) | Claude: `.mcp.json` (repo kökü). Token: `GITHUB_PERSONAL_ACCESS_TOKEN` |
| supabase / drive / gmail | claude.ai connector'ları | Claude hesabı | yalnız claude-code | Orta | claude.ai ayarları (repo'da değil) |

## TradingView'ı açma (laptop)

TV Desktop MSIX (Microsoft Store) sürümü. CDP portuyla yeniden başlat:

```powershell
$p=(Get-AppxPackage *TradingView*).InstallLocation
Stop-Process -Name TradingView -Force -ErrorAction SilentlyContinue
Start-Process "$p\TradingView.exe" -ArgumentList '--remote-debugging-port=9222'
```

Kontrol: `tv_health_check` → `cdp_connected: true`. (2026-11-04 doğrulandı: `BINANCE:BNBUSDT.P` 1h.)
`tv_launch` tool'u MSIX'i bulamazsa ("not found" / "Access is denied") yukarıdaki yolu kullan.

## Model başına config parçaları

**Claude Code** — `.mcp.json` (repo, paylaşılır):

```json
{ "mcpServers": { "github": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"] } } }
```

Not: `@modelcontextprotocol/server-github` paketi upstream'de arşivlendi; resmi halefi
`github/github-mcp-server`. Geçiş ayrı bir task (davranış farkı test edilmeden değiştirme).

**Hermes** — `~/.hermes/config.yaml` (doğrulanmadı — Hermes ilk oturumunda kendi şemasına göre düzeltsin):

```yaml
mcp_servers:
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"   # değer VPS env'inde, repo'da değil
```

TradingView MCP VPS'te **çalışmaz** (TradingView Desktop + CDP yalnız laptopta). Hermes grafik
verisini ccxt/Binance public endpoint'ten alır ya da claude-code'a task açar.

**Abacus** — Abacus desktop/CodeLLM MCP ayarı (doğrulanmadı): Claude ile aynı `mcpServers` JSON şeması
genelde kabul edilir. TradingView'ı eklerse:

```json
{ "mcpServers": { "tradingview": { "command": "node", "args": ["<HOME>/tradingview-mcp/src/server.js"] } } }
```

ve aynı deny listesini Abacus'un izin ayarında uygular. Aynı chart'ı iki model **eşzamanlı
yönetmesin** (sembol/TF değiştirme çakışır) — TV işi için task'ta `claimed_by` kim ise chart onundur.
