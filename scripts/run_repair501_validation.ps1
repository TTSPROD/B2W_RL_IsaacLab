param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputPath=(Resolve-Path -LiteralPath $OutputDirectory).Path
& (Join-Path $PSScriptRoot 'run_candidate_fullcycle.ps1') -OutputDirectory $outputPath -PolicyMap (Join-Path $outputPath 'policy_map.json')
if (-not $?) { throw 'Evaluation batch failed; postprocessing not started' }
$arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'run_local.ps1'),'scripts/summarize_repair501_validation.py')
$quoted=$arguments | ForEach-Object { '"'+$_+'"' }
$worker=Start-Process powershell.exe -ArgumentList $quoted -WorkingDirectory $rootPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $outputPath 'summary_stdout.log') -RedirectStandardError (Join-Path $outputPath 'summary_stderr.log') -PassThru -Wait
@{status=$(if($worker.ExitCode -eq 0){'completed'}else{'failed'});exit_code=$worker.ExitCode;updated=(Get-Date -Format o)} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $outputPath 'postprocessing_status.json')
if ($worker.ExitCode -ne 0) { throw 'Trace verification/postprocessing failed; see summary_stderr.log' }
