<#
.SYNOPSIS
  Railway deploy token'ını gizli olarak alıp lokal .env dosyasına yazar ("button").

.DESCRIPTION
  - Token'ı ekranda GÖSTERMEDEN ister (Read-Host -AsSecureString).
  - .env içindeki RAILWAY_TOKEN= satırını günceller (yoksa ekler).
  - .env gitignored'dır; token repoya/commit'e ASLA gitmez.
  - İsteğe bağlı olarak Railway CLI ile login + link + up akışını başlatır.

.EXAMPLE
  pwsh ./scripts/railway_set_token.ps1
  pwsh ./scripts/railway_set_token.ps1 -Deploy          # token yazdıktan sonra deploy dene
  pwsh ./scripts/railway_set_token.ps1 -Var RAILWAY_API_TOKEN   # account token'ı yaz
#>
[CmdletBinding()]
param(
  [string]$EnvFile = (Join-Path $PSScriptRoot '..' | Join-Path -ChildPath '.env'),
  [ValidateSet('RAILWAY_TOKEN', 'RAILWAY_API_TOKEN')]
  [string]$Var = 'RAILWAY_TOKEN',
  [switch]$Deploy
)

$ErrorActionPreference = 'Stop'
$EnvFile = [System.IO.Path]::GetFullPath($EnvFile)

if (-not (Test-Path $EnvFile)) {
  Write-Host ".env bulunamadı: $EnvFile" -ForegroundColor Red
  Write-Host "Önce: Copy-Item .env.example .env" -ForegroundColor Yellow
  exit 1
}

Write-Host "Railway $Var değerini yapıştır (ekranda görünmez), Enter'a bas:" -ForegroundColor Cyan
$secure = Read-Host -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

if ([string]::IsNullOrWhiteSpace($token)) {
  Write-Host "Boş değer girildi, hiçbir şey yazılmadı." -ForegroundColor Yellow
  exit 1
}

# .env'i satır satır oku; ilgili anahtarı güncelle ya da ekle.
$lines = Get-Content -LiteralPath $EnvFile
$found = $false
$updated = foreach ($line in $lines) {
  if ($line -match "^\s*$([regex]::Escape($Var))\s*=") { $found = $true; "$Var=$token" }
  else { $line }
}
if (-not $found) { $updated += "$Var=$token" }

# UTF-8 (BOM'suz) yaz.
$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($EnvFile, $updated, $enc)

# Değeri ASLA yazdırma; sadece maskelenmiş onay.
$mask = ('*' * [Math]::Min($token.Length, 8)) + " (len=$($token.Length))"
Write-Host "OK → $Var .env'e yazıldı: $mask" -ForegroundColor Green
$token = $null

if ($Deploy) {
  $railway = Get-Command railway -ErrorAction SilentlyContinue
  if (-not $railway) {
    Write-Host "Railway CLI yok. Kur: npm i -g @railway/cli  (veya: scoop install railway)" -ForegroundColor Yellow
    exit 0
  }
  Write-Host "`nRailway CLI deploy akışı:" -ForegroundColor Cyan
  Write-Host "  railway link    # proje/servisi seç" -ForegroundColor DarkGray
  Write-Host "  railway up      # mevcut servisi deploy et" -ForegroundColor DarkGray
  & railway whoami 2>$null
  Write-Host "Hazırsan elle 'railway link' ve 'railway up' çalıştır." -ForegroundColor Cyan
}
