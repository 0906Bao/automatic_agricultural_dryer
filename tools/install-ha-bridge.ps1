param([string]$NodeRedUrl='http://localhost:1880')
$ErrorActionPreference='Stop'
$repoPath=Split-Path -Parent $PSScriptRoot
$backupPath=Join-Path $repoPath ('backups\node-red-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
$headers=@{'Node-RED-API-Version'='v2'}
if ($env:NODERED_ADMIN_TOKEN) { $headers.Authorization='Bearer '+$env:NODERED_ADMIN_TOKEN }
$current=Invoke-RestMethod -Uri ($NodeRedUrl+'/flows') -Headers $headers
if (-not $current.rev -or $null -eq $current.flows) { throw 'Expected Node-RED API v2 response' }
$current | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $backupPath 'flows-before.json') -Encoding utf8
$addition=Get-Content -LiteralPath (Join-Path $repoPath 'node-red\home-assistant.flow.json') -Raw | ConvertFrom-Json
$managedIds=@($addition | ForEach-Object { $_.id })
$otherNodes=@($current.flows | Where-Object { $_.id -notin $managedIds })
$combined=@($otherNodes)+@($addition)
$body=@{rev=$current.rev;flows=$combined} | ConvertTo-Json -Depth 100
$headers['Node-RED-Deployment-Type']='nodes'
Invoke-RestMethod -Method Post -Uri ($NodeRedUrl+'/flows') -Headers $headers -ContentType 'application/json' -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) | Out-Null
$after=Invoke-RestMethod -Uri ($NodeRedUrl+'/flows') -Headers $headers
foreach ($oldNode in $otherNodes) {
    $newNode=$after.flows | Where-Object { $_.id -eq $oldNode.id } | Select-Object -First 1
    if (-not $newNode) { throw ('Existing node missing after deploy: '+$oldNode.id) }
}
Write-Host ('Installed HA bridge; preserved '+$otherNodes.Count+' other nodes. Backup: '+$backupPath)
