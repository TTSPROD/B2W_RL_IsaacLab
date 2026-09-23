param([Parameter(Mandatory)][int]$MeshSeed)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$outDir = Join-Path $root 'logs/stair_landing20_20260923'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$jobs = @()

foreach ($seed in @(54, 55)) {
    $label = "stair_landing20_short_2048_20260923_seed${seed}_full"
    $runs = @(Get-ChildItem -LiteralPath $runRoot -Directory | Where-Object { $_.Name.EndsWith("_$label") })
    if ($runs.Count -ne 1) { throw "Expected one run for $label, found $($runs.Count)" }
    $checkpoint = Join-Path $runs[0].FullName 'model_422.pt'
    $manifest = Get-Content -LiteralPath (Join-Path $runs[0].FullName 'stair_parent.json') -Raw | ConvertFrom-Json
    if ($manifest.actor_observation_dim -ne 57 -or $manifest.actor_base_lin_vel -or
        $manifest.landing_tiles_fraction -ne 0.2) { throw "Invalid landing20 manifest: $checkpoint" }
    $stdout = Join-Path $outDir "${label}_rough${MeshSeed}.stdout.log"
    $stderr = Join-Path $outDir "${label}_rough${MeshSeed}.stderr.log"
    if ((Test-Path $stdout) -or (Test-Path $stderr)) { throw "Output exists: $label mesh $MeshSeed" }
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        'scripts/smoke_b2w.py', '--checkpoint', ('"' + $checkpoint + '"'),
        '--terrain', 'rough', '--seed', "$MeshSeed", '--num-envs', '512', '--steps', '1000',
        '--reset-tilt-limit', '0.3', '--terrain-level', '9'
    )
    $process = Start-Process powershell.exe -ArgumentList $cli -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{Label=$label; Process=$process; Stdout=$stdout}
    Write-Output "START $label mesh=$MeshSeed PID=$($process.Id) actor=57"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit(); $job.Process.Refresh()
    $exitCode=$job.Process.ExitCode; $exitOk=$null -eq $exitCode -or $exitCode -eq 0
    $eval=Select-String -LiteralPath $job.Stdout -Pattern '^POLICY_EVAL'|Select-Object -Last 1
    $families=Select-String -LiteralPath $job.Stdout -Pattern '^TERRAIN_FAMILIES'|Select-Object -Last 1
    Write-Output "DONE $($job.Label) mesh=$MeshSeed exit=$exitCode manifest_actor57=true"
    if($eval){Write-Output $eval.Line}; if($families){Write-Output $families.Line}
    if(-not $exitOk -or -not $eval -or -not $families){throw "Evaluation failed: $($job.Label)"}
}
