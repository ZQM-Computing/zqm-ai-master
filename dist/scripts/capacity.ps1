$ErrorActionPreference='SilentlyContinue'
$total = (Get-Service).Count
$running = (Get-Service | Where-Object Status -eq 'Running').Count
$autoStopped = (Get-Service | Where-Object StartType -eq 'Automatic' | Where-Object Status -ne 'Running').Count
Write-Output "services_total=$total"
Write-Output "services_running=$running"
Write-Output "services_auto_stopped=$autoStopped"

Write-Output "=== top_processes ==="
Get-Process | Sort-Object WorkingSet64 -Descending | Select -First 15 | ForEach-Object {
    [PSCustomObject]@{
        Name = $_.Name
        Id = $_.Id
        WS_MB = [math]::Round($_.WorkingSet64/1MB)
        CPU = [math]::Round($_.CPU,1)
    }
} | Format-Table -AutoSize
