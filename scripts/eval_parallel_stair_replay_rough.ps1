param(
    [Parameter(Mandatory)][ValidateSet('control', 'diverse_replay')][string]$Variant,
    [Parameter(Mandatory)][int]$MeshSeed
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$outDir = Join-Path $root 'logs/stair_replay_20260923'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$jobs = @()

foreach ($seed in @(54, 55)) {
    $label = "stair_replay_${Variant}_2048_20260923_seed${seed}_full"
    $runs = @(Get-ChildItem -LiteralPath $runRoot -Directory | Where-Object { $_.Name.EndsWith("_$label") })
    if ($runs.Count -ne 1) { throw "Expected one run for $label, found $($runs.Count)" }
    $checkpoint = Join-Path $runs[0].FullName 'model_398.pt'
    if (-not (Test-Path -LiteralPath $checkpoint)) { throw "Missing checkpoint: $checkpoint" }
    $stdout = Join-Path $outDir "${label}_rough${MeshSeed}.stdout.log"
    $stderr = Join-Path $outDir "${label}_rough${MeshSeed}.stderr.log"
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
        throw "Output already exists for $label mesh $MeshSeed"
    }
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        'scripts/smoke_b2w.py', '--checkpoint', ('"' + $checkpoint + '"'),
        '--terrain', 'rough', '--seed', "$MeshSeed", '--num-envs', '512', '--steps', '1000',
        '--reset-tilt-limit', '0.3', '--terrain-level', '9'
    )
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{ Label = $label; Process = $process; Stdout = $stdout }
    Write-Output "START $label mesh=$MeshSeed PID=$($process.Id) SHA256=$((Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash.ToLowerInvariant())"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    $eval = Select-String -LiteralPath $job.Stdout -Pattern '^POLICY_EVAL' | Select-Object -Last 1
    $families = Select-String -LiteralPath $job.Stdout -Pattern '^TERRAIN_FAMILIES' | Select-Object -Last 1
    Write-Output "DONE $($job.Label) mesh=$MeshSeed exit=$($job.Process.ExitCode)"
    if ($eval) { Write-Output $eval.Line }
    if ($families) { Write-Output $families.Line }
    if ($job.Process.ExitCode -ne 0 -or -not $eval -or -not $families) {
        throw "Evaluation failed: $($job.Label)"
    }
}
