$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Missing project Python: $python" }
& $python (Join-Path $root 'dashboard\launch.py') --view jobs --open
exit $LASTEXITCODE
