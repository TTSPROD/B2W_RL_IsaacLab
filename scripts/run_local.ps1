$ErrorActionPreference = 'Stop'
$PythonArgs = $args
$IsaacSimEnvironment = if ($env:B2W_ISAAC_SIM_ENV) { $env:B2W_ISAAC_SIM_ENV } else { 'D:\isaacsim51' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$simPackages = Join-Path $IsaacSimEnvironment 'Lib\site-packages'
if (-not (Test-Path -LiteralPath $python)) { throw "Missing project Python: $python" }
if (-not (Test-Path -LiteralPath $simPackages)) { throw "Missing Isaac Sim packages: $simPackages" }

$sourceDirs = @(
    'isaaclab', 'isaaclab_assets', 'isaaclab_rl', 'isaaclab_tasks'
) | ForEach-Object { Join-Path $root ".runtime\IsaacLab\source\$_" }
$sourceDirs += Join-Path $root 'vendor\robot_lab\source\robot_lab'
$sourceDirs += $simPackages
foreach ($path in $sourceDirs) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing source path: $path" }
}

$omniConfig = Join-Path (Join-Path $root '.runtime\omniverse-config') "run-$PID"
$cache = Join-Path $root '.cache\ov'
$data = Join-Path $root '.cache\ov-data'
$logs = Join-Path $root 'logs\ov'
foreach ($path in @($omniConfig, $cache, $data, $logs)) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}
$unixCache = $cache.Replace('\', '/')
$unixData = $data.Replace('\', '/')
$unixLogs = $logs.Replace('\', '/')
$omniToml = @"
[paths]
cache_root = "$unixCache"
data_root = "$unixData"
logs_root = "$unixLogs"
"@
[System.IO.File]::WriteAllText((Join-Path $omniConfig 'omniverse.toml'), $omniToml, (New-Object System.Text.UTF8Encoding($false)))

$env:OMNI_CONFIG_PATH = $omniConfig
$env:PYTHONPATH = $sourceDirs -join [IO.Path]::PathSeparator
$env:PIP_CACHE_DIR = Join-Path $root '.cache\pip'
$env:TEMP = Join-Path $root '.cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

Push-Location $root
try {
    & $python @PythonArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
