param([ValidateSet('smoke', 'full')][string]$Mode = 'smoke')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$parents = @(
    [pscustomobject]@{Seed=54; Directory='2026-09-23_11-02-18_stair_basevel_control57_2048_20260923_seed54_full'; Sha='49c50eabfc3d9ce640dc3cc46fb15f45fb8f071351e53a768afc2a406b474801'},
    [pscustomobject]@{Seed=55; Directory='2026-09-23_11-04-25_stair_basevel_control57_2048_20260923_seed55_full'; Sha='f5d7403f98853374b3cdaf6dc329461b29f0f0658e308c0d6a47b890c2371ff2'}
)
$iterations = if ($Mode -eq 'smoke') { '1' } else { '25' }
$jobs = @()
foreach ($item in $parents) {
    $parent = Join-Path (Join-Path $runRoot $item.Directory) 'model_398.pt'
    if ((Get-FileHash -LiteralPath $parent -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Sha) {
        throw "Parent hash mismatch for seed $($item.Seed)"
    }
    $label = "stair_wheel_head_only_2048_20260923_seed$($item.Seed)_$Mode"
    $stdout = Join-Path $root "logs/train_$label.stdout.log"
    $stderr = Join-Path $root "logs/train_$label.stderr.log"
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) { throw "Output exists for $label" }
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        'scripts/train_stair_b2w.py', '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
        '--headless', '--parent-checkpoint', ('"' + $parent + '"'), '--fresh-optimizer',
        '--wheel-head-only', '--stop-speed-reward-weight', '1.0',
        '--stop-on-landing', '--restart-after-stop', '--cycle-protocol-v3',
        '--landing-tiles-fraction', '0.1', '--landing-start-probability', '1.0',
        '--inverse-rough-fraction', '0.05', '--max-stair-rise', '0.16', '--min-stair-run', '0.30',
        '--brake-profile', '--brake-distance', '1.2', '--brake-min-speed', '0.25',
        '--up-fraction', '0.35', '--rough-replay-fraction', '0.15', '--num_envs', '2048',
        '--max_iterations', $iterations, '--seed', "$($item.Seed)", '--run_name', $label
    )
    if ($Mode -eq 'smoke') { $cli += @('--reset-probe', '--rough-reset-probe') }
    $process = Start-Process powershell.exe -ArgumentList $cli -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{Label=$label; Seed=$item.Seed; Parent=$parent; Process=$process; Stdout=$stdout; Stderr=$stderr}
    Write-Output "START $label PID=$($process.Id) actor=57 action=16"
}
foreach ($job in $jobs) {
    $job.Process.WaitForExit(); $job.Process.Refresh()
    $loaded = Select-String -LiteralPath $job.Stdout -Pattern 'B2W_STAIR_PARENT_WEIGHTS_LOADED fresh_optimizer=true' -Quiet
    $constrained = Select-String -LiteralPath $job.Stdout -Pattern 'B2W_WHEEL_HEAD_ONLY=' -Quiet
    $trained = Select-String -LiteralPath $job.Stdout -Pattern 'Training time:' -Quiet
    $probes = $Mode -ne 'smoke' -or ((Select-String -LiteralPath $job.Stdout -Pattern 'B2W_LANDING_RESET_PROBE=' -Quiet) -and
        (Select-String -LiteralPath $job.Stdout -Pattern 'B2W_INVERSE_RESET_PROBE=' -Quiet))
    if ($job.Process.ExitCode -ne 0 -or -not $loaded -or -not $constrained -or -not $trained -or -not $probes) {
        throw "Run failed: $($job.Label); see $($job.Stdout) and $($job.Stderr)"
    }
    if ($Mode -eq 'full') {
        $runs = @(Get-ChildItem -LiteralPath $runRoot -Directory | Where-Object {$_.Name.EndsWith("_$($job.Label)")})
        if ($runs.Count -ne 1) { throw "Run lookup failed for $($job.Label)" }
        $candidate = Join-Path $runs[0].FullName 'model_422.pt'
        & $launcher scripts/check_wheel_head_checkpoint.py --parent $job.Parent --candidate $candidate
        if ($LASTEXITCODE -ne 0) { throw "Wheel-head invariance check failed for $($job.Label)" }
    }
    Write-Output "DONE $($job.Label) loaded=$loaded constrained=$constrained trained=$trained probes=$probes"
}
