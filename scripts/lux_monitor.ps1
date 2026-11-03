<#
LuxAlgo izleme - Windows'tan tek komut (VPS'e ssh alias: efloud-bot).

  .\scripts\lux_monitor.ps1                      # canli akis (follow), son 30 dk'dan baslar
  .\scripts\lux_monitor.ps1 report -Since 24h    # ozet tablo
  .\scripts\lux_monitor.ps1 state                # bekleyen LuxAlgo setup'lari
  .\scripts\lux_monitor.ps1 report -Bot efloud-bot-scalp

Cikis: Ctrl+C
#>
param(
    [ValidateSet('follow', 'report', 'state')]
    [string]$Mode = 'follow',
    [string]$Since = '30m',
    [string]$Bot = 'efloud-bot',
    [string]$SshHost = 'efloud-bot'
)

$py = "docker exec -i $Bot python scripts/lux_monitor.py"
switch ($Mode) {
    'follow' { $remote = "docker logs -f --since $Since $Bot 2>&1 | $py follow --color" }
    'report' { $remote = "docker logs --since $Since $Bot 2>&1 | $py report" }
    'state'  { $remote = "docker exec $Bot python scripts/lux_monitor.py state" }
}
Write-Host "[$Bot] $Mode  (ssh $SshHost)" -ForegroundColor Cyan
ssh $SshHost $remote
