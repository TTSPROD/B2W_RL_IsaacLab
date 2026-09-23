param(
    [Parameter(Mandatory)][ValidateSet('control57', 'basevel60')][string]$Variant,
    [int]$EvalSeed = 1004
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$outDir = Join-Path $root 'logs/stair_basevel_20260923'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$jobs = @()

foreach ($seed in @(54, 55)) {
    $label = "stair_basevel_${Variant}_2048_20260923_seed${seed}_full"
    $runs = @(Get-ChildItem -LiteralPath $runRoot -Directory | Where-Object { $_.Name.EndsWith("_$label") })
    if ($runs.Count -ne 1) { throw "Expected one run for $label, found $($runs.Count)" }
    $checkpoint = Join-Path $runs[0].FullName 'model_398.pt'
    $stdout = Join-Path $outDir "${label}_flat${EvalSeed}.stdout.log"
    $stderr = Join-Path $outDir "${label}_flat${EvalSeed}.stderr.log"
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
        throw "Output already exists for $label flat $EvalSeed"
    }
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        'scripts/smoke_b2w.py', '--checkpoint', ('"' + $checkpoint + '"'),
        '--terrain', 'flat', '--seed', "$EvalSeed", '--num-envs', '128', '--steps', '1000'
    )
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{ Label = $label; Process = $process; Stdout = $stdout }
    Write-Output "START $label flat=$EvalSeed PID=$($process.Id)"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    $eval = Select-String -LiteralPath $job.Stdout -Pattern '^POLICY_EVAL' | Select-Object -Last 1
    Write-Output "DONE $($job.Label) flat=$EvalSeed exit=$($job.Process.ExitCode)"
    if ($eval) { Write-Output $eval.Line }
    if ($job.Process.ExitCode -ne 0 -or -not $eval) { throw "Flat evaluation failed: $($job.Label)" }
}
