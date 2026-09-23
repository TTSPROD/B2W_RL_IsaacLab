"""Two fresh Flat54-derived seeds; Rough wheel corridor terminal and frozen quality gates."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import sha256, write_json, utc_now
from run_rough_r0 import own_child, PYTHON, read
from rough_training_protocol import ANCHOR, verify_run
from rough_evaluation import FAMILIES, CASE_SEEDS, make_cases, flat_regression
from run_rough_route_correction import verify_rough, FLAT_SEEDS, PARENT
from run_rough_corridor_preflight import (
    SOURCES, PROTOCOL, BASELINE, ROUTE_FINAL, frozen_inputs, require_finite, verify_corridor_run,
)

NAME = 'rough_corridor_training_20260920'
SEEDS = (63, 64)
BUDGET = (50, 100, 200)
OUT = ROOT/'logs/rough'/NAME
QUAL = ROOT/'logs/qualification'/NAME
CAPACITY = ROOT/'docs/results/rough_capacity_20260919.json'
PUBLISHED = ROOT/'docs/results'/f'{NAME}.json'


def validate_preflight(path):
    path = (ROOT/path).resolve()
    if not path.is_relative_to((ROOT/'docs/results').resolve()):
        raise ValueError('Published project preflight required')
    preflight = read(path)
    require_finite(preflight, 'preflight')
    if (preflight.get('status') != 'passed' or not preflight.get('precision_tracking')
            or not preflight.get('wheel_corridor') or not preflight.get('route_commands') or preflight.get('num_envs') != 64
            or preflight.get('max_training_transitions') != 4*64*24):
        raise ValueError('Passed precision 2+2 preflight required')
    if preflight['source_sha256'] != frozen_inputs():
        raise ValueError('Preflight source/protocol/historical configuration changed')
    if preflight.get('protocol_sha256') != sha256(PROTOCOL) or preflight.get('baseline_sha256') != sha256(BASELINE):
        raise ValueError('Preflight protocol or reference baseline changed')
    if [stage['name'] for stage in preflight['stages']] != ['train', 'resume']:
        raise ValueError('Both native smoke stages required')
    for index, stage in enumerate(preflight['stages']):
        if stage.get('status') != 'completed' or stage.get('external_exit_code') != 0:
            raise ValueError('Preflight child did not complete')
        old = stage['validation']
        for key in ('checkpoint', 'policy'):
            if sha256(ROOT/old[key]) != old[key+'_sha256']:
                raise ValueError('Smoke artifact changed: '+key)
        label = path.stem+'_'+stage['name']
        current = verify_run(label, 64, index*2, 2, preflight['seed'], False)
        if current['checkpoint_sha256'] != old['checkpoint_sha256']:
            raise ValueError('Wrong smoke checkpoint')
        if verify_corridor_run(ROOT/current['training_manifest'], smoke=True) != stage['corridor_validation']:
            raise ValueError('Smoke precision configuration evidence changed')
    return path, preflight


def training_command(seed, stage_index, previous=None):
    if seed not in SEEDS or stage_index not in range(3):
        raise ValueError('Unregistered precision workload')
    if (stage_index == 0) != (previous is None):
        raise ValueError('Only own previous stage may be resumed')
    label = f'{NAME}_s{seed}_stage{stage_index}'
    command = [PYTHON, '-B', '-u', 'scripts/train_b2w_desktop.py', '--rough_transfer',
        '--rough_tilt_termination', '--rough_route_commands', '--rough_precision_tracking', '--rough_wheel_corridor',
        '--headless', '--device', 'cuda:0', '--num_envs', '4096', '--seed', str(seed),
        '--max_iterations', str(BUDGET[stage_index]), '--run_name', label,
        '--reference_init', str(ANCHOR), '--pure_yaw_fraction', '.25', '--reference_update_probe',
        '--critic_warmup_updates', '50', '--reference_drift_limit', '.25', '--rough_stage', str(stage_index)]
    if previous is not None:
        expected_iteration = sum(BUDGET[:stage_index])-1
        if previous['seed'] != seed or Path(previous['checkpoint']).name != f'model_{expected_iteration}.pt':
            raise ValueError('Wrong precision resume seed or iteration')
        if sha256(ROOT/previous['checkpoint']) != previous['checkpoint_sha256']:
            raise ValueError('Own checkpoint changed before resume')
        command += ['--resume', str(ROOT/previous['checkpoint'])]
    return label, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', type=Path, required=True)
    args = parser.parse_args()
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from run_reference_transfer import assert_idle_project, verify_evaluation, summary_pass
    from flat_evaluation import summarize as summarize_flat
    assert_idle_project(__file__)
    if OUT.exists() or QUAL.exists() or PUBLISHED.exists():
        raise ValueError('Precision experiment already exists; no restart or replacement')
    preflight_path, preflight = validate_preflight(args.preflight)
    capacity = read(CAPACITY)
    if (capacity['status'] != 'completed' or capacity['selection']['num_envs'] != 4096
            or capacity['selection']['concurrent_seeds'] != 1):
        raise ValueError('Measured single4096 Rough capacity required')
    if read(BASELINE)['status'] != 'completed_diagnostic':
        raise ValueError('Completed frozen reference/anchor baseline required')
    for path in (ROOT/'logs/rsl_rl').glob('*/*/manifest.json'):
        if read(path).get('seed') in SEEDS:
            raise ValueError('Development seed already used; no replacement allowed')
    verification_path = ROOT/'docs/results/2026-09-19-reference-qualification-verification.json'
    verification = read(verification_path)
    frozen = dict(preflight['source_sha256'])
    for path in (preflight_path, CAPACITY, verification_path):
        frozen[str(path.relative_to(ROOT))] = sha256(path)
    flat_physics, rough_physics, parents, previous = {}, {}, {}, {}
    for profile, eval_seed in FLAT_SEEDS.items():
        path = PARENT/(profile+'.json')
        value = read(path)
        relative = str(path.relative_to(ROOT))
        if verification['verified_sha256'].get(relative) != sha256(path):
            raise ValueError('Frozen Flat parent report hash mismatch')
        require_finite(value, 'Flat parent')
        verify_evaluation(value, sha256(ANCHOR), profile, value['cases'], flat_physics, evaluation_seed=eval_seed)
        value['summary'] = summarize_flat(value['results'])
        if not summary_pass(value['summary']):
            raise ValueError('Qualified parent no longer passes')
        parents[profile] = value
        frozen[relative] = sha256(path)
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    (OUT/'source').mkdir()
    job = dict(status='starting', started_utc=utc_now(), supervisor_pid=os.getpid(), stages=[], milestones=[],
        seeds=list(SEEDS), updates=list(BUDGET), num_envs=4096, concurrent_training_processes=1,
        max_training_transitions=2*350*4096*24, anchor=str(ANCHOR.relative_to(ROOT)), anchor_sha256=sha256(ANCHOR),
        preflight=str(preflight_path.relative_to(ROOT)), preflight_sha256=sha256(preflight_path),
        capacity=str(CAPACITY.relative_to(ROOT)), capacity_sha256=sha256(CAPACITY),
        protocol=str(PROTOCOL.relative_to(ROOT)), protocol_sha256=sha256(PROTOCOL),
        reference_baseline=str(BASELINE.relative_to(ROOT)), reference_baseline_sha256=sha256(BASELINE),
        correction='Rough-only sticky wheel corridor true terminal and consistent curriculum; precision rewards and Flat preserved',
        historical_comparison='Precision61/62 at150 are historical comparators, not paired causal controls',
        shared_pretrained_lineage=True, independent_from_scratch_training=False,
        source_sha256=frozen, policy_quality_accepted=False, development_protocol_passed=False,
        qualification_started=False, hardware_release_accepted=False, automatic_extension=False,
        evaluate_all_registered_suites_before_quality_stop=True)
    save = lambda: write_json(OUT/'job.json', job)
    for source in SOURCES:
        shutil.copyfile(ROOT/'scripts'/source, OUT/'source'/source)
    shutil.copyfile(PROTOCOL, OUT/'source'/PROTOCOL.name)
    cases = {f'{family}/{level}/{profile}': make_cases(family, level, profile)
             for family in FAMILIES for level in range(3) for profile in CASE_SEEDS}
    write_json(OUT/'frozen_cases.json', cases)
    job['rough_cases_sha256'] = sha256(OUT/'frozen_cases.json')
    if job['rough_cases_sha256'] != read(ROUTE_FINAL)['rough_cases_sha256']:
        raise ValueError('Frozen Rough evaluation cases changed')
    frozen[str((OUT/'frozen_cases.json').relative_to(ROOT))] = job['rough_cases_sha256']
    save()
    try:
        for stage_index, updates in enumerate(BUDGET):
            start = sum(BUDGET[:stage_index])
            cumulative = start+updates
            milestone = dict(cumulative_updates=cumulative, training={}, flat={}, rough={}, status='training')
            job['milestones'].append(milestone)
            job.update(status='training', active_milestone=cumulative)
            save()
            for seed in SEEDS:
                label, command = training_command(seed, stage_index, previous.get(seed))
                job['active_seed'] = seed
                save()
                stage = own_child(command, OUT/f's{seed}_to{cumulative}', job, save)
                result = verify_run(label, 4096, start, updates, seed, stage_index == 0)
                require_finite(result, 'training validation')
                stage['corridor_validation'] = verify_corridor_run(ROOT/result['training_manifest'], smoke=False)
                stage['validation'] = result
                milestone['training'][str(seed)] = result
                previous[seed] = result
                save()
            milestone['status'] = 'evaluating'
            job['status'] = 'evaluating'
            all_good = True
            save()
            for seed in SEEDS:
                run = previous[seed]
                milestone['flat'][str(seed)] = {}
                for profile, eval_seed in FLAT_SEEDS.items():
                    label = f's{seed}_u{cumulative}_flat_{profile}'
                    report = QUAL/(label+'.json')
                    own_child([PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py', '--headless', '--device', 'cuda:0',
                        '--suite', 'flat100', '--num_envs', '100', '--seed', str(eval_seed), '--physical_profile', profile,
                        '--policy', str(ROOT/run['policy']), '--report', str(report)], OUT/label, job, save, timeout_seconds=1800)
                    value = read(report)
                    require_finite(value, 'Flat evaluation')
                    verify_evaluation(value, run['policy_sha256'], profile, parents[profile]['cases'], flat_physics, evaluation_seed=eval_seed)
                    summary = summarize_flat(value['results'])
                    passed = flat_regression(summary, parents[profile]['summary'])
                    milestone['flat'][str(seed)][profile] = dict(passed=passed, summary=summary,
                        report=str(report.relative_to(ROOT)), sha256=sha256(report))
                    all_good &= passed
                    save()
            # Complete diagnostic coverage at 150/350 even after a quality failure;
            # technical failures still abort immediately, and failed gates prohibit further PPO.
            if cumulative >= 150:
                for seed in SEEDS:
                    run = previous[seed]
                    milestone['rough'][str(seed)] = {}
                    for level in ((0,) if cumulative == 150 else (0, 1, 2)):
                        for family in FAMILIES:
                            for profile in CASE_SEEDS:
                                label = f's{seed}_u{cumulative}_{family}_l{level}_{profile}'
                                report = QUAL/(label+'.json')
                                own_child([PYTHON, '-B', '-u', 'scripts/replay_rough_b2w.py',
                                    '--policy', str(ROOT/run['policy']), '--report', str(report),
                                    '--family', family, '--level', str(level), '--physical_profile', profile],
                                    OUT/label, job, save, timeout_seconds=1800)
                                value = read(report)
                                require_finite(value, 'Rough evaluation')
                                summary = verify_rough(value, run, family, level, profile, rough_physics,
                                                       .90 if cumulative == 150 else .95)
                                milestone['rough'][str(seed)][f'{family}/{level}/{profile}'] = dict(summary=summary,
                                    report=str(report.relative_to(ROOT)), sha256=sha256(report))
                                all_good &= summary['passed']
                                save()
                    if cumulative == 350:
                        reached = all(value >= 2 for value in run['curriculum']['levels'][1:])
                        milestone['rough'][str(seed)]['curriculum_reached_level2'] = reached
                        all_good &= reached
            milestone.update(status='passed' if all_good else 'failed_quality_gate', all_gates_passed=bool(all_good))
            save()
            if not all_good:
                job.update(status='stopped_quality_gate', stopped_at=cumulative)
                return 0
        job.update(status='development_passed', development_protocol_passed=True,
                   policy_quality_accepted=False, qualification_started=False)
        return 0
    except BaseException as exc:
        job.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        return 1
    finally:
        job['finished_utc'] = utc_now()
        save()
        write_json(PUBLISHED, job)


if __name__ == '__main__':
    raise SystemExit(main())
