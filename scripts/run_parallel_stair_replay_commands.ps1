param(
    [Parameter(Mandatory)][string]$ParentCheckpoint,
    [Parameter(Mandatory)][string]$ExpectedSha256,
    [ValidateSet('smoke', 'full')][string]$Mode = 'smoke',
    [ValidateSet('control', 'diverse_replay')][string]$Variant = 'diverse_replay'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$parent = (Resolve-Path -LiteralPath $ParentCheckpoint).Path
if ((Get-FileHash -LiteralPath $parent -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedSha256.ToLowerInvariant()) {
    throw 'Parent checkpoint hash mismatch'
}
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$labelRoot = "stair_replay_${Variant}_2048_20260923"
$iterations = if ($Mode -eq 'smoke') { '1' } else { '50' }
$jobs = @()
$common = @(
    'scripts/train_stair_b2w.py', '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
    '--headless', '--parent-checkpoint', $parent, '--stop-on-landing', '--restart-after-stop',
    '--cycle-protocol-v3', '--landing-tiles-fraction', '0.1', '--landing-start-probability', '1.0',
    '--inverse-rough-fraction', '0.05', '--max-stair-rise', '0.16', '--min-stair-run', '0.30',
    '--brake-profile', '--brake-distance', '1.2', '--brake-min-speed', '0.25',
    '--up-fraction', '0.35', '--rough-replay-fraction', '0.15', '--num_envs', '2048'
)

foreach ($seed in @(54, 55)) {
    $label = "${labelRoot}_seed${seed}_${Mode}"
    $stdout = Join-Path $root "logs/train_$label.stdout.log"
    $stderr = Join-Path $root "logs/train_$label.stderr.log"
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
        throw "Output already exists for $label"
    }
    $cli = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"')) +
        $common + @('--max_iterations', $iterations, '--seed', "$seed", '--run_name', $label)
    if ($Variant -eq 'diverse_replay') { $cli += '--diverse-replay-commands' }
    if ($Mode -eq 'smoke') {
        $cli += @('--reset-probe', '--rough-reset-probe')
        if ($Variant -eq 'diverse_replay') { $cli += '--replay-command-probe' }
    }
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{ Label = $label; Process = $process; Stdout = $stdout; Stderr = $stderr }
    Write-Output "START $label PID=$($process.Id)"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    $loaded = Select-String -LiteralPath $job.Stdout -Pattern 'B2W_STAIR_PARENT_LOADED' -Quiet
    $trained = Select-String -LiteralPath $job.Stdout -Pattern 'Training time:' -Quiet
    $resetProbes = $Mode -ne 'smoke' -or (
        (Select-String -LiteralPath $job.Stdout -Pattern 'B2W_LANDING_RESET_PROBE=' -Quiet) -and
        (Select-String -LiteralPath $job.Stdout -Pattern 'B2W_INVERSE_RESET_PROBE=' -Quiet))
    $commandProbe = $Mode -ne 'smoke' -or $Variant -ne 'diverse_replay' -or
        (Select-String -LiteralPath $job.Stdout -Pattern 'B2W_REPLAY_COMMAND_PROBE=' -Quiet)
    Write-Output "DONE $($job.Label) exit=$($job.Process.ExitCode) loaded=$loaded trained=$trained reset_probes=$resetProbes command_probe=$commandProbe"
    if ($job.Process.ExitCode -ne 0 -or -not $loaded -or -not $trained -or -not $resetProbes -or -not $commandProbe) {
        throw "Run failed: $($job.Label); see $($job.Stdout) and $($job.Stderr)"
    }
}
