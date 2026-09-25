[CmdletBinding()]
param(
    [ValidateSet('flat', 'stair_up', 'stair_down', 'scene')]
    [string]$Terrain = 'flat',
    [string]$Policy = '',
    [string]$Xml = '',
    [ValidateRange(0, 3)]
    [int]$GamepadIndex = 0,
    [ValidateRange(0.01, 1.0)]
    [double]$MaxForward = 0.7,
    [ValidateRange(0.01, 1.0)]
    [double]$MaxLateral = 0.4,
    [ValidateRange(0.01, 1.0)]
    [double]$MaxYaw = 0.5,
    [ValidateRange(0, 1000000)]
    [int]$SmokeSteps = 0,
    [string]$Log = '',
    [string]$RecordCommands = '',
    [string]$ReplayCommands = '',
    [switch]$HeadlessReplay,
    [ValidateSet('auto', 'reset', 'stop')]
    [string]$UnsafeAction = 'auto',
    [ValidateRange(0.1, 30.0)]
    [double]$PreFailureWindowSeconds = 2.0
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runner = Join-Path $PSScriptRoot 'run_local.ps1'
$entrypoint = Join-Path $PSScriptRoot 'play_mujoco_b2w_gamepad.py'
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing local runtime launcher: $runner"
}

$pythonArgs = @(
    $entrypoint,
    '--terrain', $Terrain,
    '--gamepad-index', $GamepadIndex,
    '--max-forward', $MaxForward,
    '--max-lateral', $MaxLateral,
    '--max-yaw', $MaxYaw,
    '--unsafe-action', $UnsafeAction,
    '--pre-failure-window-s', $PreFailureWindowSeconds
)
if ($SmokeSteps -gt 0) {
    $pythonArgs += @('--smoke-steps', $SmokeSteps)
}
if ($Policy) {
    $resolvedPolicy = (Resolve-Path -LiteralPath $Policy -ErrorAction Stop).Path
    $pythonArgs += @('--policy', $resolvedPolicy)
}
if ($Xml) {
    $resolvedXml = (Resolve-Path -LiteralPath $Xml -ErrorAction Stop).Path
    $pythonArgs += @('--xml', $resolvedXml)
}
if ($Log) {
    $resolvedLog = if ([IO.Path]::IsPathRooted($Log)) {
        [IO.Path]::GetFullPath($Log)
    } else {
        [IO.Path]::GetFullPath((Join-Path $root $Log))
    }
    $pythonArgs += @('--log', $resolvedLog)
}
if ($RecordCommands) {
    $resolvedRecord = if ([IO.Path]::IsPathRooted($RecordCommands)) {
        [IO.Path]::GetFullPath($RecordCommands)
    } else {
        [IO.Path]::GetFullPath((Join-Path $root $RecordCommands))
    }
    $pythonArgs += @('--record-commands', $resolvedRecord)
}
if ($ReplayCommands) {
    $resolvedReplay = (Resolve-Path -LiteralPath $ReplayCommands -ErrorAction Stop).Path
    $pythonArgs += @('--replay-commands', $resolvedReplay)
}
if ($HeadlessReplay) {
    $pythonArgs += '--headless-replay'
}

Push-Location $root
try {
    & $runner @pythonArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
