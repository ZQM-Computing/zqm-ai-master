<#
.SYNOPSIS
One-time repair of Windows OpenSSH known_hosts for N3 (.78) and N9 (.250).
.DESCRIPTION
Removes stale host key entries for 192.168.1.78 and 192.168.1.250 from the
current user's known_hosts and re-scans them using ssh-keyscan. No elevation,
no service restart, no remote command execution.
.NOTES
Requires OpenSSH client available in PATH. Runs under normal user context.
#>

$ErrorActionPreference = 'Stop'
$knownHosts = Join-Path (Join-Path $env:USERPROFILE '.ssh') 'known_hosts'
if (-not (Test-Path $knownHosts)) {
    Write-Host "No known_hosts at $knownHosts - nothing to fix."
    exit 0
}

function Remove-EntriesFor {
    param([string]$Pattern)
    $content = Get-Content -LiteralPath $knownHosts
    $before = $content.Count
    $content = $content | Where-Object { $_ -notmatch [regex]::Escape($Pattern) }
    Set-Content -LiteralPath $knownHosts -Value $content -NoNewline
    $after = $content.Count
    Write-Host "Removed $($before - $after) stale entry/entries for '$Pattern'."
}

function Rescan-Host {
    param([string]$Address)
    $tmp = Join-Path $env:TEMP ("known_hosts_scan_" + [Guid]::NewGuid().ToString('N'))
    try {
        ssh-keyscan -t ed25519 "$Address" 2>$null | Out-File -FilePath $tmp -Encoding ascii
        if (-not (Get-Item -LiteralPath $tmp).Length) {
            throw "ssh-keyscan returned no data for $Address"
        }
        Add-Content -LiteralPath $knownHosts -Value (Get-Content -LiteralPath $tmp)
        Write-Host "Added fresh ed25519 host key for $Address."
    } finally {
        if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Force | Out-Null }
    }
}

$targets = @('192.168.1.78', '192.168.1.250')

foreach ($ip in $targets) {
    Remove-EntriesFor -Pattern $ip
    if (-not (ssh-keyscan -t ed25519 "$ip" 2>$null)) {
        Write-Host "WARN: could not scan $ip - host may be offline or SSH not reachable."
    } else {
        Rescan-Host -Address $ip
    }
}

Write-Host "Known-hosts repair finished. Run 'ssh -o BatchMode=yes zqmlocal@<ip> echo ok' to verify."
