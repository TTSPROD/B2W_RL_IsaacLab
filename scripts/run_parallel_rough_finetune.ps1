param(
    [Parameter(Mandatory)][string]$ParentCheckpoint,
    [Parameter(Mandatory)][string]$ExpectedSha256,
    [ValidateSet('smoke', 'full')][string]$Mode = 'smoke',
    [ValidateSet('control', 'inverse25')][string]$Variant = 'inverse25'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$parent = (Resolve-Path -LiteralPath $ParentCheckpoint).Path
if ((Get-FileHash -LiteralPath $parent -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedSha256.ToLowerInvariant()) {
    throw 'Parent checkpoint hash mismatch'
}
$run = Split-Path -Leaf (Split-Path -Parent $parent)
$checkpoint = Split-Path -Leaf $parent
$labelRoot = "rough_${Variant}_2048_20260922"
$iterations = if ($Mode -eq 'smoke') { '1' } else { '50' }
$numEnvs = if ($Mode -eq 'smoke') { '128' } else { '2048' }
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$logDir = Join-Path $root 'logs/rough_finetune_20260922'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$jobs = @()

foreach ($seed in @(54, 55)) {
    $label = "${labelRoot}_seed${seed}_${Mode}"
    $stdout = Join-Path $logDir "$label.stdout.log"
    $stderr = Join-Path $logDir "$label.stderr.log"
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
        throw "Output already exists for $label"
    }
    $cli = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"'),
        'scripts/train_b2w.py', '--task', 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0',
        '--headless', '--resume', '--load_run', $run, '--checkpoint', $checkpoint,
        '--conservative-ppo', '--freeze-action-std', '--reset-tilt-limit', '0.1',
        '--num_envs', $numEnvs, '--max_iterations', $iterations,
        '--seed', "$seed", '--run_name', $label
    )
    if ($Variant -eq 'inverse25') { $cli += @('--inverse-terrain-proportion', '0.25') }
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $cli -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $jobs += [pscustomobject]@{ Label = $label; Process = $process; Stdout = $stdout; Stderr = $stderr }
    Write-Output "START $label PID=$($process.Id)"
}

foreach ($job in $jobs) {
    $job.Process.WaitForExit()
    $job.Process.Refresh()
    $fixedStd = Select-String -LiteralPath $job.Stdout -Pattern 'B2W_ACTION_STD_FROZEN=0.1' -Quiet
    $loaded = Select-String -LiteralPath $job.Stdout -Pattern 'Loading model checkpoint from:' -Quiet
    $trained = Select-String -LiteralPath $job.Stdout -Pattern 'Training time:' -Quiet
    Write-Output "DONE $($job.Label) exit=$($job.Process.ExitCode) loaded=$loaded fixed_std=$fixedStd trained=$trained"
    if ($job.Process.ExitCode -ne 0 -or -not $fixedStd -or -not $loaded -or -not $trained) {
        throw "Run failed: $($job.Label); see $($job.Stdout) and $($job.Stderr)"
    }
}
