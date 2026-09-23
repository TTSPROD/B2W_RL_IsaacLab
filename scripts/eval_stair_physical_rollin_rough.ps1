param([Parameter(Mandatory)][int]$MeshSeed)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher=Join-Path $PSScriptRoot 'run_local.ps1';$runRoot=Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$outDir=Join-Path $root 'logs/stair_physical_rollin_20260923';New-Item -ItemType Directory -Force $outDir|Out-Null
$jobs=@()
foreach($seed in @(54,55)){
    $label="stair_physical_rollin_2048_20260923_seed${seed}_full"
    $runs=@(Get-ChildItem $runRoot -Directory|Where-Object{$_.Name.EndsWith("_$label")});if($runs.Count-ne1){throw "Run lookup failed: $label"}
    $checkpoint=Join-Path $runs[0].FullName 'model_422.pt';$m=Get-Content (Join-Path $runs[0].FullName 'stair_parent.json') -Raw|ConvertFrom-Json
    if($m.actor_observation_dim-ne57-or$m.actor_base_lin_vel-or$m.rollin_start_offset_m-ne1.0){throw "Invalid roll-in manifest"}
    $stdout=Join-Path $outDir "${label}_rough${MeshSeed}.stdout.log";$stderr=Join-Path $outDir "${label}_rough${MeshSeed}.stderr.log"
    if((Test-Path $stdout)-or(Test-Path $stderr)){throw "Output exists"}
    $cli=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$launcher+'"'),'scripts/smoke_b2w.py','--checkpoint',('"'+$checkpoint+'"'),'--terrain','rough','--seed',"$MeshSeed",'--num-envs','512','--steps','1000','--reset-tilt-limit','0.3','--terrain-level','9')
    $p=Start-Process powershell.exe -ArgumentList $cli -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{Label=$label;Process=$p;Stdout=$stdout};Write-Output "START $label mesh=$MeshSeed PID=$($p.Id) actor=57"
}
foreach($j in $jobs){$j.Process.WaitForExit();$j.Process.Refresh();$ec=$j.Process.ExitCode;$ok=$null-eq$ec-or$ec-eq0;$ev=Select-String $j.Stdout -Pattern '^POLICY_EVAL'|Select-Object -Last 1;$fam=Select-String $j.Stdout -Pattern '^TERRAIN_FAMILIES'|Select-Object -Last 1;Write-Output "DONE $($j.Label) mesh=$MeshSeed exit=$ec";if($ev){$ev.Line};if($fam){$fam.Line};if(-not$ok-or-not$ev-or-not$fam){throw "Evaluation failed"}}
