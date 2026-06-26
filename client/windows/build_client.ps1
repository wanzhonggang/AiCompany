$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Source = Join-Path $PSScriptRoot "ai_company_client.py"
$BuildDir = Join-Path $PSScriptRoot "build"
$DistDir = Join-Path $PSScriptRoot "dist"
$DownloadDir = Join-Path $Root "backend\static\downloads"
$OutputExe = Join-Path $DownloadDir "AiCompanyWorkstationClient.exe"

New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null

pyinstaller `
  --noconfirm `
  --onefile `
  --windowed `
  --name "AiCompanyWorkstationClient" `
  --distpath $DistDir `
  --workpath $BuildDir `
  $Source

Copy-Item -Force (Join-Path $DistDir "AiCompanyWorkstationClient.exe") $OutputExe
Write-Host "Client executable generated: $OutputExe"
