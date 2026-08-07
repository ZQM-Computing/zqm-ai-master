param(
    [string]$BaseUrl = "http://localhost:8808"
)
$ErrorActionPreference='SilentlyContinue'
$paths = @("/healthz", "/api/healthz", "/api/version", "/api/support/status")
foreach ($p in $paths) {
    try {
        $r = Invoke-RestMethod -Uri "$BaseUrl$p" -Method Get -TimeoutSec 5
        Write-Host "$p -> OK"
        Write-Host ($r | ConvertTo-Json -Compress)
    } catch {
        Write-Host "$p -> FAIL"
    }
}
