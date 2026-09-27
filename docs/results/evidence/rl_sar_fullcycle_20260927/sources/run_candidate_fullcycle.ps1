param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][string]$PolicyMap
)
$ErrorActionPreference = 'Stop'
$rootPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputPath = (Resolve-Path -LiteralPath $OutputDirectory).Path
$mapPath = (Resolve-Path -LiteralPath $PolicyMap).Path
$selection = Get-Content -LiteralPath $mapPath -Raw | ConvertFrom-Json
$ids = @($selection.PSObject.Properties.Name)
if ($ids.Count -ne 2 -or $ids -contains '10000') { throw 'Exactly two allowed policies required' }
$jobs = @($ids | ForEach-Object { 'flat_' + $_ }) + @(
    'rough_04','boxes_10','slope_up_10','slope_down_10',
    'stairs_up_06','stairs_down_06','stairs_up_12','stairs_down_12','stairs_up_18','stairs_down_18')
$done = @()
function Write-ProgressRecord($record) {
    $temporary = Join-Path $outputPath 'evaluation_progress.json.tmp'
    $record | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -LiteralPath $temporary
    Move-Item -LiteralPath $temporary -Destination (Join-Path $outputPath 'evaluation_progress.json') -Force
}
foreach ($job in $jobs) {
    $result = Join-Path $outputPath ($job + '.json')
    # Never silently skip a stale or incomplete result from another invocation.
    if (Test-Path -LiteralPath $result) { throw "Output already exists: $result" }
    Write-ProgressRecord @{status='running';current=$job;completed=$done;total_jobs=$jobs.Count;policies=$ids;updated=(Get-Date -Format o)}
    $argsList = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'run_local.ps1'))
    if ($job.StartsWith('flat_')) {
        $policyId = $job.Substring(5)
        $exportDir = Join-Path $rootPath $selection.$policyId
        $argsList += @('scripts/eval_candidate_operating57_isaac.py','--terrain','flat',
            '--policy',(Join-Path $exportDir 'policy.pt'),'--policy-id',$policyId,
            '--export-manifest',(Join-Path $exportDir 'manifest.json'),'--output',$result)
    } else {
        $argsList += @('scripts/eval_fullcycle_terrain.py','--terrain',$job,'--policy-map',$mapPath,'--output',$result)
    }
    $quotedArgs = $argsList | ForEach-Object { '"' + $_ + '"' }
    $worker = Start-Process powershell.exe -ArgumentList $quotedArgs -WorkingDirectory $rootPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $outputPath ($job + '_stdout.log')) -RedirectStandardError (Join-Path $outputPath ($job + '_stderr.log')) -PassThru -Wait
    if ($worker.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $result)) {
        Write-ProgressRecord @{status='failed';current=$job;completed=$done;total_jobs=$jobs.Count;exit_code=$worker.ExitCode;updated=(Get-Date -Format o)}
        throw "Evaluation failed: $job"
    }
    $saved = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    $expectedCount = if ($job.StartsWith('flat_')) { 1152 } elseif ($job.StartsWith('stairs_')) { 576 } else { 2304 }
    if ($saved.smoke -or $saved.records.Count -ne $expectedCount) { throw "Incomplete result: $job" }
    $done += $job
}
Write-ProgressRecord @{status='completed';completed=$done;total_jobs=$jobs.Count;policies=$ids;updated=(Get-Date -Format o)}
