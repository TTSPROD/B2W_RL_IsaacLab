param([switch]$FullSuite)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$bench = Join-Path $root 'logs/stair_benchmark'
$outDir = Join-Path $root 'logs/stair_hold_wheel_screen_20260923'
New-Item -ItemType Directory -Force $outDir | Out-Null
$config = if ($FullSuite) { 'configs/stair_eval_v3.json' } else { 'configs/stair_eval_v3_screen_14_32.json' }
$suffix = if ($FullSuite) { 'v3open128' } else { 'screen14x32' }
$expectedFiles = if ($FullSuite) { 6 } else { 2 }
$expectedEnvs = $expectedFiles * 128
$parents = @(
    [pscustomobject]@{Seed=54; Directory='2026-09-23_11-02-18_stair_basevel_control57_2048_20260923_seed54_full'; Sha='49c50eabfc3d9ce640dc3cc46fb15f45fb8f071351e53a768afc2a406b474801'},
    [pscustomobject]@{Seed=55; Directory='2026-09-23_11-04-25_stair_basevel_control57_2048_20260923_seed55_full'; Sha='f5d7403f98853374b3cdaf6dc329461b29f0f0658e308c0d6a47b890c2371ff2'}
)
$jobs = @()
foreach ($parent in $parents) {
    $checkpoint = Join-Path (Join-Path $runRoot $parent.Directory) 'model_398.pt'
    if ((Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash.ToLowerInvariant() -ne $parent.Sha) {
        throw "Parent hash mismatch for seed $($parent.Seed)"
    }
    $label = "holdwheel0p0ramp10_control57_s$($parent.Seed)_$suffix"
    if (Get-ChildItem -LiteralPath $bench -Filter "${label}_cycle_*.json" -ErrorAction SilentlyContinue) {
        throw "Output exists for $label"
    }
    $stdout = Join-Path $outDir "$label.stdout.log"
    $stderr = Join-Path $outDir "$label.stderr.log"
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        'scripts/eval_stair_suite.py', '--checkpoint', ('"' + $checkpoint + '"'),
        '--label', $label, '--config', $config, '--split', 'development',
        '--brake-profile', '--brake-distance', '1.2', '--brake-min-speed', '0.25',
        '--hold-wheel-action-scale', '0.0', '--hold-wheel-ramp-steps', '10'
    )
    $process = Start-Process powershell.exe -ArgumentList $cli -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{Label=$label; Process=$process}
    Write-Output "START $label PID=$($process.Id) actor=57 action=16"
}
foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    if ($job.Process.ExitCode -ne 0) { throw "Evaluation failed for $($job.Label)" }
    $files = @(Get-ChildItem -LiteralPath $bench -Filter "$($job.Label)_cycle_*.json")
    if ($files.Count -ne $expectedFiles) { throw "Unexpected output count for $($job.Label)" }
    $metrics = @($files | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json })
    Write-Output "DONE $($job.Label) passage=$(($metrics | Measure-Object passage_success -Sum).Sum)/$expectedEnvs cycle=$(($metrics | Measure-Object success -Sum).Sum)/$expectedEnvs unsafe=$(($metrics | Measure-Object unsafe -Sum).Sum) stop_failed=$(($metrics | Measure-Object stop_failed -Sum).Sum) incomplete=$(($metrics | Measure-Object incomplete -Sum).Sum)"
}
