param(
    [ValidateSet('smoke', 'pilot')]
    [string]$Mode = 'smoke'
)

$ErrorActionPreference = 'Stop'
if ($env:B2W_PAYLOAD_URDF) { throw 'This experiment requires nominal B2W without B2W_PAYLOAD_URDF' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$runs = @(Get-ChildItem -LiteralPath $runRoot -Directory | Where-Object {
    $_.Name.EndsWith('_cycle57_v1_A_full_seed54_20260924_094742')
})
if ($runs.Count -ne 1) { throw "Expected one cycle57 A run; found $($runs.Count)" }
$parent = Join-Path $runs[0].FullName 'model_3000.pt'
$expectedParentSha = '20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17'
$actualParentSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $parent).Hash.ToLowerInvariant()
if ($actualParentSha -ne $expectedParentSha) { throw "Parent SHA mismatch: $actualParentSha" }

$failureUp = Join-Path $root 'logs/failure_replay_cycle57_A_model3000_up_seed3001.json'
$failureDown = Join-Path $root 'logs/failure_replay_cycle57_A_model3000_down_seed3001.json'
foreach ($path in @($failureUp, $failureDown)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing captured failure states: $path" }
}

$updates = if ($Mode -eq 'smoke') { 1 } else { 25 }
$numEnvs = if ($Mode -eq 'smoke') { 64 } else { 4096 }
$saveInterval = if ($Mode -eq 'smoke') { 1 } else { 5 }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$label = "cycle57_failure_replay_lr1e5_${Mode}_seed54_$stamp"
$cli = @(
    'scripts/train_stair_b2w.py',
    '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
    '--headless',
    '--parent-checkpoint', $parent,
    '--fresh-optimizer',
    '--learning-rate', '1e-5',
    '--save-interval', "$saveInterval",
    '--stop-on-landing',
    '--restart-after-stop',
    '--cycle-protocol-v3',
    '--diverse-replay-commands',
    '--stop-speed-reward-weight', '1.0',
    '--landing-tiles-fraction', '0.1',
    '--landing-start-probability', '1.0',
    '--failure-replay-up', $failureUp,
    '--failure-replay-down', $failureDown,
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
if ($Mode -eq 'smoke') {
    # Failure-replay states intentionally retain their captured dynamic root
    # height, so the static landing-height probe does not apply here.
    $cli += @('--rough-reset-probe', '--replay-command-probe', '--failure-replay-probe')
}

Write-Output "CYCLE57_FAILURE_REPLAY_START label=$label mode=$Mode envs=$numEnvs updates=$updates parent_sha=$actualParentSha"
& $launcher @cli
if ($LASTEXITCODE -ne 0) { throw "cycle57 failure-replay trainer failed with exit code $LASTEXITCODE" }
Write-Output "CYCLE57_FAILURE_REPLAY_COMPLETE label=$label"
