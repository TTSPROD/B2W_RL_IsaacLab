param(
    [ValidatePattern('^model_[0-9]+[.]pt$')][string]$CheckpointName = 'model_398.pt',
    [ValidatePattern('^[a-zA-Z0-9_-]*$')][string]$Tag = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$outDir = Join-Path $root 'logs/stair_ascent_focus_20260923'
$benchmarkDir = Join-Path $root 'logs/stair_benchmark'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$jobs = @()

foreach ($seed in @(54, 55)) {
    $runLabel = "stair_ascent45_57d_2048_20260923_seed${seed}_full"
    $runs = @(Get-ChildItem -LiteralPath $runRoot -Directory | Where-Object { $_.Name.EndsWith("_$runLabel") })
    if ($runs.Count -ne 1) { throw "Expected one run for $runLabel, found $($runs.Count)" }
    $checkpoint = Join-Path $runs[0].FullName $CheckpointName
    $manifest = Get-Content -LiteralPath (Join-Path $runs[0].FullName 'stair_parent.json') -Raw | ConvertFrom-Json
    if ($manifest.actor_observation_dim -ne 57 -or $manifest.actor_base_lin_vel) {
        throw "Checkpoint does not satisfy the required 57-to-16 actor ABI: $checkpoint"
    }
    $label = if ($Tag) { "ascent45_57d_s${seed}_${Tag}_v3open128" } else { "ascent45_57d_s${seed}_v3open128" }
    if (Get-ChildItem -LiteralPath $benchmarkDir -Filter "${label}_cycle_*.json" -ErrorAction SilentlyContinue) {
        throw "Suite output already exists for $label"
    }
    $stdout = Join-Path $outDir "${label}.suite.stdout.log"
    $stderr = Join-Path $outDir "${label}.suite.stderr.log"
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        'scripts/eval_stair_suite.py', '--checkpoint', ('"' + $checkpoint + '"'),
        '--label', $label, '--config', 'configs/stair_eval_v3.json', '--split', 'development',
        '--num-envs', '128', '--horizon', '900', '--brake-profile', '--brake-distance', '1.2',
        '--brake-min-speed', '0.25'
    )
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{ Label = $label; Process = $process; Stdout = $stdout; Stderr = $stderr }
    Write-Output "START $label PID=$($process.Id) manifest_actor57=true"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    $exitCode = $job.Process.ExitCode
    $exitOk = $null -eq $exitCode -or $exitCode -eq 0
    $files = @(Get-ChildItem -LiteralPath $benchmarkDir -Filter "$($job.Label)_cycle_*.json")
    if (-not $exitOk -or $files.Count -ne 6) {
        throw "Suite failed: $($job.Label); exit=$exitCode rows=$($files.Count); see $($job.Stdout) and $($job.Stderr)"
    }
    $rows = @($files | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json })
    $total = [pscustomobject]@{
        passage = ($rows | Measure-Object passage_success -Sum).Sum
        cycle = ($rows | Measure-Object success -Sum).Sum
        unsafe = ($rows | Measure-Object unsafe -Sum).Sum
        stop_failed = ($rows | Measure-Object stop_failed -Sum).Sum
        incomplete = ($rows | Measure-Object incomplete -Sum).Sum
        timeouts = ($rows | Measure-Object timeouts -Sum).Sum
    }
    Write-Output "DONE $($job.Label) passage=$($total.passage)/768 cycle=$($total.cycle)/768 unsafe=$($total.unsafe) stop_failed=$($total.stop_failed) incomplete=$($total.incomplete) timeouts=$($total.timeouts)"
}
