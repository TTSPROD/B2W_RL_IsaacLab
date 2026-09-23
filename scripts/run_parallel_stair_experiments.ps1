param(
    [ValidateSet('smoke', 'full')][string]$Mode = 'smoke',
    [ValidateSet('control', 'passage_bonus', 'late_brake', 'stop_speed', 'stop_speed_1', 'all')][string]$Variant = 'control'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$parent = Join-Path $root 'logs/rsl_rl/unitree_b2w_rough/2026-09-21_11-29-39_rough_from_flat54_stage1/model_349.pt'
if (-not (Test-Path -LiteralPath $parent)) { throw 'Pinned parent checkpoint is missing' }
$expected = '916bf5c5b4e5ca43ecfacd4bde6c5a92b164b9c0a6d5c9257a6c7ed68662febf'
if ((Get-FileHash -LiteralPath $parent -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
    throw 'Pinned parent checkpoint hash mismatch'
}

$variants = if ($Variant -eq 'all') { @('control', 'passage_bonus', 'late_brake') } else { @($Variant) }
$common = @(
    'scripts/train_stair_b2w.py', '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
    '--headless', '--parent-checkpoint', $parent, '--stop-on-landing', '--restart-after-stop',
    '--cycle-protocol-v3', '--landing-tiles-fraction', '0.1', '--landing-start-probability', '1.0',
    '--inverse-rough-fraction', '0.05', '--max-stair-rise', '0.16', '--min-stair-run', '0.30',
    '--brake-profile', '--brake-min-speed', '0.25', '--num_envs', '2048'
)
$plan = @{
    control       = @{ brake = '1.2'; passage = '0'; stop = '0' }
    passage_bonus = @{ brake = '1.2'; passage = '25'; stop = '0' }
    late_brake    = @{ brake = '0.8'; passage = '0'; stop = '0' }
    stop_speed    = @{ brake = '1.2'; passage = '0'; stop = '2.0' }
    stop_speed_1  = @{ brake = '1.2'; passage = '0'; stop = '1.0' }
}

foreach ($name in $variants) {
    $cfg = $plan[$name]
    $jobs = @()
    foreach ($seed in @(54, 55)) {
        $label = "v3_2048_${name}_seed${seed}_$Mode"
        $stdout = Join-Path $root "logs/train_$label.stdout.log"
        $stderr = Join-Path $root "logs/train_$label.stderr.log"
        if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
            throw "Output already exists for $label"
        }
        $iterations = if ($Mode -eq 'smoke') { '1' } else { '50' }
        $cli = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"')) +
            $common + @('--up-fraction', '0.35', '--rough-replay-fraction', '0.15',
                '--brake-distance', $cfg.brake, '--max_iterations', $iterations,
                '--seed', "$seed", '--run_name', $label)
        if ($cfg.passage -ne '0') { $cli += @('--passage-reward-weight', $cfg.passage) }
        if ($cfg.stop -ne '0') { $cli += @('--stop-speed-reward-weight', $cfg.stop) }
        if ($Mode -eq 'smoke') { $cli += @('--reset-probe', '--rough-reset-probe') }
        $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
            -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        $jobs += [pscustomobject]@{ Label = $label; Process = $process; Stdout = $stdout; Stderr = $stderr }
        Write-Output "START $label PID=$($process.Id)"
    }
    foreach ($job in $jobs) {
        $job.Process.WaitForExit()
        $job.Process.Refresh()
        $tail = Get-Content -LiteralPath $job.Stdout -Tail 120 -ErrorAction SilentlyContinue
        $probeOk = $Mode -ne 'smoke' -or ((Select-String -LiteralPath $job.Stdout -Pattern 'B2W_LANDING_RESET_PROBE=' -Quiet) -and
            (Select-String -LiteralPath $job.Stdout -Pattern 'B2W_INVERSE_RESET_PROBE=' -Quiet))
        $trainingOk = $tail -match 'Training time:'
        Write-Output "DONE $($job.Label) exit=$($job.Process.ExitCode) training=$([bool]$trainingOk) probes=$([bool]$probeOk)"
        if ($job.Process.ExitCode -ne 0 -or -not $trainingOk -or -not $probeOk) {
            throw "Run failed: $($job.Label); see $($job.Stdout) and $($job.Stderr)"
        }
    }
}
