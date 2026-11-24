param([string]$VMDirectory=(Join-Path $env:LOCALAPPDATA 'AutomaticAgriculturalDryer\HAOS'))
$ErrorActionPreference='Stop'
$repoPath=Split-Path -Parent $PSScriptRoot
$isoPath=Join-Path $repoPath '.local\haos-config.iso'
$vmPath=[System.IO.Path]::GetFullPath($VMDirectory)
$vmxPath=Join-Path $vmPath 'dryer-home-assistant.vmx'
if (-not (Test-Path -LiteralPath (Join-Path $vmPath 'installation.json'))) { throw 'Expected project-owned HAOS installation metadata' }
if (-not (Test-Path -LiteralPath $isoPath)) { throw 'Prepare CONFIG ISO first' }
$vmrun='C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
# Only the newly provisioned project VM is restarted; no other VMs/containers.
& $vmrun -T ws stop $vmxPath hard
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the project VM; do not edit a running VMX' }
$text=[System.IO.File]::ReadAllText($vmxPath)
$settings=@{'ide1:0.present'='TRUE';'ide1:0.deviceType'='cdrom-image';'ide1:0.fileName'=$isoPath;'ide1:0.startConnected'='TRUE'}
foreach($key in $settings.Keys){
    $text=$text -replace ('(?m)^'+[regex]::Escape($key)+'\s*=.*\r?\n?'),''
    $text+="`n$key = `"$($settings[$key])`""
}
[System.IO.File]::WriteAllText($vmxPath,$text,[System.Text.UTF8Encoding]::new($false))
& $vmrun -T ws start $vmxPath nogui
if ($LASTEXITCODE -ne 0) { throw 'Could not start project VM with CONFIG ISO' }
Write-Host 'Project VM restarted with CONFIG ISO.'
