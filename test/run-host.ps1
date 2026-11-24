$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
Push-Location $repoPath
try {
    New-Item -ItemType Directory -Force -Path .pio/host-tests | Out-Null
    $vswherePath = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswherePath) {
        $vsPath = & $vswherePath -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (-not $vsPath) { throw 'Install the Visual C++ build tools, or run test/run-host.sh with g++.' }
        $vcvarsPath = Join-Path $vsPath 'VC\Auxiliary\Build\vcvars64.bat'
        & cmd.exe /d /c "`"$vcvarsPath`" >nul && cl /nologo /EHsc /std:c++14 /W4 /WX /D_CRT_SECURE_NO_WARNINGS /Iinclude test\host\test_controller.cpp /Fo.pio\host-tests\test_controller.obj /Fe.pio\host-tests\test_controller.exe /link /INCREMENTAL:NO"
        if ($LASTEXITCODE -ne 0) { throw 'C++ compilation failed' }
        & ./.pio/host-tests/test_controller.exe
        if ($LASTEXITCODE -ne 0) { throw 'Controller tests failed' }
    } else { throw 'Visual C++ build tools not found; use test/run-host.sh with g++.' }
    node --test test/node-red.test.cjs test/home-assistant.test.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Node-RED tests failed' }
} finally { Pop-Location }
