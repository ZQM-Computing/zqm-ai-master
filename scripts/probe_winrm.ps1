$ErrorActionPreference='SilentlyContinue'
try {
  $r=Invoke-WebRequest -Uri http://192.168.1.224:5985/wsman -UseBasicParsing -TimeoutSec 3
  Write-Output ("STATUS:" + $r.StatusCode)
  Write-Output ($r.Content.Substring(0, [Math]::Min(180, $r.Content.Length)))
} catch {
  Write-Output ("ERROR:" + $_.Exception.Message)
}
