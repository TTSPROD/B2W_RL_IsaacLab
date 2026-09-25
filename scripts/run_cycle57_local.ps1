param(
    [ValidateSet('A', 'B', 'C', 'D')]
    [string]$Variant = 'A',
    [ValidateSet('smoke', 'pilot', 'full')]
    [string]$Mode = 'smoke'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$parent = Join-Path $root 'artifacts\upstream\inverse57_4gpu_20260923\final\selected_policy.pt'
$expectedParentSha = '73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa'

if (-not (Test-Path -LiteralPath $parent)) { throw "Missing inverse57 update3000 parent: $parent" }
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $actualParentSha = ([BitConverter]::ToString(
        $sha256.ComputeHash([IO.File]::ReadAllBytes($parent))) -replace '-', '').ToLowerInvariant()
}
finally {
    $sha256.Dispose()
}
if ($actualParentSha -ne $expectedParentSha) { throw "Parent SHA mismatch: $actualParentSha" }

$updates = switch ($Mode) {
    'smoke' { 1 }
    'pilot' { 50 }
    'full' { 1000 }
}
$numEnvs = if ($Mode -eq 'smoke') { 64 } else { 4096 }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$label = "cycle57_v1_${Variant}_${Mode}_seed54_${stamp}"

$cli = @(
    'scripts/train_stair_b2w.py',
    '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
    '--headless',
    '--parent-checkpoint', $parent,
    '--learning-rate', '5e-5',
    '--stop-on-landing',
    '--restart-after-stop',
    '--cycle-protocol-v3',
    '--diverse-replay-commands',
    '--landing-tiles-fraction', '0.1',
    '--landing-start-probability', '1.0',
    '--inverse-rough-fraction', '0.25',
    '--rough-replay-fraction', '0.45',
    '--up-fraction', '0.20',
    '--max-stair-rise', '0.19',
    '--min-stair-run', '0.27',
    '--brake-profile',
    '--brake-distance', '1.2',
    '--brake-min-speed', '0.25',
    '--num_envs', "$numEnvs",
    '--max_iterations', "$updates",
    '--seed', '54',
    '--run_name', $label
)

if ($Variant -eq 'B') {
    $cli += @('--stop-speed-reward-weight', '1.0')
}
if ($Variant -eq 'C') {
    $cli += @('--passage-reward-weight', '100.0', '--hold-reward-weight', '100.0')
}
if ($Variant -eq 'D') {
    $cli += @('--hold-reward-weight', '100.0')
}
if ($Mode -eq 'smoke') {
    $cli += @('--reset-probe', '--rough-reset-probe', '--replay-command-probe')
}

Write-Output "CYCLE57_START label=$label variant=$Variant mode=$Mode envs=$numEnvs updates=$updates parent_sha=$actualParentSha"
& $launcher @cli
if ($LASTEXITCODE -ne 0) { throw "cycle57 trainer failed with exit code $LASTEXITCODE" }
Write-Output "CYCLE57_COMPLETE label=$label"
