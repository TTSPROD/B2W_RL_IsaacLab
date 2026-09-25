[CmdletBinding()]
param(
    [ValidateSet('flat', 'rough', 'stair_up', 'stair_down', 'map')]
    [string]$Terrain = 'flat',
    [string]$Policy = '',
    [ValidateRange(0, 3)][int]$GamepadIndex = 0,
    [ValidateRange(0.01, 1.0)][double]$MaxForward = 1.0,
    [ValidateRange(0.01, 1.0)][double]$MaxLateral = 1.0,
    [ValidateRange(0.01, 1.0)][double]$MaxYaw = 1.0,
    [string]$TerrainFamily = 'random_rough',
    [ValidateRange(0, 9)][int]$TerrainLevel = 9,
    [int]$Seed = 2002,
    [ValidateSet('cpu', 'cuda:0')][string]$Device = 'cpu',
    [ValidateRange(30, 240)][int]$Fps = 144,
    [ValidateRange(0, 1000000)][int]$SmokeSteps = 0
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $Policy) { $Policy = Join-Path $projectRoot 'policies/server/upstream_19999/export/policy.pt' }
$policyPath = (Resolve-Path -LiteralPath $Policy -ErrorAction Stop).Path
$sceneName = if ($Terrain -like 'stair_*') { 'stair' } else { $Terrain }
$entrypoint = if ($SmokeSteps) { 'play_b2w_gamepad.py' } else { 'view_b2w_gamepad_3d.py' }
$pythonArgs = @((Join-Path $PSScriptRoot $entrypoint), '--policy', $policyPath,
    '--terrain', $sceneName, '--gamepad-index', $GamepadIndex,
    '--max-forward', $MaxForward, '--max-lateral', $MaxLateral, '--max-yaw', $MaxYaw,
    '--device', $Device, '--seed', $Seed)
if ($Terrain -like 'stair_*') { $pythonArgs += @('--stair-direction', $Terrain.Substring(6)) }
if ($Terrain -eq 'rough') { $pythonArgs += @('--terrain-family', $TerrainFamily, '--terrain-level', $TerrainLevel) }
if ($SmokeSteps) { $pythonArgs += @('--smoke-steps', $SmokeSteps) } else { $pythonArgs += @('--fps', $Fps) }
Push-Location $projectRoot
try {
    if ($SmokeSteps) {
        $smokeOutput = @(& (Join-Path $PSScriptRoot 'run_local.ps1') @pythonArgs)
        $runExit = $LASTEXITCODE
        $smokeOutput | Write-Output
        if ($runExit -ne 0 -or -not ($smokeOutput -match '^ISAAC_GAMEPAD_SMOKE=')) {
            throw 'Isaac smoke did not reach the completion marker; inspect the traceback above.'
        }
        exit 0
    }
    & (Join-Path $PSScriptRoot 'run_local.ps1') @pythonArgs
    exit $LASTEXITCODE
} finally { Pop-Location }
