param(
    [Parameter(Mandatory = $true)]
    [string]$ReferenceCheckpoint,
    [Parameter(Mandatory = $true)]
    [string]$CandidateCheckpoint,
    [int]$NumEnvs = 64,
    [int]$Horizon = 900,
    [string]$Label = 'cycle57_candidate_heldout_20260924'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $PSScriptRoot 'run_local.ps1'
$reference = (Resolve-Path -LiteralPath $ReferenceCheckpoint).Path
$candidate = (Resolve-Path -LiteralPath $CandidateCheckpoint).Path
if ($reference -eq $candidate) { throw 'Reference and candidate checkpoints must differ' }
if ($NumEnvs -lt 1 -or $Horizon -lt 1) { throw 'NumEnvs and Horizon must be positive' }

# These cells are intentionally distinct from the seed-3001, 14 cm x 32 cm
# development screen used for checkpoint selection.
$scenarios = @(
    [ordered]@{ name = 'nominal_unseen'; seed = 4101; rise = 0.14; run = 0.32 },
    [ordered]@{ name = 'steep_unseen'; seed = 4102; rise = 0.16; run = 0.29 },
    [ordered]@{ name = 'shallow_unseen'; seed = 4103; rise = 0.12; run = 0.38 }
)
$suiteDefinition = [ordered]@{
    schema = 'b2w_cycle57_heldout_suite_v1'
    payload = 'none'
    num_envs_per_cell = $NumEnvs
    horizon_policy_steps = $Horizon
    speed_m_s = 0.7
    num_steps = 6
    cycle_protocol = 'v3'
    brake_profile = @{ distance_m = 1.2; minimum_speed_m_s = 0.25 }
    scenarios = $scenarios
    directions = @('up', 'down')
}
$suiteJson = $suiteDefinition | ConvertTo-Json -Depth 8 -Compress
$suiteBytes = [System.Text.Encoding]::UTF8.GetBytes($suiteJson)
$suiteSha = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($suiteBytes)).ToLowerInvariant()

$outputDirectory = Join-Path $root "logs/heldout_validation/$Label"
if (Test-Path -LiteralPath $outputDirectory) {
    throw "Refusing to overwrite held-out evidence: $outputDirectory"
}
New-Item -ItemType Directory -Path $outputDirectory | Out-Null
$suiteDefinition | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outputDirectory 'suite.json') -Encoding utf8

$policies = [ordered]@{ reference = $reference; candidate = $candidate }
$records = @()
foreach ($policyName in $policies.Keys) {
    $checkpoint = $policies[$policyName]
    foreach ($scenario in $scenarios) {
        foreach ($direction in @('up', 'down')) {
            $stem = "${policyName}_$($scenario.name)_${direction}_seed$($scenario.seed)_n${NumEnvs}"
            $output = Join-Path $outputDirectory "$stem.json"
            $log = Join-Path $outputDirectory "$stem.log"
            Write-Output "RUN policy=$policyName scenario=$($scenario.name) direction=$direction"
            & $launcher scripts/eval_stair_b2w.py --checkpoint $checkpoint `
                --direction $direction --rise $scenario.rise --run $scenario.run --num-steps 6 --speed 0.7 `
                --num-envs $NumEnvs --horizon $Horizon --seed $scenario.seed --cycle --cycle-protocol-v3 `
                --brake-profile --brake-distance 1.2 --brake-min-speed 0.25 --suite-sha256 $suiteSha `
                --output $output *> $log
            if ($LASTEXITCODE -ne 0) { throw "Evaluation failed: $stem (see $log)" }
            $metrics = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
            $exclusive = $metrics.success + $metrics.unsafe + $metrics.stop_failed + $metrics.timeouts + $metrics.incomplete
            if ($metrics.policy_actor_observation_dim -ne 57 -or $exclusive -ne $NumEnvs -or $metrics.suite_sha256 -ne $suiteSha) {
                throw "Invalid evaluator result: $stem"
            }
            $records += [pscustomobject]@{
                policy = $policyName
                scenario = $scenario.name
                direction = $direction
                seed = $scenario.seed
                rise_m = $scenario.rise
                run_m = $scenario.run
                success = $metrics.success
                unsafe = $metrics.unsafe
                stop_failed = $metrics.stop_failed
                timeouts = $metrics.timeouts
                incomplete = $metrics.incomplete
                passage_success = $metrics.passage_success
                policy_sha256 = $metrics.policy_sha256
                wheel_saturation_fraction = $metrics.safety_telemetry.overall.wheels.torque_utilization.at_or_above_95pct_fraction
                leg_saturation_fraction = $metrics.safety_telemetry.overall.legs.torque_utilization.at_or_above_95pct_fraction
                wheel_rolling_residual_rms_m_s = $metrics.safety_telemetry.overall.wheel_rolling_residual_m_s.rms
                action_delta_rms = $metrics.safety_telemetry.overall.action_delta.rms_per_action_element
            }
            Write-Output ("DONE policy={0} scenario={1} direction={2} cycle={3}/{4} unsafe={5}" -f `
                $policyName, $scenario.name, $direction, $metrics.success, $NumEnvs, $metrics.unsafe)
        }
    }
}

$aggregates = @()
foreach ($policyName in $policies.Keys) {
    $rows = @($records | Where-Object policy -eq $policyName)
    $aggregates += [pscustomobject]@{
        policy = $policyName
        checkpoint = $policies[$policyName]
        policy_sha256 = $rows[0].policy_sha256
        minimum_cell_success = ($rows.success | Measure-Object -Minimum).Minimum
        total_success = ($rows.success | Measure-Object -Sum).Sum
        total_unsafe = ($rows.unsafe | Measure-Object -Sum).Sum
        total_stop_failed = ($rows.stop_failed | Measure-Object -Sum).Sum
        total_timeouts = ($rows.timeouts | Measure-Object -Sum).Sum
        total_incomplete = ($rows.incomplete | Measure-Object -Sum).Sum
        wheel_saturation_fraction_worst = ($rows.wheel_saturation_fraction | Measure-Object -Maximum).Maximum
        leg_saturation_fraction_worst = ($rows.leg_saturation_fraction | Measure-Object -Maximum).Maximum
        wheel_rolling_residual_rms_worst_m_s = ($rows.wheel_rolling_residual_rms_m_s | Measure-Object -Maximum).Maximum
        action_delta_rms_worst = ($rows.action_delta_rms | Measure-Object -Maximum).Maximum
    }
}
$ranked = @($aggregates | Sort-Object `
    @{Expression='minimum_cell_success'; Descending=$true}, `
    @{Expression='total_unsafe'; Ascending=$true}, `
    @{Expression='total_stop_failed'; Ascending=$true}, `
    @{Expression='total_timeouts'; Ascending=$true}, `
    @{Expression='total_incomplete'; Ascending=$true}, `
    @{Expression='wheel_saturation_fraction_worst'; Ascending=$true}, `
    @{Expression='total_success'; Descending=$true})

$referenceAggregate = $aggregates | Where-Object policy -eq 'reference'
$candidateAggregate = $aggregates | Where-Object policy -eq 'candidate'
$summary = [ordered]@{
    schema = 'b2w_cycle57_heldout_validation_v1'
    selection_status = 'heldout_candidate_comparison'
    suite_sha256 = $suiteSha
    suite = $suiteDefinition
    ranking = 'lexicographic: minimum cell completion desc; unsafe/stop-failed/timeout/incomplete asc; actuator safety asc; total completion desc'
    candidate_minus_reference = [ordered]@{
        minimum_cell_success = $candidateAggregate.minimum_cell_success - $referenceAggregate.minimum_cell_success
        total_success = $candidateAggregate.total_success - $referenceAggregate.total_success
        total_unsafe = $candidateAggregate.total_unsafe - $referenceAggregate.total_unsafe
        total_stop_failed = $candidateAggregate.total_stop_failed - $referenceAggregate.total_stop_failed
        wheel_saturation_fraction_worst = $candidateAggregate.wheel_saturation_fraction_worst - $referenceAggregate.wheel_saturation_fraction_worst
    }
    ranking_result = $ranked
    cells = $records
}
$summaryPath = Join-Path $outputDirectory 'summary.json'
$summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $summaryPath -Encoding utf8
$records | Export-Csv -LiteralPath (Join-Path $outputDirectory 'cells.csv') -NoTypeInformation -Encoding utf8
Write-Output "SUMMARY=$summaryPath"
$ranked | Format-Table policy, minimum_cell_success, total_success, total_unsafe, total_stop_failed, wheel_saturation_fraction_worst -AutoSize
