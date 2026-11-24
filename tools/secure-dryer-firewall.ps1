param([string]$VmSubnet = '192.168.137.0/24')
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell session.'
}
$logPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.local/security/firewall-apply.log'
Start-Transcript -Path $logPath -Force | Out-Null
# Explicit deny rules take precedence over broad Docker/application allow rules.
# Block remote unicast sources outside loopback and the dedicated VM subnet.
$addressCode = @'
import ipaddress, sys
vm = ipaddress.ip_network(sys.argv[1], strict=True)
assert vm.version == 4 and vm.is_private and vm.prefixlen >= 24
networks = list(ipaddress.summarize_address_range(ipaddress.ip_address('1.0.0.0'), ipaddress.ip_address('223.255.255.255')))
for allowed in [ipaddress.ip_network('127.0.0.0/8'), vm]:
    networks = [part for n in networks for part in (n.address_exclude(allowed) if allowed.subnet_of(n) else [n])]
print('\n'.join(str(n.network_address) + '-' + str(n.broadcast_address) for n in networks))
'@
$blocked = @(& python -c $addressCode $VmSubnet)
if ($LASTEXITCODE -ne 0 -or -not $blocked) { throw 'Invalid private VM subnet' }
$rules = @(
    @{Name='Dryer-MQTT-Block-Outside-VM'; Action='Block'; LocalPort=@(1883,8883); RemoteAddress=$blocked},
    @{Name='Dryer-MQTT-Block-IPv6'; Action='Block'; LocalPort=@(1883,8883); RemoteAddress=@('2000::/3','fc00::/7','fe80::/10')},
    @{Name='Dryer-MQTT-Allow-VM'; Action='Allow'; LocalPort=8883; RemoteAddress=$VmSubnet},
    @{Name='Dryer-NodeRed-Block-Remote'; Action='Block'; LocalPort=1880; RemoteAddress=@('1.0.0.0-126.255.255.255','128.0.0.0-223.255.255.255','2000::/3','fc00::/7','fe80::/10')}
)
$backup = Join-Path (Split-Path -Parent $PSScriptRoot) '.local/security/firewall-before.json'
if (-not (Test-Path -LiteralPath $backup)) {
    $existing = @(Get-NetFirewallRule -Name 'Dryer-*' -ErrorAction SilentlyContinue | ForEach-Object {
        $ports = $_ | Get-NetFirewallPortFilter
        $addresses = $_ | Get-NetFirewallAddressFilter
        [pscustomobject]@{Name=$_.Name;Enabled=[string]$_.Enabled;Action=[string]$_.Action;LocalPort=$ports.LocalPort;RemoteAddress=$addresses.RemoteAddress}
    })
    ConvertTo-Json -InputObject $existing -Depth 5 | Set-Content -LiteralPath $backup
}
foreach ($rule in $rules) {
    Write-Host ('Applying ' + $rule.Name)
    if (Get-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue) {
        Set-NetFirewallRule -Name $rule.Name -Enabled True -Direction Inbound -Profile Any -Action $rule.Action -Protocol TCP -LocalPort $rule.LocalPort -RemoteAddress $rule.RemoteAddress
    } else {
        New-NetFirewallRule @rule -DisplayName $rule.Name -Enabled True -Direction Inbound -Profile Any -Protocol TCP -EdgeTraversalPolicy Block | Out-Null
    }
}
Write-Host 'Firewall: Node-RED localhost only; MQTT localhost and VM subnet only.'
$resultPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.local/security/firewall-result.json'
@{applied=$true;vm_subnet=$VmSubnet;rule_names=@($rules | ForEach-Object {$_.Name})} | ConvertTo-Json | Set-Content -LiteralPath $resultPath
Stop-Transcript | Out-Null
