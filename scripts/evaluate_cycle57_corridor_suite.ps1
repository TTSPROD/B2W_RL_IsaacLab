param(
    [Parameter(Mandatory = $true)]
    [string]$Checkpoint,
    [int]$NumEnvs = 64,
    [int]$Horizon = 900,
    [double]$HoldWheelActionScale = 1.0,
    [int]$HoldWheelRampSteps = 0,
    [double]$HoldWheelFeedbackGain = 0.0,
    [int]$HoldWheelFeedbackRampSteps = 10,
    [string]$StopControllerConfig,
    [string]$StopControllerVariant,
    [string]$SettledLatchConfig,
    [string]$SettledLatchVariant,
    [int]$NominalSeed = 5101,
    [int]$SteepSeed = 5102,
    [int]$ShallowSeed = 5103,
    [switch]$CaptureHoldTraces,
    [string]$Label = 'cycle57_model3000_corridor_seed510x_20260924'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$checkpointPath = (Resolve-Path -LiteralPath $Checkpoint).Path
if ($NumEnvs -lt 1 -or $Horizon -lt 1) { throw 'NumEnvs and Horizon must be positive' }
if ($HoldWheelActionScale -lt 0.0 -or $HoldWheelActionScale -gt 1.0) {
    throw 'HoldWheelActionScale must be in [0, 1]'
}
if ($HoldWheelRampSteps -lt 0 -or ($HoldWheelRampSteps -gt 0 -and $HoldWheelActionScale -eq 1.0)) {
    throw 'HoldWheelRampSteps requires a reduced HoldWheelActionScale'
}
if ($HoldWheelFeedbackGain -lt 0.0 -or $HoldWheelFeedbackRampSteps -lt 0) {
    throw 'Hold wheel feedback settings must be non-negative'
}
if ($HoldWheelFeedbackGain -gt 0.0 -and ($HoldWheelActionScale -ne 1.0 -or $HoldWheelRampSteps -ne 0)) {
    throw 'Hold wheel feedback is mutually exclusive with fixed wheel scaling'
}
if ([string]::IsNullOrWhiteSpace($StopControllerConfig) -ne [string]::IsNullOrWhiteSpace($StopControllerVariant)) {
    throw 'StopControllerConfig and StopControllerVariant are required together'
}
if ([string]::IsNullOrWhiteSpace($SettledLatchConfig) -ne [string]::IsNullOrWhiteSpace($SettledLatchVariant)) {
    throw 'SettledLatchConfig and SettledLatchVariant are required together'
}
if (-not [string]::IsNullOrWhiteSpace($StopControllerConfig) -and
        -not [string]::IsNullOrWhiteSpace($SettledLatchConfig)) {
    throw 'Filtered stop controller and settled latch are mutually exclusive'
}
$stopControllerArgs = @()
$stopControllerDefinition = $null
if (-not [string]::IsNullOrWhiteSpace($StopControllerConfig)) {
    if ($HoldWheelActionScale -ne 1.0 -or $HoldWheelRampSteps -ne 0 -or $HoldWheelFeedbackGain -gt 0.0) {
        throw 'Filtered stop controller is mutually exclusive with legacy wheel adapters'
    }
    $stopControllerPath = (Resolve-Path -LiteralPath $StopControllerConfig).Path
    $stopSweep = Get-Content -LiteralPath $stopControllerPath -Raw | ConvertFrom-Json
    if ($stopSweep.schema -ne 'b2w_stop_controller_sweep_v1') { throw 'Unsupported stop-controller sweep schema' }
    $selected = @($stopSweep.variants | Where-Object { $_.name -eq $StopControllerVariant })
    if ($selected.Count -ne 1 -or $selected[0].mode -ne 'filtered_hysteretic') {
        throw 'Selected variant is not one registered filtered_hysteretic controller'
    }
    $stopControllerArgs = @('--stop-controller-config', $stopControllerPath,
                            '--stop-controller-variant', $StopControllerVariant)
    $stopControllerDefinition = $selected[0]
}
$settledLatchArgs = @()
$settledLatchDefinition = $null
if (-not [string]::IsNullOrWhiteSpace($SettledLatchConfig)) {
    if ($HoldWheelActionScale -ne 1.0 -or $HoldWheelRampSteps -ne 0 -or $HoldWheelFeedbackGain -gt 0.0) {
        throw 'Settled latch is mutually exclusive with legacy wheel adapters'
    }
    $settledLatchPath = (Resolve-Path -LiteralPath $SettledLatchConfig).Path
    $latchExperiment = Get-Content -LiteralPath $settledLatchPath -Raw | ConvertFrom-Json
    if ($latchExperiment.schema -ne 'b2w_settled_latch_experiment_v1') {
        throw 'Unsupported settled-latch experiment schema'
    }
    $selected = @($latchExperiment.variants | Where-Object { $_.name -eq $SettledLatchVariant })
    if ($selected.Count -ne 1 -or $selected[0].mode -ne 'settled_hold_latch') {
        throw 'Selected variant is not one registered settled_hold_latch controller'
    }
    $settledLatchArgs = @('--settled-latch-config', $settledLatchPath,
                          '--settled-latch-variant', $SettledLatchVariant)
    $settledLatchDefinition = $selected[0]
}

# These seeds were not used to select model_3000 or tune the fixed corridor gains.
$scenarios = @(
    [ordered]@{ name = 'nominal'; seed = $NominalSeed; rise = 0.14; run = 0.32 },
    [ordered]@{ name = 'steep'; seed = $SteepSeed; rise = 0.16; run = 0.29 },
    [ordered]@{ name = 'shallow'; seed = $ShallowSeed; rise = 0.12; run = 0.38 }
)
$suiteDefinition = [ordered]@{
    schema = 'b2w_cycle57_corridor_suite_v1'
    selection_status = 'post_selection_controller_qualification'
    payload = 'none'
    policy_abi = '57 observations -> 16 actions'
    controller = [ordered]@{
        formula = 'yaw_cmd=clip(-0.8*lateral_error_m-1.2*heading_error_rad,-0.5,0.5)'
        policy_abi_changed = $false
        hold_wheel_action_scale = $HoldWheelActionScale
        hold_wheel_ramp_steps = $HoldWheelRampSteps
        hold_wheel_feedback_gain = $HoldWheelFeedbackGain
        hold_wheel_feedback_ramp_steps = $HoldWheelFeedbackRampSteps
        filtered_stop_controller = $stopControllerDefinition
        settled_latch = $settledLatchDefinition
    }
    num_envs_per_cell = $NumEnvs
    horizon_policy_steps = $Horizon
    speed_m_s = 0.7
    num_steps = 6
    cycle_protocol = 'v3'
    full_rate_hold_traces = [bool]$CaptureHoldTraces
    brake_profile = @{ distance_m = 1.2; minimum_speed_m_s = 0.25 }
    scenarios = $scenarios
    directions = @('up', 'down')
}
$suiteJson = $suiteDefinition | ConvertTo-Json -Depth 8 -Compress
$suiteBytes = [System.Text.Encoding]::UTF8.GetBytes($suiteJson)
$suiteSha = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($suiteBytes)).ToLowerInvariant()

$outputDirectory = Join-Path $root "logs/corridor_qualification/$Label"
if (Test-Path -LiteralPath $outputDirectory) {
    throw "Refusing to overwrite corridor evidence: $outputDirectory"
}
New-Item -ItemType Directory -Path $outputDirectory | Out-Null
$suiteDefinition | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outputDirectory 'suite.json') -Encoding utf8

$records = @()
foreach ($scenario in $scenarios) {
    foreach ($direction in @('up', 'down')) {
        $stem = "$($scenario.name)_${direction}_seed$($scenario.seed)_n${NumEnvs}"
        $output = Join-Path $outputDirectory "$stem.json"
        $log = Join-Path $outputDirectory "$stem.log"
        $traceArgs = @()
        if ($CaptureHoldTraces) {
            $traceArgs = @('--hold-trace', (Join-Path $outputDirectory "$stem.hold_trace.npz"))
        }
        Write-Output "RUN scenario=$($scenario.name) direction=$direction"
        & $launcher scripts/eval_stair_b2w.py --checkpoint $checkpointPath `
            --direction $direction --rise $scenario.rise --run $scenario.run --num-steps 6 --speed 0.7 `
            --num-envs $NumEnvs --horizon $Horizon --seed $scenario.seed --scenario-label $scenario.name `
            --cycle --cycle-protocol-v3 `
            --brake-profile --brake-distance 1.2 --brake-min-speed 0.25 --corridor-controller `
            --hold-wheel-action-scale $HoldWheelActionScale --hold-wheel-ramp-steps $HoldWheelRampSteps `
            --hold-wheel-feedback-gain $HoldWheelFeedbackGain `
            --hold-wheel-feedback-ramp-steps $HoldWheelFeedbackRampSteps `
            @stopControllerArgs `
            @settledLatchArgs `
            @traceArgs `
            --suite-sha256 $suiteSha --output $output *> $log
        if ($LASTEXITCODE -ne 0) { throw "Evaluation failed: $stem (see $log)" }
        $metrics = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
        $exclusive = $metrics.success + $metrics.unsafe + $metrics.stop_failed + $metrics.timeouts + $metrics.incomplete
        if ($metrics.policy_actor_observation_dim -ne 57 -or $exclusive -ne $NumEnvs `
                -or $metrics.suite_sha256 -ne $suiteSha -or -not $metrics.corridor_controller.enabled `
                -or ($CaptureHoldTraces -and $metrics.hold_trace.complete_hold_traces -ne $metrics.passage_success) `
                -or ($SettledLatchVariant -and $metrics.cycle.settled_latch.variant -ne $SettledLatchVariant) `
                -or ($StopControllerVariant -and $metrics.cycle.filtered_stop_controller.variant -ne $StopControllerVariant)) {
            throw "Invalid evaluator result: $stem"
        }
        $records += [pscustomobject]@{
            scenario = $scenario.name
            direction = $direction
            seed = $scenario.seed
            rise_m = $scenario.rise
            run_m = $scenario.run
            success = $metrics.success
            success_fraction = $metrics.success / $NumEnvs
            passage_success = $metrics.passage_success
            unsafe = $metrics.unsafe
            stop_failed = $metrics.stop_failed
            timeouts = $metrics.timeouts
            incomplete = $metrics.incomplete
            lateral_p95_m = $metrics.max_abs_lateral_drift_m.p95
            lateral_max_m = $metrics.max_abs_lateral_drift_m.maximum
            wheel_saturation_fraction = $metrics.safety_telemetry.overall.wheels.torque_utilization.at_or_above_95pct_fraction
            hold_wheel_saturation_fraction = $metrics.safety_telemetry.by_phase.hold.wheels.torque_utilization.at_or_above_95pct_fraction
            wheel_clipping_fraction = $metrics.safety_telemetry.overall.wheels.torque_utilization.computed_to_applied_clipping_fraction
            wheel_rolling_residual_rms_m_s = $metrics.safety_telemetry.overall.wheel_rolling_residual_m_s.rms
            leg_joint_margin_min = $metrics.safety_telemetry.overall.leg_soft_joint_limit_margin_fraction.absolute_min
            hold_leg_joint_margin_min = $metrics.safety_telemetry.by_phase.hold.leg_soft_joint_limit_margin_fraction.absolute_min
            settled_latch_count = if ($SettledLatchVariant) { $metrics.cycle.settled_latch.latched_environment_count } else { 0 }
            policy_sha256 = $metrics.policy_sha256
        }
        Write-Output ("DONE scenario={0} direction={1} cycle={2}/{3} unsafe={4} stop_failed={5}" -f `
            $scenario.name, $direction, $metrics.success, $NumEnvs, $metrics.unsafe, $metrics.stop_failed)
    }
}

$minimumCellSuccess = ($records.success | Measure-Object -Minimum).Minimum
$summary = [ordered]@{
    schema = 'b2w_cycle57_corridor_qualification_v1'
    selection_status = 'post_selection_controller_qualification'
    suite_sha256 = $suiteSha
    suite = $suiteDefinition
    checkpoint = $checkpointPath
    policy_sha256 = $records[0].policy_sha256
    stop_controller_variant = $StopControllerVariant
    settled_latch_variant = $SettledLatchVariant
    minimum_cell_success = $minimumCellSuccess
    minimum_cell_success_fraction = $minimumCellSuccess / $NumEnvs
    each_cell_at_least_95pct = ($minimumCellSuccess / $NumEnvs) -ge 0.95
    total_success = ($records.success | Measure-Object -Sum).Sum
    total_unsafe = ($records.unsafe | Measure-Object -Sum).Sum
    total_stop_failed = ($records.stop_failed | Measure-Object -Sum).Sum
    total_timeouts = ($records.timeouts | Measure-Object -Sum).Sum
    total_incomplete = ($records.incomplete | Measure-Object -Sum).Sum
    max_lateral_drift_m = ($records.lateral_max_m | Measure-Object -Maximum).Maximum
    wheel_saturation_fraction_worst = ($records.wheel_saturation_fraction | Measure-Object -Maximum).Maximum
    hold_wheel_saturation_fraction_worst = ($records.hold_wheel_saturation_fraction | Measure-Object -Maximum).Maximum
    wheel_clipping_fraction_worst = ($records.wheel_clipping_fraction | Measure-Object -Maximum).Maximum
    wheel_rolling_residual_rms_worst_m_s = ($records.wheel_rolling_residual_rms_m_s | Measure-Object -Maximum).Maximum
    leg_joint_margin_min = ($records.leg_joint_margin_min | Measure-Object -Minimum).Minimum
    hold_leg_joint_margin_min = ($records.hold_leg_joint_margin_min | Measure-Object -Minimum).Minimum
    settled_latch_count = ($records.settled_latch_count | Measure-Object -Sum).Sum
    cells = $records
}
$summaryPath = Join-Path $outputDirectory 'summary.json'
$summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $summaryPath -Encoding utf8
$records | Export-Csv -LiteralPath (Join-Path $outputDirectory 'cells.csv') -NoTypeInformation -Encoding utf8
Write-Output "SUMMARY=$summaryPath"
$records | Format-Table scenario, direction, success, unsafe, stop_failed, lateral_max_m, wheel_saturation_fraction -AutoSize
