# restart-void-bus.ps1
# Restart ZQM-Void-N4 (nssm) so the repointed bus in app/core/config.py
# (garden/flatspace/network/eden 192.168.1.228 -> 192.168.1.217) takes effect,
# then INDEPENDENTLY verify the new instance reports the bus as reachable.
# MUST run AS ADMIN (service control + registry read need elevation).

$ErrorActionPreference = 'Continue'

function Test-Elevated {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object System.Security.Principal.WindowsPrincipal($id)
    return $pr.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}
if (-not (Test-Elevated)) {
    Write-Host "NOT ELEVATED. Re-run this script from an Admin PowerShell window (right-click -> Run as Administrator)."
    exit 1
}

$svc = 'ZQM-Void-N4'
$s = Get-Service -Name $svc -ErrorAction SilentlyContinue
if (-not $s) { Write-Host "Service '$svc' not found."; exit 2 }
Write-Host "Found: $($s.Name) [$($s.Status)]"

Write-Host "Restarting '$svc'..."
Restart-Service -Name $svc -Force
Start-Sleep -Seconds 8

$s2 = Get-Service -Name $svc
Write-Host "Post-restart status: $($s2.Status)"

# 1) :8808 listening?
$listening = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $ar = $tcp.BeginConnect('127.0.0.1', 8808, $null, $null)
    if ($ar.AsyncWaitHandle.WaitOne(2000) -and $tcp.Connected) { $listening = $true }
    $tcp.Close()
} catch { }
Write-Host ":8808 listening after restart = $listening"

# 2) version probe (non-auth) confirms new process is up
try {
    $v = (Invoke-RestMethod -Uri 'http://127.0.0.1:8808/api/version' -TimeoutSec 5).version
    Write-Host "Live Void version = $v"
} catch { Write-Host "version probe failed: $_" }

# 3) read the nssm stdout log (where Void prints garden/health) and surface reachability
$logPath = $null
try {
    $key = "HKLM:\SYSTEM\CurrentControlSet\Services\$svc\Parameters"
    $appStdout = (Get-ItemProperty -Path $key -Name 'AppStdout' -ErrorAction SilentlyContinue).AppStdout
    if ($appStdout) { $logPath = $appStdout }
} catch { }
if ($logPath -and (Test-Path $logPath)) {
    Write-Host "nssm log: $logPath"
    $tail = Get-Content -Path $logPath -Tail 40
    $gardenLine = $tail | Where-Object { $_ -match 'garden|reachable|degraded|Garden' } | Select-Object -Last 8
    if ($gardenLine) {
        Write-Host "--- garden/health signals from Void log ---"
        $gardenLine | ForEach-Object { Write-Host "   $_" }
    } else {
        Write-Host "No explicit garden/reachable line in last 40 log lines."
    }
} else {
    Write-Host "nssm stdout log path not found or unreadable; skipping log scan."
}

# 4) confirm config on disk is repointed (RUNNING tree is what the service loads)
$cfg = 'C:\Void\ZQM-AI-Master\app\core\config.py'
if (-not (Test-Path $cfg)) {
    $cfg = 'C:\Users\zqmco\repos\ZQM-Computing\zqm-ai-master\app\core\config.py'
}
    $hit = (Select-String -Path $cfg -Pattern 'garden_endpoint.*192\.168\.1\.217' -Quiet)
    $stale = (Select-String -Path $cfg -Pattern 'garden_endpoint.*192\.168\.1\.228' -Quiet)
    Write-Host "config garden_endpoint -> .217 : $hit | still .228 : $stale"
}
Write-Host "DONE."
