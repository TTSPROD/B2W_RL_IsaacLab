param(
    [Parameter(Mandatory=$true)][int]$BlockerPid,
    [Parameter(Mandatory=$true)][string]$ConsoleDirectory
)
$ErrorActionPreference = 'Stop'
$rootPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$consolePath = (Resolve-Path -LiteralPath $ConsoleDirectory).Path
if (-not $consolePath.StartsWith($rootPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Console directory must be inside this project'
}
$state = @{status='waiting_for_gpu'; blocker_pid=$BlockerPid; target_updates=500; parent=23999; final=24499}
function Save-State {
    $state.updated_local = Get-Date -Format o
    $temporary = Join-Path $consolePath 'queue_status.json.tmp'
    $state | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath $temporary
    Move-Item -LiteralPath $temporary -Destination (Join-Path $consolePath 'queue_status.json') -Force
}
try {
    Save-State
    $blocker = Get-Process -Id $BlockerPid -ErrorAction SilentlyContinue
    if ($blocker) {
        # Wait for the whole known batch, including gaps between its workers.
        while (-not $blocker.WaitForExit(10000)) { Save-State }
    }
    do {
        $busy = @(Get-CimInstance Win32_Process | Where-Object {
            $_.Name -match '^python' -and $_.CommandLine -match 'train_b2w|eval_candidate_operating57|eval_fullcycle_terrain'
        })
        if ($busy.Count) { Save-State; Start-Sleep -Seconds 10 }
    } while ($busy.Count)
    $state.status = 'starting'; Save-State
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'run_local.ps1'),
        'scripts/train_b2w_23999.py','--headless','--num_envs','4096','--max_iterations','500','--run_name','regression_rehearsal')
    $quoted = $arguments | ForEach-Object { '"' + $_ + '"' }
    $worker = Start-Process powershell.exe -ArgumentList $quoted -WorkingDirectory $rootPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $consolePath 'stdout.log') -RedirectStandardError (Join-Path $consolePath 'stderr.log') -PassThru
    # Retain the handle before exit; otherwise Windows PowerShell can lose ExitCode.
    $null = $worker.Handle
    $state.status = 'launched'; $state.training_launcher_pid = $worker.Id; Save-State
    $worker.WaitForExit()
    $worker.Refresh()
    $state.exit_code = $worker.ExitCode
    $state.status = if ($null -eq $worker.ExitCode) { 'process_exited_unknown' } elseif ($worker.ExitCode -eq 0) { 'process_completed' } else { 'failed' }
    Save-State
} catch {
    $state.status = 'failed'; $state.error = $_.Exception.Message; Save-State
    throw
}
