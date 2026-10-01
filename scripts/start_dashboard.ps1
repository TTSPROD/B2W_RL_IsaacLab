$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'run_local.ps1') dashboard/launch.py --view jobs --open
exit $LASTEXITCODE
