param(
    [string]$VMDirectory = (Join-Path $env:LOCALAPPDATA 'AutomaticAgriculturalDryer\HAOS'),
    [string]$Network = 'nat',
    [switch]$Start
)
$ErrorActionPreference = 'Stop'
if ($Network -notin @('nat','bridged')) { throw 'Network must be nat or bridged' }
$vmrun = 'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
if (-not (Test-Path -LiteralPath $vmrun)) { throw 'VMware Workstation vmrun.exe not found' }
$vmPath = [System.IO.Path]::GetFullPath($VMDirectory)
$vmxPath = Join-Path $vmPath 'dryer-home-assistant.vmx'
if (Test-Path -LiteralPath $vmxPath) {
    $runningVMs=@(& $vmrun list)
    if ($runningVMs -contains $vmxPath) { Write-Host ('Project VM already running: '+$vmxPath); return }
}
New-Item -ItemType Directory -Path $vmPath -Force | Out-Null
if (-not (Test-Path -LiteralPath $vmxPath)) {
    # Some HAOS releases are board-specific. Select the newest stable release
    # that actually contains the official VMware disk, not just releases/latest.
    $releases = Invoke-RestMethod 'https://api.github.com/repos/home-assistant/operating-system/releases?per_page=10'
    $asset = $null
    foreach ($release in $releases) {
        if ($release.prerelease -or $release.draft) { continue }
        $asset = $release.assets | Where-Object { $_.name -match '^haos_ova-[\d.]+\.vmdk\.zip$' } | Select-Object -First 1
        if ($asset) { break }
    }
    if (-not $asset) { throw 'No official stable VMware VMDK image found' }
    if ($asset.browser_download_url -notmatch '^https://github\.com/home-assistant/operating-system/releases/download/') { throw 'Unexpected download origin' }
    if ($asset.digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Missing release SHA256 digest; verify the official image manually' }
    $archivePath = Join-Path $vmPath $asset.name
    $expected = $asset.digest.Substring(7)
    if (-not (Test-Path -LiteralPath $archivePath)) {
        Write-Host ('Downloading official HAOS image: ' + $asset.name)
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archivePath
    }
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw 'HAOS image checksum mismatch; archive was left untouched for inspection'
    }
    $diskPath = Join-Path $vmPath ($asset.name -replace '\.zip$','')
    if (Test-Path -LiteralPath $diskPath) { throw 'Existing disk without VMX; refusing to overwrite it' }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $vmPath
    if (-not (Test-Path -LiteralPath $diskPath)) { throw 'Expected VMDK not found after extraction' }
    $diskName = Split-Path -Leaf $diskPath
    $vmx = @"
.encoding = "UTF-8"
config.version = "8"
virtualHW.version = "19"
displayName = "Agricultural Dryer - Home Assistant OS"
guestOS = "otherlinux-64"
firmware = "efi"
memsize = "2048"
numvcpus = "2"
cpuid.coresPerSocket = "2"
scsi0.present = "TRUE"
scsi0.virtualDev = "lsilogic"
scsi0:0.present = "TRUE"
scsi0:0.fileName = "$diskName"
ethernet0.present = "TRUE"
ethernet0.connectionType = "$Network"
ethernet0.virtualDev = "e1000"
ethernet0.addressType = "generated"
usb.present = "FALSE"
sound.present = "FALSE"
floppy0.present = "FALSE"
tools.syncTime = "TRUE"
"@
    [System.IO.File]::WriteAllText($vmxPath,$vmx,[System.Text.UTF8Encoding]::new($false))
    [pscustomobject]@{release=$release.tag_name;image=$asset.name;sha256=$expected;network=$Network;vmx=$vmxPath} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $vmPath 'installation.json') -Encoding utf8
}
Write-Host ('VMX: ' + $vmxPath)
# Keep the NIC on conventional PCI for compatibility with older Workstation.
$currentVMX=[System.IO.File]::ReadAllText($vmxPath)
$currentVMX=$currentVMX -replace '(?m)^ethernet0.virtualDev\s*=.*$', 'ethernet0.virtualDev = "e1000"'
$currentVMX=$currentVMX -replace '(?m)^ethernet0.pciSlotNumber\s*=.*\r?\n?', ''
$pciSettings=@{'pciBridge0.present'='TRUE'}
foreach ($bridge in 4..7) {
    $pciSettings["pciBridge$bridge.present"]='TRUE'
    $pciSettings["pciBridge$bridge.virtualDev"]='pcieRootPort'
    $pciSettings["pciBridge$bridge.functions"]='8'
}
foreach ($key in $pciSettings.Keys) {
    if ($currentVMX -notmatch ('(?m)^'+[regex]::Escape($key)+'\s*=')) {
        $currentVMX += "`n$key = `"$($pciSettings[$key])`""
    }
}
[System.IO.File]::WriteAllText($vmxPath,$currentVMX,[System.Text.UTF8Encoding]::new($false))
if ($Start) {
    & $vmrun -T ws start $vmxPath nogui
    if ($LASTEXITCODE -ne 0) { throw 'VMware could not start HAOS; inspect the reported hypervisor error' }
    Write-Host 'HAOS VM started. First boot may download Home Assistant Core.'
}
