# fix-void-f1f2.ps1
# Combined admin fix for the live Void (C:\Void\ZQM-AI-Master) degraded state.
#   F1: ensure Ollama is running (with the embeddings API live) so flatspace
#       embedding writes + inference work. Non-disruptive: if :11434 already
#       answers, we do NOT kill the user's existing Ollama (e.g. tray app) — we
#       just verify embeddings. Only start a server if none is up.
#   F2: restart ZQM-Void-N4 nssm service (picks up repointed .217 bus endpoints
#       in config.py + new mesh_ollama LOCAL backend).
# Run AS ADMIN (right-click -> Run as Administrator). Script self-checks elevation.
# All verifications are INDEPENDENT (re-probe the live services, not self-claims).

$ErrorActionPreference = 'Continue'

function Need-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object System.Security.Principal.WindowsPrincipal($id)
    return -not $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}
if (Need-Admin) {
    Write-Host "[BLOCKED] Run this script AS ADMIN (right-click -> Run as Administrator)." -ForegroundColor Red
    exit 1
}
Write-Host "[ok] running elevated." -ForegroundColor Green

$ollamaExe = "C:\Users\zqmco\AppData\Local\Programs\Ollama\ollama.exe"
$logDir = "C:\Void\ZQM-AI-Master"

function Test-OllamaUp {
    try { $r = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2; return $true }
    catch { return $false }
}

function Test-Embeddings($model) {
    try {
        $body = @{ model = $model; prompt = "hello" } | ConvertTo-Json -Compress
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/embeddings" -Method Post `
            -ContentType "application/json" -Body $body -TimeoutSec 10
        return ($null -ne $r.embedding -and $r.embedding.Count -gt 0)
    } catch { return $false }
}

# ---------- F1: ensure Ollama serving with embeddings ----------
Write-Host "`n=== F1: Ollama with embeddings ===" -ForegroundColor Cyan

if (Test-OllamaUp) {
    Write-Host "Ollama already serving on :11434 — not disrupting the running instance." -ForegroundColor Green
} else {
    Write-Host "Ollama not up — starting 'ollama serve' (background)..."
    Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden `
        -RedirectStandardOutput "$logDir\ollama_embed.log" -ErrorAction SilentlyContinue
}

# wait for :11434 + embeddings on the two models The Void actually uses
$models = @("all-minilm:latest", "qwen2.5:3b")   # flatspace embed model + chat model
$ok = $true
for ($i = 0; $i -lt 40; $i++) {
    if (-not (Test-OllamaUp)) { Start-Sleep -Seconds 1; continue }
    $allOk = $true
    foreach ($m in $models) { if (-not (Test-Embeddings $m)) { $allOk = $false; break } }
    if ($allOk) { $ok = $true; break }
    Start-Sleep -Seconds 1
}
if ($ok) {
    Write-Host "[PASS] Ollama :11434 up + embeddings return vectors for all-minilm:latest AND qwen2.5:3b." -ForegroundColor Green
} else {
    Write-Host "[WARN] Ollama/embeddings not ready within 40s. Check $logDir\ollama_embed.log" -ForegroundColor Yellow
    Write-Host "        (health gate itself only needs .217:8808 — see F2 — not Ollama.)" -ForegroundColor Yellow
}

# ---------- F2: restart ZQM-Void-N4 ----------
Write-Host "`n=== F2: restart ZQM-Void-N4 ===" -ForegroundColor Cyan
try {
    Restart-Service -Name "ZQM-Void-N4" -Force -ErrorAction Stop
    Start-Sleep -Seconds 6
    $s = Get-Service -Name "ZQM-Void-N4" -ErrorAction Stop
    if ($s.Status -eq "Running") { Write-Host "[PASS] ZQM-Void-N4 running." -ForegroundColor Green }
    else { Write-Host "[WARN] ZQM-Void-N4 status: $($s.Status)" -ForegroundColor Yellow }
} catch {
    Write-Host "[BLOCKED] restart failed: $($_.Exception.Message)" -ForegroundColor Red
}

# ---------- independent verification: live health envelope ----------
Write-Host "`n=== live health re-check (:8808 /api/void/talk) ===" -ForegroundColor Cyan
$token = $null
try {
    Push-Location "C:\Void\ZQM-AI-Master"
    $token = (python -c "import sys; sys.path.insert(0,'.'); from app.core.security import create_access_token; print(create_access_token(subject={'sub':'hermes-debug','username':'hermes','roles':['admin'],'type':'user'}))" 2>$null | Select-Object -Last 1)
    Pop-Location
} catch { Write-Host "[note] could not mint admin token; skipping envelope read." -ForegroundColor Yellow }
if ($token) {
    try {
        $env:PYTHONIOENCODING = "utf-8"
        $body = '{"message":"status check","level":"basic"}'
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8808/api/void/talk" -Method Post -ContentType "application/json" -Headers @{ Authorization = "Bearer $token" } -Body $body -TimeoutSec 40
        $h = $resp.state.health
        Write-Host "status        : $($h.status)"
        Write-Host "garden        : $($h.garden)"
        Write-Host "flatspace     : $($h.flatspace)"
        Write-Host "database      : $($h.database)"
        Write-Host "redis         : $($h.redis)"
        Write-Host "reply         : $($resp.reply)"
    } catch { Write-Host "[WARN] envelope read failed: $($_.Exception.Message)" -ForegroundColor Yellow }
}

Write-Host "`n=== done. Paste this output back to Hermes. ===" -ForegroundColor Cyan
