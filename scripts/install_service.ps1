# Customer installer manifest for Windows
# Intended to be run as Administrator from an extracted release archive.

param(
    [string]$InstallDir = "C:\Void\TheVoid",
    [string]$ServiceName = "TheVoid",
    [string]$Python = "C:\Program Files\Python312\python.exe",
    [string]$AppDir = ""
)

if (-not $AppDir) { $AppDir = $InstallDir }
$ErrorActionPreference = 'SilentlyContinue'

Write-Host "Installing The Void to $InstallDir"
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir | Out-Null }

Write-Host "Creating Windows service: $ServiceName"
$cmd = "`"$Python`" -m uvicorn app.main:app --host 0.0.0.0 --port 8808 --workers 1 --app-dir `"$AppDir`""
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Host "nssm not found; please install nssm and re-run this script."
    exit 1
}
& nssm install $ServiceName $Python $("-m uvicorn app.main:app --host 0.0.0.0 --port 8808 --workers 1 --app-dir `"$AppDir`"")
& nssm set $ServiceName AppDirectory $AppDir
& nssm set $ServiceName Start SERVICE_AUTO_START
Write-Host "Running first-run auto-config..."
& $Python "$AppDir\\scripts\\auto_config.py"
Write-Host "Installing Python dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r "$AppDir\\requirements.txt"
Write-Host "Starting service..."
& nssm start $ServiceName
Write-Host "Installation complete. Verify with: http://localhost:8808/healthz"
