param(
    [string]$Base = 'logs/core_stage3_selection_20260929',
    [int]$Parallel = 3
)
$ErrorActionPreference = 'Stop'
if ($Parallel -lt 1 -or $Parallel -gt 3) { throw 'Parallel must be in [1,3]' }
$rootPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$basePath = (Resolve-Path (Join-Path $rootPath $Base)).Path
& (Join-Path $PSScriptRoot 'run_local.ps1') dashboard/launch.py --view selection
if ($LASTEXITCODE -ne 0) { throw 'Evaluation dashboard failed to start' }
$plan = Get-Content -LiteralPath (Join-Path $basePath 'declared_plan.json') -Raw | ConvertFrom-Json
if ($plan.schema -ne 'b2w_core_stage3_selection_v1') { throw 'Unexpected selection plan' }
$jobs = @($plan.variants.psobject.Properties.Name)
$completed = [System.Collections.Generic.List[string]]::new()

function Write-ProgressFile([string]$status, [string[]]$active, [object[]]$failures) {
    $payload = [ordered]@{
        status = $status
        total_jobs = $jobs.Count
        completed = @($completed)
        active = @($active)
        failures = @($failures)
        policies = @($plan.policies)
        updated = (Get-Date -Format o)
    }
    $temporary = Join-Path $basePath 'evaluation_progress.json.tmp'
    $payload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination (Join-Path $basePath 'evaluation_progress.json') -Force
}

$pending = [System.Collections.Generic.Queue[string]]::new()
foreach ($job in $jobs) {
    $result = Join-Path $basePath ($job + '.json')
    $trace = Join-Path $basePath ($job + '.npz')
    if ((Test-Path -LiteralPath $result) -and (Test-Path -LiteralPath $trace)) {
        $completed.Add($job)
    } elseif ((Test-Path -LiteralPath $result) -or (Test-Path -LiteralPath $trace)) {
        throw "Incomplete existing result: $job"
    } else {
        $pending.Enqueue($job)
    }
}
Write-ProgressFile 'running' @() @()

while ($pending.Count -gt 0) {
    $batch = @()
    while ($pending.Count -gt 0 -and $batch.Count -lt $Parallel) {
        $job = $pending.Dequeue()
        $result = Join-Path $basePath ($job + '.json')
        $arguments = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'run_local.ps1'),
            'scripts/eval_fullcycle_terrain.py', '--terrain', $job, '--output', $result,
            '--seeds', '5', '--policy-map', (Join-Path $basePath 'policy_map.json'),
            '--protocol-module', 'core_stage3_selection_protocol'
        )
        $process = Start-Process powershell.exe -ArgumentList ($arguments | ForEach-Object { '"' + $_ + '"' }) `
            -WorkingDirectory $rootPath -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $basePath ($job + '_stdout.log')) `
            -RedirectStandardError (Join-Path $basePath ($job + '_stderr.log')) -PassThru
        $batch += [pscustomobject]@{ Name = $job; Process = $process; Result = $result }
    }
    Write-ProgressFile 'running' @($batch.Name) @()
    $batch.Process | Wait-Process
    $failures = @()
    foreach ($entry in $batch) {
        $entry.Process.Refresh()
        if ($entry.Process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $entry.Result)) {
            $failures += [pscustomobject]@{ terrain = $entry.Name; exit_code = $entry.Process.ExitCode }
        } else {
            $completed.Add($entry.Name)
        }
    }
    if ($failures.Count) {
        Write-ProgressFile 'failed' @() $failures
        throw "Stage-3 selection failed: $($failures.terrain -join ', ')"
    }
}

& (Join-Path $PSScriptRoot 'run_local.ps1') scripts/summarize_core_stage3_selection.py `
    --base $basePath --output (Join-Path $basePath 'analysis')
if ($LASTEXITCODE -ne 0) {
    Write-ProgressFile 'failed' @('postprocessing') @([pscustomobject]@{ terrain = 'postprocessing'; exit_code = $LASTEXITCODE })
    throw 'Stage-3 selection postprocessing failed'
}
Write-ProgressFile 'completed' @() @()
