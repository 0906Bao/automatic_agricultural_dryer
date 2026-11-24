# Run as Administrator. Allows only local-subnet clients, never Internet routing.
$ErrorActionPreference='Stop'
$ruleName='AutomaticAgriculturalDryer-HA-8123-LAN'
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Agricultural Dryer HA LAN' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8123 `
        -Profile Any -RemoteAddress LocalSubnet -EdgeTraversalPolicy Block | Out-Null
}
Write-Host 'HA port 8123 allowed for LocalSubnet only; no Internet port forwarding.'
