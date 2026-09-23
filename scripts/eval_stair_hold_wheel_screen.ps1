$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$bench = Join-Path $root 'logs/stair_benchmark'
$outDir = Join-Path $root 'logs/stair_hold_wheel_screen_20260923'
New-Item -ItemType Directory -Force $outDir | Out-Null

$parents = @(
    [pscustomobject]@{Seed=54; Directory='2026-09-23_11-02-18_stair_basevel_control57_2048_20260923_seed54_full'; Sha='49c50eabfc3d9ce640dc3cc46fb15f45fb8f071351e53a768afc2a406b474801'},
    [pscustomobject]@{Seed=55; Directory='2026-09-23_11-04-25_stair_basevel_control57_2048_20260923_seed55_full'; Sha='f5d7403f98853374b3cdaf6dc329461b29f0f0658e308c0d6a47b890c2371ff2'}
)

foreach ($scale in @(0.5, 0.0)) {
    $scaleLabel = $scale.ToString('0.0', [Globalization.CultureInfo]::InvariantCulture).Replace('.', 'p')
    $jobs = @()
    foreach ($parent in $parents) {
        $checkpoint = Join-Path (Join-Path $runRoot $parent.Directory) 'model_398.pt'
        if (-not (Test-Path -LiteralPath $checkpoint)) { throw "Missing parent: $checkpoint" }
        $actualSha = (Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualSha -ne $parent.Sha) { throw "Parent hash mismatch for seed $($parent.Seed)" }
        $label = "holdwheel${scaleLabel}_control57_s$($parent.Seed)_screen14x32"
        if (Get-ChildItem -LiteralPath $bench -Filter "${label}_cycle_*.json" -ErrorAction SilentlyContinue) {
            throw "Output exists for $label"
        }
        $stdout = Join-Path $outDir "$label.stdout.log"
        $stderr = Join-Path $outDir "$label.stderr.log"
        $cli = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
            'scripts/eval_stair_suite.py', '--checkpoint', ('"' + $checkpoint + '"'),
            '--label', $label, '--config', 'configs/stair_eval_v3_screen_14_32.json',
            '--split', 'development', '--brake-profile', '--brake-distance', '1.2',
            '--brake-min-speed', '0.25', '--hold-wheel-action-scale',
            $scale.ToString([Globalization.CultureInfo]::InvariantCulture)
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
        if ($files.Count -ne 2) { throw "Expected two outputs for $($job.Label)" }
        $metrics = @($files | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json })
        Write-Output "DONE $($job.Label) passage=$(($metrics | Measure-Object passage_success -Sum).Sum)/256 cycle=$(($metrics | Measure-Object success -Sum).Sum)/256 unsafe=$(($metrics | Measure-Object unsafe -Sum).Sum) stop_failed=$(($metrics | Measure-Object stop_failed -Sum).Sum) incomplete=$(($metrics | Measure-Object incomplete -Sum).Sum)"
    }
}
