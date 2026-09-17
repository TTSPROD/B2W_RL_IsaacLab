[CmdletBinding()]
param([string]$BootstrapPython = 'python')
# Run from PowerShell; installs only this project's runtime, never starts training.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Uv = Join-Path $ProjectRoot '.cache/tools/bin/uv.exe'
$ManagedPython = Join-Path $ProjectRoot '.cache/python/cpython-3.11.13-windows-x86_64-none/python.exe'
$Python = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
$Lab = Join-Path $ProjectRoot '.runtime/IsaacLab'
$Commit = '37ddf626871758333d6ed89cf64ad702aef127d0'
$ReportDir = Join-Path $ProjectRoot 'logs/setup'
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}
$ScopedEnvironment = @{
    UV_CACHE_DIR = Join-Path $ProjectRoot '.cache/uv'
    UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot '.cache/python'
    UV_PYTHON_BIN_DIR = Join-Path $ProjectRoot '.cache/tools/bin'
    PIP_CACHE_DIR = Join-Path $ProjectRoot '.cache/pip'
    TEMP = Join-Path $ProjectRoot '.cache/tmp'
    TMP = Join-Path $ProjectRoot '.cache/tmp'
    PYTHONDONTWRITEBYTECODE = '1'
}
$PreviousEnvironment = @{}
$PreviousLocation = Get-Location
try {
    Set-Location -LiteralPath $ProjectRoot
    foreach ($Directory in @('.cache/tools', '.cache/tmp', '.cache/python', '.runtime', 'logs/setup')) {
        New-Item -ItemType Directory -Force -Path $Directory | Out-Null
    }
    foreach ($Name in $ScopedEnvironment.Keys) {
        $PreviousEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
        [Environment]::SetEnvironmentVariable($Name, $ScopedEnvironment[$Name], 'Process')
    }
    if (-not (Test-Path -LiteralPath $Uv)) {
        Invoke-Checked $BootstrapPython @('-m','pip','install','--target','.cache/tools','uv==0.8.22')
    }
    $UvVersion = & $Uv --version
    if ($LASTEXITCODE -ne 0 -or $UvVersion -notmatch '^uv 0\.8\.22(?:\s|$)') { throw 'Expected local uv 0.8.22' }
    Invoke-Checked $Uv @('python','install','3.11.13','--no-bin','--no-registry')
    if (-not (Test-Path -LiteralPath $Python)) {
        Invoke-Checked $Uv @('venv','--python',$ManagedPython,'.venv','--seed')
    }
    Invoke-Checked $Python @('-B','-c','import sys; assert sys.version_info[:3] == (3,11,13), sys.version')
    if (-not (Test-Path -LiteralPath $Lab)) {
        Invoke-Checked 'git' @('clone','--depth','1','--branch','v2.3.2','https://github.com/isaac-sim/IsaacLab.git',$Lab)
    }
    $ActualCommit = & git -C $Lab rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $ActualCommit.Trim() -ne $Commit) { throw 'Unexpected Isaac Lab commit' }
    # Only the packaging pin differs; reject any other setup.py content.
    $SetupFile = Join-Path $Lab 'source/isaaclab/setup.py'
    $OriginalLines = & git -C $Lab show 'HEAD:source/isaaclab/setup.py'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read pinned setup metadata' }
    $Original = [string]::Join([char]10, $OriginalLines) + [char]10
    $Patched = $Original.Replace('"starlette==0.49.1"', '"starlette==0.45.3"')
    $Current = [IO.File]::ReadAllText($SetupFile).Replace(([string][char]13 + [char]10), [string][char]10)
    if ($Current -ne $Original -and $Current -ne $Patched) { throw 'Unexpected local Isaac Lab setup.py edits' }
    [IO.File]::WriteAllText($SetupFile, $Patched, [Text.UTF8Encoding]::new($false))
    $ConstraintArgs = @('--constraint','requirements/desktop-constraints.txt')
    if (Test-Path -LiteralPath 'requirements/desktop-win-py311.lock.txt') {
        $ConstraintArgs += @('--constraint','requirements/desktop-win-py311.lock.txt')
    }
    $BuildArguments = @('-m','pip','install') + $ConstraintArgs + @('pip','setuptools==80.9.0','wheel==0.45.1','toml')
    Invoke-Checked $Python $BuildArguments
    # Resolve Sim and Lab together so later installs cannot silently break Sim pins.
    $InstallArguments = @('-m','pip','install','--no-build-isolation','--disable-pip-version-check') + $ConstraintArgs + @(
        '--extra-index-url','https://pypi.nvidia.com',
        '--extra-index-url','https://download.pytorch.org/whl/cu128',
        'isaacsim[all,extscache]==5.1.0','torch==2.7.0+cu128','torchvision==0.22.0+cu128',
        '-e','.runtime/IsaacLab/source/isaaclab',
        '-e','.runtime/IsaacLab/source/isaaclab_assets',
        '-e','.runtime/IsaacLab/source/isaaclab_tasks',
        '-e','.runtime/IsaacLab/source/isaaclab_rl[rsl-rl]',
        '-e','.runtime/IsaacLab/source/isaaclab_mimic',
        'psutil','colorama','xacrodoc','matplotlib',
        '--log','logs/setup/bootstrap-install.log'
    )
    if (Test-Path -LiteralPath 'requirements/desktop-win-py311.lock.txt') {
        $InstallArguments += @('--requirement','requirements/desktop-win-py311.lock.txt')
    }
    Invoke-Checked $Python $InstallArguments
    Invoke-Checked $Python @('-m','pip','check')
    $Freeze = & $Python -m pip freeze --all
    if ($LASTEXITCODE -ne 0) { throw 'Cannot capture package freeze' }
    $Freeze | Set-Content -LiteralPath (Join-Path $ReportDir 'pip-freeze.txt') -Encoding utf8
    @{
        isaaclab_commit=$Commit
        metadata_patch='requirements/isaaclab-sim51-metadata.patch'
        runtime_setup_sha256=(Get-FileHash -LiteralPath $SetupFile -Algorithm SHA256).Hash
        python=$Python
        installed_utc=[DateTime]::UtcNow.ToString('o')
        qualification='Installation only; run smoke_b2w.py before training'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ReportDir 'bootstrap-runtime.json') -Encoding utf8
    Write-Host 'Installation and dependency checks passed. See docs/DESKTOP_SETUP.md for GPU smoke and training.'
}
finally {
    foreach ($Name in $PreviousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousEnvironment[$Name], 'Process')
    }
    Set-Location -LiteralPath $PreviousLocation.Path
}
