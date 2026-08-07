param([string]$target)
$pass = ConvertTo-SecureString "EllaRose89!" -AsPlainText -Force
$cred = New-Object PSCredential("zqmlocal", $pass)
$s = New-PSSession -ComputerName $target -Credential $cred -ErrorAction SilentlyContinue
if ($s) {
    $r = Invoke-Command -Session $s -ScriptBlock { hostname; whoami; systeminfo | Select-String "OS|System Type|Total Physical Memory" }
    $r | Out-String
    Remove-PSSession $s
} else {
    Write-Output "NO_SESSION"
}
