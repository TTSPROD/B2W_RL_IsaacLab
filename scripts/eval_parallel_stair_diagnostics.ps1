param([ValidateSet('candidates', 'stop_speed', 'parent_late')][string]$Mode = 'candidates')

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$suiteHash = (Get-FileHash (Join-Path $root 'configs/stair_eval_v3.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$outDir = Join-Path $root 'logs/stair_benchmark'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$groups = @()
if ($Mode -eq 'candidates' -or $Mode -eq 'stop_speed') {
    $variants = if ($Mode -eq 'stop_speed') { @('stop_speed') } else { @('control', 'passage_bonus', 'late_brake') }
    foreach ($variant in $variants) {
        $members = @()
        foreach ($seed in @(54, 55)) {
            $label = "v3_2048_${variant}_seed${seed}_full"
            $dir = Get-ChildItem (Join-Path $root 'logs/rsl_rl/unitree_b2w_stair') -Directory |
                Where-Object Name -Like "*_$label" | Select-Object -First 1
            if (-not $dir) { throw "Missing $label" }
            $members += [pscustomobject]@{
                label = $label
                checkpoint = Join-Path $dir.FullName 'model_398.pt'
                brake = if ($variant -eq 'late_brake') { '0.8' } else { '1.2' }
            }
        }
        $groups += ,$members
    }
} else {
    $groups += ,@([pscustomobject]@{
        label = 'v3_parent_late_brake'
        checkpoint = Join-Path $root 'logs/rsl_rl/unitree_b2w_rough/2026-09-21_11-29-39_rough_from_flat54_stage1/model_349.pt'
        brake = '0.8'
    })
}

foreach ($members in $groups) {
    foreach ($direction in @('up', 'down')) {
        $jobs = @()
        foreach ($member in $members) {
            $stem = "$($member.label)_cycle_${direction}_h14_r32_seed3001"
            $output = Join-Path $outDir "$stem.json"
            $stdout = Join-Path $outDir "$stem.stdout.log"
            $stderr = Join-Path $outDir "$stem.stderr.log"
            if ((Test-Path $output) -or (Test-Path $stdout) -or (Test-Path $stderr)) {
                throw "Output already exists: $stem"
            }
            $cli = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
                'scripts/eval_stair_b2w.py', '--checkpoint', ('"' + $member.checkpoint + '"'),
                '--direction', $direction, '--rise', '0.14', '--run', '0.32', '--num-steps', '6',
                '--speed', '0.7', '--seed', '3001', '--num-envs', '64', '--horizon', '800',
                '--cycle', '--cycle-protocol-v3', '--hold-steps', '100', '--stop-speed', '0.15',
                '--max-stop-drift', '0.35', '--restart-distance', '0.35', '--suite-sha256', $suiteHash,
                '--brake-profile', '--brake-distance', $member.brake, '--brake-min-speed', '0.25',
                '--output', ('"' + $output + '"'))
            $process = Start-Process powershell.exe -ArgumentList $cli -WorkingDirectory $root `
                -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
            $jobs += [pscustomobject]@{ stem = $stem; process = $process; output = $output }
            Write-Output "START $stem PID=$($process.Id)"
        }
        foreach ($job in $jobs) {
            $job.process.WaitForExit()
            $job.process.Refresh()
            if ($job.process.ExitCode -ne 0 -or -not (Test-Path $job.output)) {
                throw "Evaluation failed: $($job.stem)"
            }
            $result = Get-Content $job.output -Raw | ConvertFrom-Json
            if ($result.schema -ne 'b2w_stair_eval_v3' -or $result.suite_sha256 -ne $suiteHash -or
                $result.success + $result.unsafe + $result.stop_failed + $result.timeouts + $result.incomplete -ne 64) {
                throw "Invalid evaluation output: $($job.stem)"
            }
            Write-Output "DONE $($job.stem) passage=$($result.passage_success) cycle=$($result.success) unsafe=$($result.unsafe) stop_failed=$($result.stop_failed) incomplete=$($result.incomplete)"
        }
    }
}
