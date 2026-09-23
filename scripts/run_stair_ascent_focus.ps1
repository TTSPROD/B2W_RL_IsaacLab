param(
    [Parameter(Mandatory)][string]$ParentCheckpoint,
    [Parameter(Mandatory)][string]$ExpectedSha256,
    [ValidateSet('smoke', 'full')][string]$Mode = 'smoke'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$parent = (Resolve-Path -LiteralPath $ParentCheckpoint).Path
$actualHash = (Get-FileHash -LiteralPath $parent -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) {
    throw 'Parent checkpoint hash mismatch'
}

$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$iterations = if ($Mode -eq 'smoke') { '1' } else { '50' }
$jobs = @()
$common = @(
    'scripts/train_stair_b2w.py', '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
    '--headless', '--parent-checkpoint', $parent, '--fresh-optimizer',
    '--stop-on-landing', '--restart-after-stop', '--cycle-protocol-v3',
    '--landing-tiles-fraction', '0.1', '--landing-start-probability', '1.0',
    '--inverse-rough-fraction', '0.05', '--max-stair-rise', '0.16', '--min-stair-run', '0.30',
    '--brake-profile', '--brake-distance', '1.2', '--brake-min-speed', '0.25',
    '--up-fraction', '0.45', '--rough-replay-fraction', '0.15', '--num_envs', '2048'
)

foreach ($seed in @(54, 55)) {
    $label = "stair_ascent45_57d_2048_20260923_seed${seed}_${Mode}"
    $stdout = Join-Path $root "logs/train_$label.stdout.log"
    $stderr = Join-Path $root "logs/train_$label.stderr.log"
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
        throw "Output already exists for $label"
    }
    $cli = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"')) +
        $common + @('--max_iterations', $iterations, '--seed', "$seed", '--run_name', $label)
    if ($Mode -eq 'smoke') { $cli += @('--reset-probe', '--rough-reset-probe') }
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{ Label = $label; Process = $process; Stdout = $stdout; Stderr = $stderr }
    Write-Output "START $label PID=$($process.Id)"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    $exitCode = $job.Process.ExitCode
    $loaded57 = Select-String -LiteralPath $job.Stdout -Pattern 'B2W_STAIR_PARENT_WEIGHTS_LOADED fresh_optimizer=true' -Quiet
    $task57 = Select-String -LiteralPath $job.Stdout -Pattern '"actor_observation_dim": 57' -Quiet
    $mix = Select-String -LiteralPath $job.Stdout -Pattern '"up_fraction": 0.45, "down_fraction": 0.24999999999999994' -Quiet
    $trained = Select-String -LiteralPath $job.Stdout -Pattern 'Training time:' -Quiet
    $probes = $Mode -ne 'smoke' -or (
        (Select-String -LiteralPath $job.Stdout -Pattern 'B2W_LANDING_RESET_PROBE=' -Quiet) -and
        (Select-String -LiteralPath $job.Stdout -Pattern 'B2W_INVERSE_RESET_PROBE=' -Quiet)
    )
    $exitOk = $null -eq $exitCode -or $exitCode -eq 0
    Write-Output "DONE $($job.Label) exit=$exitCode loaded57=$loaded57 task57=$task57 mix=$mix trained=$trained probes=$probes"
    if (-not $exitOk -or -not $loaded57 -or -not $task57 -or -not $mix -or -not $trained -or -not $probes) {
        throw "Run failed: $($job.Label); see $($job.Stdout) and $($job.Stderr)"
    }
}
