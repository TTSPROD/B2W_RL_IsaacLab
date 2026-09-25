param(
    [string]$RunSuffix = 'cycle57_v1_A_full_seed54_20260924_094742',
    [int[]]$CheckpointUpdates = @(3000, 3050, 3200, 3400, 3600, 3800, 3998),
    [int]$NumEnvs = 32,
    [int]$Horizon = 900,
    [int]$Seed = 3001,
    [string]$Label = 'cycle57_A_coarse_safety_20260924'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$runRoot = Join-Path $root 'logs/rsl_rl/unitree_b2w_stair'
$runs = @(Get-ChildItem -LiteralPath $runRoot -Directory | Where-Object { $_.Name.EndsWith("_$RunSuffix") })
if ($runs.Count -ne 1) { throw "Expected exactly one run ending in _$RunSuffix; found $($runs.Count)" }
if ($NumEnvs -lt 1 -or $Horizon -lt 1) { throw 'NumEnvs and Horizon must be positive' }

$outputDirectory = Join-Path $root "logs/checkpoint_screen/$Label"
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$records = @()

foreach ($update in $CheckpointUpdates) {
    $checkpoint = Join-Path $runs[0].FullName "model_$update.pt"
    if (-not (Test-Path -LiteralPath $checkpoint -PathType Leaf)) { throw "Missing checkpoint: $checkpoint" }
    $directionResults = @{}
    foreach ($direction in @('up', 'down')) {
        $stem = "model_${update}_${direction}_seed${Seed}_n${NumEnvs}"
        $output = Join-Path $outputDirectory "$stem.json"
        $log = Join-Path $outputDirectory "$stem.log"
        if ((Test-Path -LiteralPath $output) -or (Test-Path -LiteralPath $log)) {
            throw "Refusing to overwrite screen evidence: $stem"
        }
        Write-Output "RUN checkpoint=$update direction=$direction"
        & $launcher scripts/eval_stair_b2w.py --checkpoint $checkpoint `
            --direction $direction --rise 0.14 --run 0.32 --num-steps 6 --speed 0.7 `
            --num-envs $NumEnvs --horizon $Horizon --seed $Seed --cycle --cycle-protocol-v3 `
            --brake-profile --brake-distance 1.2 --brake-min-speed 0.25 --output $output *> $log
        if ($LASTEXITCODE -ne 0) { throw "Evaluation failed: $stem (see $log)" }
        $metrics = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
        $exclusive = $metrics.success + $metrics.unsafe + $metrics.stop_failed + $metrics.timeouts + $metrics.incomplete
        if ($metrics.policy_actor_observation_dim -ne 57 -or $exclusive -ne $NumEnvs) {
            throw "Invalid evaluator result: $stem"
        }
        $directionResults[$direction] = $metrics
        Write-Output ("DONE checkpoint={0} direction={1} cycle={2}/{3} unsafe={4} wheel_sat={5:P3}" -f `
            $update, $direction, $metrics.success, $NumEnvs, $metrics.unsafe, `
            $metrics.safety_telemetry.overall.wheels.torque_utilization.at_or_above_95pct_fraction)
    }
    $up = $directionResults['up']
    $down = $directionResults['down']
    $records += [pscustomobject]@{
        checkpoint_update = $update
        checkpoint = $checkpoint
        policy_sha256 = $up.policy_sha256
        up_cycle = $up.success
        down_cycle = $down.success
        worst_direction_cycle = [Math]::Min($up.success, $down.success)
        total_cycle = $up.success + $down.success
        total_unsafe = $up.unsafe + $down.unsafe
        total_stop_failed = $up.stop_failed + $down.stop_failed
        total_timeouts = $up.timeouts + $down.timeouts
        total_incomplete = $up.incomplete + $down.incomplete
        wheel_saturation_fraction_worst = [Math]::Max(
            $up.safety_telemetry.overall.wheels.torque_utilization.at_or_above_95pct_fraction,
            $down.safety_telemetry.overall.wheels.torque_utilization.at_or_above_95pct_fraction)
        leg_saturation_fraction_worst = [Math]::Max(
            $up.safety_telemetry.overall.legs.torque_utilization.at_or_above_95pct_fraction,
            $down.safety_telemetry.overall.legs.torque_utilization.at_or_above_95pct_fraction)
        wheel_clipping_fraction_worst = [Math]::Max(
            $up.safety_telemetry.overall.wheels.torque_utilization.computed_to_applied_clipping_fraction,
            $down.safety_telemetry.overall.wheels.torque_utilization.computed_to_applied_clipping_fraction)
        wheel_rolling_residual_rms_worst_m_s = [Math]::Max(
            $up.safety_telemetry.overall.wheel_rolling_residual_m_s.rms,
            $down.safety_telemetry.overall.wheel_rolling_residual_m_s.rms)
        action_delta_rms_worst = [Math]::Max(
            $up.safety_telemetry.overall.action_delta.rms_per_action_element,
            $down.safety_telemetry.overall.action_delta.rms_per_action_element)
        leg_joint_margin_min = [Math]::Min(
            $up.safety_telemetry.overall.leg_soft_joint_limit_margin_fraction.absolute_min,
            $down.safety_telemetry.overall.leg_soft_joint_limit_margin_fraction.absolute_min)
        leg_power_peak_worst_w = [Math]::Max(
            $up.safety_telemetry.overall.legs.absolute_mechanical_power_w.episode_peak_p95,
            $down.safety_telemetry.overall.legs.absolute_mechanical_power_w.episode_peak_p95)
        wheel_power_peak_worst_w = [Math]::Max(
            $up.safety_telemetry.overall.wheels.absolute_mechanical_power_w.episode_peak_p95,
            $down.safety_telemetry.overall.wheels.absolute_mechanical_power_w.episode_peak_p95)
    }
}

$ranked = @($records | Sort-Object `
    @{Expression='worst_direction_cycle'; Descending=$true}, `
    @{Expression='total_unsafe'; Ascending=$true}, `
    @{Expression='total_stop_failed'; Ascending=$true}, `
    @{Expression='total_timeouts'; Ascending=$true}, `
    @{Expression='total_incomplete'; Ascending=$true}, `
    @{Expression='wheel_saturation_fraction_worst'; Ascending=$true}, `
    @{Expression='leg_saturation_fraction_worst'; Ascending=$true}, `
    @{Expression='wheel_rolling_residual_rms_worst_m_s'; Ascending=$true}, `
    @{Expression='action_delta_rms_worst'; Ascending=$true}, `
    @{Expression='total_cycle'; Descending=$true})

$summary = [ordered]@{
    schema = 'b2w_cycle57_checkpoint_screen_v1'
    selection_status = 'development_coarse_screen_only'
    payload = 'none'
    run = $runs[0].FullName
    seed = $Seed
    num_envs_per_direction = $NumEnvs
    horizon_policy_steps = $Horizon
    geometry = @{ rise_m = 0.14; run_m = 0.32; num_steps = 6; speed_m_s = 0.7 }
    ranking = 'lexicographic: worst-direction cycle desc; unsafe/stop-failed/timeout/incomplete asc; actuator safety asc; total cycle desc'
    candidates = $ranked
}
$summaryPath = Join-Path $outputDirectory 'summary.json'
$csvPath = Join-Path $outputDirectory 'summary.csv'
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
$ranked | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding utf8
Write-Output "SUMMARY=$summaryPath"
$ranked | Format-Table checkpoint_update, up_cycle, down_cycle, worst_direction_cycle, total_unsafe, `
    wheel_saturation_fraction_worst, leg_saturation_fraction_worst, wheel_rolling_residual_rms_worst_m_s -AutoSize
