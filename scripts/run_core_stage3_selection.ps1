# Historical entrypoint; process ownership is centralized in the dashboard.
param(
    [string]$Base = 'logs/core_stage3_selection_20260929',
    [int]$Parallel = 1
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'run_local.ps1') scripts/run_core_locomotion_eval.py --base $Base --max-parallel $Parallel --protocol-module core_stage3_selection_protocol
exit $LASTEXITCODE
