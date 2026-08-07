# Void diagnostic helper — uses the correct admin auth
param([string]$BaseUrl="http://127.0.0.1:8808")

$ErrorActionPreference = 'SilentlyContinue'
$bearer = $env:ZQM_ADMIN_TOKEN
if (-not $bearer) {
    # Try reading from .env if present
    $envLine = Get-Content "$PSScriptRoot\.env" -ErrorAction SilentlyContinue | Where-Object { $_ -match '^ZQM_ADMIN_PASSWORD=' }
    if ($envLine) {
        $pw = $envLine.Split('=',2)[1].Trim('"')
        $bearer = ([Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:$pw")))
    } else {
        $bearer = "Basic YWRtaW46"
    }
}
$hdrs = @{ Authorization = "Bearer $bearer" }

Write-Host "=== STATUS ==="
(Invoke-Rest -Uri "$BaseUrl/api/status" -Headers $hdrs | ConvertTo-Json -Depth 5)

Write-Host "`n=== VERSION ==="
(Invoke-Rest -Uri "$BaseUrl/api/version" | ConvertTo-Json -Depth 3)

Write-Host "`n=== /docs OPENAPI COUNT ==="
$oai = Invoke-Rest -Uri "$BaseUrl/openapi.json"
$oai.paths.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object

Write-Host "`n=== FALSIFICATION AUDIT ==="
(Invoke-Rest -Uri "$BaseUrl/api/falsification/audit" -Headers $hdrs | ConvertTo-Json -Depth 5)

Write-Host "`n=== MESH OLLAMA STATUS ==="
(Invoke-Rest -Uri "$BaseUrl/api/mesh/ollama" -Headers $hdrs | ConvertTo-Json -Depth 5)

Write-Host "`n=== SELF-IMPROVE LEDGER ==="
(Invoke-Rest -Uri "$BaseUrl/api/self-improve/ledger" -Headers $hdrs | ConvertTo-Json -Depth 5)

Write-Host "`n=== PROCESS LIST ==="
Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, WorkingSet64, StartTime | Format-Table -AutoSize
