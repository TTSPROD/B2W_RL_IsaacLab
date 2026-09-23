$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$suite = Join-Path $PSScriptRoot 'eval_stair_suite.py'
$checkpoint = Join-Path $root 'logs/rsl_rl/unitree_b2w_rough/2026-09-21_13-56-09_rough_from_flat54_seed55_stage1/model_349.pt'
$expectedHash = '765FE2A4CD1438CA3E81C387BE570473C5DD3F9DB656C4F064EC7A903DD802ED'
$outDir = Join-Path $root 'logs/stair_command_profiles_20260923'
$benchmarkDir = Join-Path $root 'logs/stair_benchmark'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

if (-not (Test-Path -LiteralPath $checkpoint -PathType Leaf)) { throw "Missing checkpoint: $checkpoint" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $checkpoint).Hash -ne $expectedHash) {
    throw 'Parent checkpoint hash mismatch'
}

$profiles = @(
    [pscustomobject]@{ Label = 'rough55_cmd_gentle16_v3open128'; Distance = '1.6'; Minimum = '0.35' },
    [pscustomobject]@{ Label = 'rough55_cmd_gentle20_v3open128'; Distance = '2.0'; Minimum = '0.40' }
)
$jobs = @()

foreach ($profile in $profiles) {
    if (Get-ChildItem -LiteralPath $benchmarkDir -Filter "$($profile.Label)_cycle_*.json" -ErrorAction SilentlyContinue) {
        throw "Suite output already exists for $($profile.Label)"
    }
    $stdout = Join-Path $outDir "$($profile.Label).stdout.log"
    $stderr = Join-Path $outDir "$($profile.Label).stderr.log"
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        $suite, '--checkpoint', ('"' + $checkpoint + '"'), '--label', $profile.Label,
        '--config', 'configs/stair_eval_v3.json', '--split', 'development',
        '--num-envs', '128', '--horizon', '900', '--brake-profile',
        '--brake-distance', $profile.Distance, '--brake-min-speed', $profile.Minimum
    )
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{ Profile = $profile; Process = $process; Stdout = $stdout; Stderr = $stderr }
    Write-Output "START $($profile.Label) PID=$($process.Id) actor=57 actions=16"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    $exitCode = $job.Process.ExitCode
    $exitOk = $null -eq $exitCode -or $exitCode -eq 0
    $files = @(Get-ChildItem -LiteralPath $benchmarkDir -Filter "$($job.Profile.Label)_cycle_*.json")
    if (-not $exitOk -or $files.Count -ne 6) {
        throw "Suite failed: $($job.Profile.Label); exit=$exitCode rows=$($files.Count)"
    }
    $rows = @($files | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json })
    $total = [pscustomobject]@{
        passage = ($rows | Measure-Object passage_success -Sum).Sum
        cycle = ($rows | Measure-Object success -Sum).Sum
        unsafe = ($rows | Measure-Object unsafe -Sum).Sum
        stop_failed = ($rows | Measure-Object stop_failed -Sum).Sum
        incomplete = ($rows | Measure-Object incomplete -Sum).Sum
    }
    Write-Output "DONE $($job.Profile.Label) passage=$($total.passage)/768 cycle=$($total.cycle)/768 unsafe=$($total.unsafe) stop_failed=$($total.stop_failed) incomplete=$($total.incomplete)"
}
