"""Explicitly requested 150->350 diagnostic continuation after the failed Rough gate."""
from __future__ import annotations
import argparse, os, shutil, sys, traceback
from pathlib import Path
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import sha256, write_json, utc_now
from run_rough_r0 import own_child, PYTHON, read
from rough_training_protocol import SOURCES, ANCHOR, verify_run
from rough_evaluation import FAMILIES, CASE_SEEDS, make_cases, flat_regression
from run_rough_tilt_correction import verify_rough, verify_config_change, FLAT_SEEDS, PARENT
from run_reference_transfer import assert_idle_project, verify_evaluation, summary_pass

NAME = 'rough_requested_continue_20260920'
OUT = ROOT/'logs/rough'/NAME
QUAL = ROOT/'logs/qualification'/NAME
PRIOR = ROOT/'docs/results/rough_tilt_correction_20260920.json'
PROTOCOL = ROOT/'docs/ROUGH_REQUESTED_CONTINUATION.md'
SEEDS = (57, 58)


def select_parents(prior):
    """The explicit exception covers only this completed 150-update Rough quality stop."""
    if (prior['status'] != 'stopped_quality_gate' or prior.get('error')
            or prior.get('stopped_at') != 150 or prior['num_envs'] != 4096
            or prior['seeds'] != list(SEEDS) or len(prior['milestones']) != 1):
        raise ValueError('Requires the disclosed Rough150 quality stop, not a technical failure')
    milestone = prior['milestones'][0]
    if (milestone['cumulative_updates'] != 150 or milestone['status'] != 'failed_quality_gate'
            or milestone['all_gates_passed'] or set(milestone['training']) != {'57', '58'}):
        raise ValueError('Unexpected parent milestone or incomplete seed pair')
    for seed in SEEDS:
        run = milestone['training'][str(seed)]
        if (run['seed'] != seed or Path(run['checkpoint']).name != 'model_149.pt'
                or len(run['checkpoint_sha256']) != 64):
            raise ValueError('Requires each own completed model_149 checkpoint')
        profiles = milestone['flat'][str(seed)]
        if set(profiles) != set(FLAT_SEEDS) or not all(v['passed'] for v in profiles.values()):
            raise ValueError('Exception does not cover a Flat regression failure')
        expected = {f'{f}/0/{p}' for f in FAMILIES for p in CASE_SEEDS}
        if set(milestone['rough'][str(seed)]) != expected:
            raise ValueError('Missing original Rough evaluation batches')
    return {seed: milestone['training'][str(seed)] for seed in SEEDS}


def training_command(seed, parent):
    if seed not in SEEDS or parent['seed'] != seed or Path(parent['checkpoint']).name != 'model_149.pt':
        raise ValueError('Wrong requested continuation lineage')
    label = f'{NAME}_s{seed}_stage2'
    return label, [PYTHON, '-B', '-u', 'scripts/train_b2w.py', '--rough_transfer',
                  '--rough_tilt_termination', '--headless', '--device', 'cuda:0',
                  '--num_envs', '4096', '--seed', str(seed), '--max_iterations', '200',
                  '--run_name', label, '--resume', str(ROOT/parent['checkpoint']),
                  '--reference_init', str(ANCHOR), '--pure_yaw_fraction', '.25',
                  '--reference_update_probe', '--critic_warmup_updates', '50',
                  '--reference_drift_limit', '.25', '--rough_stage', '2']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--continue_after_failed_rough150', action='store_true', required=True)
    parser.parse_args()
    configure_process(); os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    assert_idle_project(__file__)
    prior = read(PRIOR); initial = select_parents(prior)
    for path, expected in prior['source_sha256'].items():
        if sha256(ROOT/path) != expected:
            raise ValueError('Validated training/evaluation source changed: '+path)
    for seed, run in initial.items():
        for key in ('checkpoint', 'policy'):
            if sha256(ROOT/run[key]) != run[key+'_sha256']:
                raise ValueError('Parent artifact changed: '+run[key])
        m = read(ROOT/run['training_manifest'])
        if not m['rough_tilt_termination'] or m['rough_stage'] != 1:
            raise ValueError('Parent must use the validated tilt correction')
        verified = verify_run(f'rough_tilt_correction_20260920_s{seed}_stage1', 4096, 50, 100, seed, False)
        if verified['checkpoint_sha256'] != run['checkpoint_sha256']:
            raise ValueError('Parent verification mismatch')

    # Bind old evaluation rows and physical samples before allocating new training work.
    flat_physics = {}; rough_physics = {}; flat_parent = {}
    verification = read(ROOT/'docs/results/2026-09-19-reference-qualification-verification.json')
    for profile, eval_seed in FLAT_SEEDS.items():
        path = PARENT/(profile+'.json'); report = read(path)
        if verification['verified_sha256'][str(path.relative_to(ROOT))] != sha256(path):
            raise ValueError('Qualified Flat report changed')
        summary = verify_evaluation(report, sha256(ANCHOR), profile, report['cases'], flat_physics,
                                    evaluation_seed=eval_seed)
        if not summary_pass(summary):
            raise ValueError('Qualified parent Flat gate failed')
        flat_parent[profile] = dict(cases=report['cases'], summary=summary)
    old = prior['milestones'][0]
    for seed in SEEDS:
        run = initial[seed]
        for profile, record in old['flat'][str(seed)].items():
            path = ROOT/record['report']; report = read(path)
            if sha256(path) != record['sha256']:
                raise ValueError('Parent Flat evaluation changed')
            summary = verify_evaluation(report, run['policy_sha256'], profile, flat_parent[profile]['cases'],
                                        flat_physics, evaluation_seed=FLAT_SEEDS[profile])
            if not flat_regression(summary, flat_parent[profile]['summary']):
                raise ValueError('Parent Flat regression does not pass')
        for key, record in old['rough'][str(seed)].items():
            family, level, profile = key.split('/')
            path = ROOT/record['report']
            if sha256(path) != record['sha256']:
                raise ValueError('Original Rough report changed')
            summary = verify_rough(read(path), run, family, int(level), profile, rough_physics, .90)
            if summary != record['summary']:
                raise ValueError('Original Rough summary differs from complete raw rows')

    if list((ROOT/'logs/rsl_rl/unitree_b2w_rough').glob('*_'+NAME+'*/manifest.json')):
        raise ValueError('Requested continuation already started; no automatic restart')
    OUT.mkdir(parents=True, exist_ok=False); QUAL.mkdir(parents=True, exist_ok=False)
    (OUT/'source').mkdir()
    sources = (*SOURCES, 'run_reference_transfer.py', 'run_rough_tilt_correction.py', Path(__file__).name)
    frozen = {f'scripts/{name}': sha256(ROOT/'scripts'/name) for name in sources}
    frozen[str(PROTOCOL.relative_to(ROOT))] = sha256(PROTOCOL)
    frozen[str(PRIOR.relative_to(ROOT))] = sha256(PRIOR)
    for run in initial.values():
        for key in ('checkpoint', 'training_manifest'):
            frozen[run[key]] = sha256(ROOT/run[key])
    milestone = dict(cumulative_updates=350, status='training', training={}, flat={}, rough={})
    job = dict(status='starting', started_utc=utc_now(), supervisor_pid=os.getpid(), stages=[],
               milestones=[milestone], seeds=list(SEEDS), num_envs=4096, concurrent_training_processes=1,
               initial_parents=initial, new_updates_per_seed=200, final_updates_per_seed=350,
               max_training_transitions=400*4096*24, source_sha256=frozen,
               protocol=str(PROTOCOL.relative_to(ROOT)), protocol_sha256=sha256(PROTOCOL),
               prior_job=str(PRIOR.relative_to(ROOT)), prior_job_sha256=sha256(PRIOR),
               user_request='продолжай обучение', explicitly_requested_after_failed_rough150=True,
               scope='Diagnostic continuation; old milestone150 remains failed',
               prior_milestone150_passed=False, development_protocol_passed=False,
               policy_quality_accepted=False, qualification_started=False, hardware_release_accepted=False,
               automatic_extension=False, active_milestone=350)
    save = lambda: write_json(OUT/'job.json', job)
    for name in sources:
        shutil.copyfile(ROOT/'scripts'/name, OUT/'source'/name)
    shutil.copyfile(PROTOCOL, OUT/'source'/PROTOCOL.name)
    cases = {f'{f}/{level}/{p}': make_cases(f, level, p) for f in FAMILIES for level in range(3) for p in CASE_SEEDS}
    write_json(OUT/'frozen_cases.json', cases)
    job['rough_cases_sha256'] = sha256(OUT/'frozen_cases.json')
    if job['rough_cases_sha256'] != prior['rough_cases_sha256']:
        raise ValueError('Original frozen Rough cases changed')
    save()
    try:
        for seed in SEEDS:
            label, command = training_command(seed, initial[seed])
            job.update(status='training', active_seed=seed); save()
            stage = own_child(command, OUT/f's{seed}_to350', job, save)
            run = verify_run(label, 4096, 150, 200, seed, False)
            stage['config_validation'] = verify_config_change((ROOT/initial[seed]['training_manifest']).parent,
                                                              (ROOT/run['training_manifest']).parent)
            stage['validation'] = run; milestone['training'][str(seed)] = run; save()

        job['status'] = 'evaluating'; milestone['status'] = 'evaluating'; save()
        all_good = True
        for seed in SEEDS:
            job['active_seed'] = seed
            run = milestone['training'][str(seed)]; milestone['flat'][str(seed)] = {}
            for profile, eval_seed in FLAT_SEEDS.items():
                label = f's{seed}_u350_flat_{profile}'; path = QUAL/(label+'.json')
                own_child([PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py', '--headless', '--device', 'cuda:0',
                           '--suite', 'flat100', '--num_envs', '100', '--seed', str(eval_seed), '--physical_profile', profile,
                           '--policy', str(ROOT/run['policy']), '--report', str(path)], OUT/label, job, save, timeout_seconds=1800)
                summary = verify_evaluation(read(path), run['policy_sha256'], profile, flat_parent[profile]['cases'],
                                            flat_physics, evaluation_seed=eval_seed)
                passed = flat_regression(summary, flat_parent[profile]['summary'])
                milestone['flat'][str(seed)][profile] = dict(passed=passed, summary=summary,
                                                            report=str(path.relative_to(ROOT)), sha256=sha256(path))
                all_good &= passed; save()
            # This fixed diagnostic budget collects every final batch even if a quality criterion fails.
            milestone['rough'][str(seed)] = {}
            for level in range(3):
                for family in FAMILIES:
                    for profile in CASE_SEEDS:
                        label = f's{seed}_u350_{family}_l{level}_{profile}'; path = QUAL/(label+'.json')
                        own_child([PYTHON, '-B', '-u', 'scripts/replay_rough_b2w.py', '--policy', str(ROOT/run['policy']),
                                   '--report', str(path), '--family', family, '--level', str(level), '--physical_profile', profile],
                                  OUT/label, job, save, timeout_seconds=1800)
                        summary = verify_rough(read(path), run, family, level, profile, rough_physics, .95)
                        milestone['rough'][str(seed)][f'{family}/{level}/{profile}'] = dict(
                            summary=summary, report=str(path.relative_to(ROOT)), sha256=sha256(path))
                        all_good &= summary['passed']; save()
            reached = all(value >= 2 for value in run['curriculum']['levels'][1:])
            milestone['rough'][str(seed)]['curriculum_reached_level2'] = reached
            all_good &= reached; save()
        milestone.update(status='passed_final_checks' if all_good else 'failed_final_checks',
                         all_gates_passed=bool(all_good))
        job.update(status='completed_diagnostic', final_checks_passed=bool(all_good)); return 0
    except BaseException as exc:
        job.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc()); return 1
    finally:
        job['finished_utc'] = utc_now(); save(); write_json(ROOT/'docs/results'/f'{NAME}.json', job)


if __name__ == '__main__':
    raise SystemExit(main())
