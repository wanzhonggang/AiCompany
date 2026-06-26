import io
import zipfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse


router = APIRouter(tags=["downloads"])

CLIENT_VERSION = "1.0.0"
ROOT_DIR = Path(__file__).resolve().parents[2]
CLIENT_EXE = ROOT_DIR / "static" / "downloads" / "AiCompanyWorkstationClient.exe"


POWERSHELL_CLIENT = r'''
$ErrorActionPreference = "Stop"
$Version = "1.0.0"

Write-Host ""
Write-Host "AI Company Workstation Client" -ForegroundColor Cyan
Write-Host "Version: $Version"
Write-Host ""

$BaseUrl = Read-Host "Platform URL, for example https://your-domain.com"
if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
  Write-Host "Platform URL is required." -ForegroundColor Red
  exit 1
}
$BaseUrl = $BaseUrl.Trim().TrimEnd("/")

$BindCode = Read-Host "Bind code"
if ([string]::IsNullOrWhiteSpace($BindCode)) {
  Write-Host "Bind code is required." -ForegroundColor Red
  exit 1
}
$BindCode = $BindCode.Trim().ToUpperInvariant()

function Get-LocalIPv4 {
  $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress -First 1
  if ($addresses) { return $addresses }
  return ""
}

function Build-Payload {
  return @{
    bind_code = $BindCode
    machine_name = $env:COMPUTERNAME
    ip_address = Get-LocalIPv4
    client_version = $Version
    system_info = "Windows $([Environment]::OSVersion.VersionString); User=$env:USERNAME"
  } | ConvertTo-Json -Depth 4
}

function Invoke-ClientPost($Path) {
  $payload = Build-Payload
  return Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl$Path" `
    -ContentType "application/json; charset=utf-8" `
    -Body $payload
}

try {
  $result = Invoke-ClientPost "/api/workstations/client/bind"
  Write-Host ""
  Write-Host "Bind success." -ForegroundColor Green
  Write-Host "Workstation: $($result.name)"
  Write-Host "Workstation ID: $($result.workstation_id)"
  Write-Host ""
} catch {
  Write-Host ""
  Write-Host "Bind failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Please check platform URL and bind code."
  Read-Host "Press Enter to exit"
  exit 1
}

Write-Host "Heartbeat started. Keep this window open while the AI employee uses this computer." -ForegroundColor Cyan
while ($true) {
  try {
    Invoke-ClientPost "/api/workstations/client/heartbeat" | Out-Null
    Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') heartbeat ok"
  } catch {
    Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') heartbeat failed: $($_.Exception.Message)" -ForegroundColor Yellow
  }
  Start-Sleep -Seconds 30
}
'''.strip()


CMD_LAUNCHER = r'''
@echo off
setlocal
title AI Company Workstation Client
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0workstation-client.ps1"
pause
'''.strip()


README = f'''
AI Company Workstation Client
Version: {CLIENT_VERSION}

How to use:
1. Extract this package on the customer's Windows computer.
2. Run start-client.cmd.
3. Enter the platform URL, for example https://your-domain.com.
4. Enter the bind code generated in Work Environment > Computer Management.
5. Keep the client window open. It will report heartbeat every 30 seconds.

Backend APIs used:
- POST /api/workstations/client/bind
- POST /api/workstations/client/heartbeat
'''.strip()


@router.get("/api/downloads/client/latest")
@router.get("/downloads/client/latest")
async def download_latest_client():
    if CLIENT_EXE.exists():
        return FileResponse(
            CLIENT_EXE,
            media_type="application/vnd.microsoft.portable-executable",
            filename="AI企业工作电脑客户端.exe",
        )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("start-client.cmd", CMD_LAUNCHER + "\r\n")
        zf.writestr("workstation-client.ps1", POWERSHELL_CLIENT + "\r\n")
        zf.writestr("README.txt", README + "\r\n")
        zf.writestr("VERSION.txt", CLIENT_VERSION + "\r\n")
    archive.seek(0)
    headers = {
        "Content-Disposition": 'attachment; filename="AiCompany-Workstation-Client-latest.zip"'
    }
    return StreamingResponse(archive, media_type="application/zip", headers=headers)
