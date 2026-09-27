param([ValidateSet('Flat','Terrain')][string]$Phase = 'Flat')
$ErrorActionPreference = 'Stop'
$rootPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputPath = Join-Path $rootPath 'logs/fullcycle21999_validation_20260927'
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$jobs = if ($Phase -eq 'Flat') { @('flat_19999','flat_21999') } else {
    @('rough_04','boxes_10','slope_up_10','slope_down_10','stairs_up_06','stairs_down_06','stairs_up_12','stairs_down_12','stairs_up_18','stairs_down_18')
}
$done = @()
foreach ($job in $jobs) {
    $result = Join-Path $outputPath ($job + '.json')
    if (Test-Path -LiteralPath $result) {
        $saved = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
        $expectedCount = if ($Phase -eq 'Flat') { 1152 } elseif ($job.StartsWith('stairs_')) { 576 } else { 2304 }
        $tracePath = [IO.Path]::ChangeExtension($result, '.npz')
        if ($saved.smoke -or $saved.records.Count -ne $expectedCount -or -not (Test-Path -LiteralPath $tracePath)) { throw "Existing incomplete result: $result" }
        $hashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
        $stream = [IO.File]::OpenRead($tracePath)
        try { $traceHash = [BitConverter]::ToString($hashAlgorithm.ComputeHash($stream)).Replace('-','').ToLower() } finally { $stream.Dispose(); $hashAlgorithm.Dispose() }
        if ($traceHash -ne $saved.trace_sha256) { throw "Trace SHA mismatch: $result" }
        $done += $job
        continue
    }
    @{status='running'; phase=$Phase; current=$job; completed=$done; started=(Get-Date -Format o)} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $outputPath ($Phase.ToLower() + '_progress.json'))
    $argsList = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'run_local.ps1'))
    if ($Phase -eq 'Flat') {
        $policyId = [int]$job.Substring(5)
        $exportDir = if ($policyId -eq 19999) { 'policies/server/upstream_19999/export' } else { 'logs/fullcycle21999_validation_20260927/contract/policy-contract-export' }
        $argsList += @('scripts/eval_candidate_operating57_isaac.py','--terrain','flat','--policy',($exportDir + '/policy.pt'),'--policy-id',$policyId,'--export-manifest',($exportDir + '/manifest.json'),'--output',$result)
    } else {
        $argsList += @('scripts/eval_fullcycle_terrain.py','--terrain',$job,'--output',$result)
    }
    $quotedArgs = $argsList | ForEach-Object { '"' + $_ + '"' }
    $worker = Start-Process powershell.exe -ArgumentList $quotedArgs -WorkingDirectory $rootPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $outputPath ($job + '_stdout.log')) -RedirectStandardError (Join-Path $outputPath ($job + '_stderr.log')) -PassThru -Wait
    if ($worker.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $result)) {
        @{status='failed'; phase=$Phase; current=$job; completed=$done; exit_code=$worker.ExitCode; updated=(Get-Date -Format o)} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $outputPath ($Phase.ToLower() + '_progress.json'))
        throw "Evaluation failed: $job"
    }
    $done += $job
}
@{status='completed'; phase=$Phase; completed=$done; updated=(Get-Date -Format o)} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $outputPath ($Phase.ToLower() + '_progress.json'))
