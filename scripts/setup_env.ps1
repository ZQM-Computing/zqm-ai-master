param(
    [string]$EnvFile = "C:\Void\TheVoid\.env",
    [string]$CustomerName = "Customer",
    [string]$SupportEmail = "admin@zqmlabs.com"
)
$ErrorActionPreference='SilentlyContinue'
if (-not (Test-Path $EnvFile)) { New-Item -ItemType File -Path $EnvFile | Out-Null }
Add-Content -Path $EnvFile -Value "CUSTOMER_NAME=$CustomerName"
Add-Content -Path $EnvFile -Value "BRAND_COMPANY_NAME=$CustomerName"
Add-Content -Path $EnvFile -Value "BRAND_SUPPORT_EMAIL=$SupportEmail"
Write-Host "Environment prepared at $EnvFile"
