param(
    [ValidateSet('A', 'B', 'C')]
    [string]$Variant = 'A',
    [ValidateSet('smoke', 'pilot', 'full')]
    [string]$Mode = 'smoke'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$generator = Join-Path $PSScriptRoot 'generate_b2w_payload_urdf.py'
$python = Join-Path $root '.venv\Scripts\python.exe'
$payloadUrdf = Join-Path $root '.cache\assets\b2w_payload_v1\b2w_payload_v1.urdf'
$parent = if ($Variant -eq 'C') {
    Join-Path $root 'logs\rsl_rl\unitree_b2w_stair\2026-09-24_12-06-40_payload57_v1_B_pilot_seed58_20260924_120634\model_3098.pt'
} else {
    Join-Path $root 'artifacts\upstream\inverse57_4gpu_20260923\final\selected_policy.pt'
}
$expectedParentSha = if ($Variant -eq 'C') {
    '4fac5e083e334790933e2cec755f97f833f52b995bb53b8097120d42bd000c7c'
} else {
    '73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa'
}

if (-not (Test-Path -LiteralPath $parent)) { throw "Missing inverse57 update3000 parent: $parent" }
$actualParentSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $parent).Hash.ToLowerInvariant()
if ($actualParentSha -ne $expectedParentSha) { throw "Parent SHA mismatch: $actualParentSha" }

& $python $generator --output $payloadUrdf | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $payloadUrdf)) {
    throw 'Payload URDF generation failed'
}

$updates = switch ($Mode) {
    'smoke' { 1 }
    'pilot' { if ($Variant -eq 'C') { 50 } else { 100 } }
    'full' { 500 }
}
$numEnvs = if ($Mode -eq 'smoke') { 64 } else { 4096 }
$seed = if ($Variant -eq 'C') { 59 } else { 58 }
$learningRate = if ($Variant -eq 'C') { '2e-5' } else { '5e-5' }
$roughReplayFraction = if ($Variant -eq 'C') { '0.35' } else { '0.45' }
$inverseRoughFraction = if ($Variant -eq 'C') { '0.20' } else { '0.25' }
$upFraction = if ($Variant -eq 'C') { '0.25' } else { '0.20' }
$observationNoiseScale = if ($Variant -eq 'C') { '1.25' } else { '1.0' }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$label = "payload57_v1_${Variant}_${Mode}_seed${seed}_${stamp}"

$cli = @(
    'scripts/train_stair_b2w.py',
    '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
    '--headless',
    '--parent-checkpoint', $parent,
    '--learning-rate', $learningRate,
    '--observation-noise-scale', $observationNoiseScale,
    '--stop-on-landing',
    '--restart-after-stop',
    '--cycle-protocol-v3',
    '--diverse-replay-commands',
    '--landing-tiles-fraction', '0.1',
    '--landing-start-probability', '1.0',
    '--inverse-rough-fraction', $inverseRoughFraction,
    '--rough-replay-fraction', $roughReplayFraction,
    '--up-fraction', $upFraction,
    '--max-stair-rise', '0.19',
    '--min-stair-run', '0.27',
    '--brake-profile',
    '--brake-distance', '1.2',
    '--brake-min-speed', '0.25',
    '--num_envs', "$numEnvs",
    '--max_iterations', "$updates",
    '--seed', "$seed",
    '--run_name', $label
)
if ($Mode -eq 'smoke') {
    $cli += @('--reset-probe', '--rough-reset-probe', '--replay-command-probe')
}
if ($Variant -in @('B', 'C')) {
    $cli += @('--stop-speed-reward-weight', '1.0')
}
$previousPayloadUrdf = $env:B2W_PAYLOAD_URDF
$env:B2W_PAYLOAD_URDF = $payloadUrdf
try {
    Write-Output "PAYLOAD57_START label=$label variant=$Variant mode=$Mode envs=$numEnvs updates=$updates payload_kg=11 parent_sha=$actualParentSha"
    & $launcher @cli
    if ($LASTEXITCODE -ne 0) { throw "Payload trainer failed with exit code $LASTEXITCODE" }
    Write-Output "PAYLOAD57_COMPLETE label=$label"
}
finally {
    $env:B2W_PAYLOAD_URDF = $previousPayloadUrdf
}
