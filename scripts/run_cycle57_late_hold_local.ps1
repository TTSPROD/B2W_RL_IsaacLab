param(
    [ValidateSet('smoke', 'pilot')]
    [string]$Mode = 'smoke'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$protocolPath = Join-Path $root 'configs\cycle57_late_hold_v1.json'
$protocol = Get-Content -LiteralPath $protocolPath -Raw | ConvertFrom-Json
$parent = Join-Path $root ($protocol.parent.path -replace '/', '\')

if (-not (Test-Path -LiteralPath $parent)) { throw "Missing cycle57 parent: $parent" }
$parentSha = (Get-FileHash -LiteralPath $parent -Algorithm SHA256).Hash.ToLowerInvariant()
if ($parentSha -ne $protocol.parent.sha256) { throw "Parent SHA mismatch: $parentSha" }

$updates = if ($Mode -eq 'smoke') { 1 } else { [int]$protocol.training.pilot_updates }
$numEnvs = if ($Mode -eq 'smoke') { 64 } else { [int]$protocol.training.environments }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$label = "cycle57_late_hold_v1_${Mode}_seed$($protocol.training.seed)_${stamp}"
$reward = $protocol.variants[0].late_hold_speed_penalty

$cli = @(
    'scripts/train_stair_b2w.py',
    '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
    '--headless',
    '--parent-checkpoint', $parent,
    '--learning-rate', "$($protocol.training.learning_rate)",
    '--save-interval', "$($protocol.training.save_interval_updates)",
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
    '--late-hold-speed-penalty-weight', "$(-[double]$reward.weight)",
    '--late-hold-start-step', "$($reward.start_step)",
    '--late-hold-speed-threshold', "$($reward.speed_threshold_m_s)",
    '--num_envs', "$numEnvs",
    '--max_iterations', "$updates",
    '--seed', "$($protocol.training.seed)",
    '--run_name', $label
)
if ($Mode -eq 'smoke') {
    $cli += @('--reset-probe', '--rough-reset-probe', '--replay-command-probe')
}

Write-Output "CYCLE57_LATE_HOLD_START label=$label mode=$Mode envs=$numEnvs updates=$updates parent_sha=$parentSha"
& $launcher @cli
if ($LASTEXITCODE -ne 0) { throw "cycle57 late-hold trainer failed with exit code $LASTEXITCODE" }
Write-Output "CYCLE57_LATE_HOLD_COMPLETE label=$label"
