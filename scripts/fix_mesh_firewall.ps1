# N1/N2 Firewall Remediation Script for ZQM-MESH
# Run as Administrator on each target node (N1 and N2)
# This script opens Ollama, HTTP API, and gossip ports to the 192.168.1.0/24 subnet
#
# Usage (run on N1, then on N2):
#   powershell -ExecutionPolicy Bypass -File .\fix_mesh_firewall.ps1

param(
    [ValidateSet("N1","N2")]
    [string]$NodeId = "N1"
)

$ErrorActionPreference = 'Stop'
$subnet = "192.168.1.0/24"

Write-Host "=== ZQM-MESH Firewall Remediation for $NodeId ===" -ForegroundColor Cyan
Write-Host "Subnet: $subnet" -ForegroundColor Gray

# Rules to add: name, display name, direction, protocol, ports, program (optional)
$rules = @(
    @{
        Name        = "ZQM-MESH-Ollama-In"
        DisplayName = "ZQM-MESH Ollama API (11434)"
        Direction   = "Inbound"
        Protocol    = "TCP"
        Ports       = 11434
        Program     = ""
    },
    @{
        Name        = "ZQM-MESH-VoidAPI-In"
        DisplayName = "ZQM-MESH Void API (8808)"
        Direction   = "Inbound"
        Protocol    = "TCP"
        Ports       = 8808
        Program     = ""
    },
    @{
        Name        = "ZQM-MESH-Gossip-In"
        DisplayName = "ZQM-MESH Gossip UI (8891)"
        Direction   = "Inbound"
        Protocol    = "TCP"
        Ports       = 8891
        Program     = ""
    },
    @{
        Name        = "ZQM-MESH-Quantum-In"
        DisplayName = "ZQM-MESH Quantum API (8891 alt/5000)"
        Direction   = "Inbound"
        Protocol    = "TCP"
        Ports       = 5000,8891
        Program     = ""
    }
)

$added = 0
$skipped = 0
$failed = 0

foreach ($rule in $rules) {
    $name = $rule.Name
    $display = $rule.DisplayName
    $portList = $rule.Ports -join ","
    $prog = $rule.Program

    # Check if rule already exists
    $existing = Get-NetFirewallRule -DisplayName $display -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[SKIP] Rule exists: $display" -ForegroundColor Yellow
        $skipped++
        continue
    }

    try {
        if ($prog) {
            New-NetFirewallRule `
                -Name $name `
                -DisplayName $display `
                -Direction $rule.Direction `
                -Protocol $rule.Protocol `
                -LocalPort $portList `
                -Program $prog `
                -Action Allow `
                -Profile Any `
                -ErrorAction Stop | Out-Null
        } else {
            New-NetFirewallRule `
                -Name $name `
                -DisplayName $display `
                -Direction $rule.Direction `
                -Protocol $rule.Protocol `
                -LocalPort $portList `
                -RemoteAddress $subnet `
                -Action Allow `
                -Profile Any `
                -ErrorAction Stop | Out-Null
        }
        Write-Host "[ADDED] $display" -ForegroundColor Green
        $added++
    }
    catch {
        Write-Host "[FAIL] $display : $_" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "  Added  : $added"
Write-Host "  Skipped: $skipped"
Write-Host "  Failed : $failed"
Write-Host ""

if ($failed -eq 0) {
    Write-Host "Firewall remediation complete for $NodeId." -ForegroundColor Green
    Write-Host "Verify from N4: Test-NetConnection -ComputerName <$NodeId IP> -Port 11434" -ForegroundColor Gray
} else {
    Write-Host "Some rules failed. Re-run as Administrator." -ForegroundColor Red
}
