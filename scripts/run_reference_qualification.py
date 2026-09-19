"""Three fresh transfer seeds, fixed successful schedule and final-only new cases."""
from pathlib import Path
import math, os, shutil, sys, traceback
sys.dont_write_bytecode = True
import run_reference_transfer as base
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from flat_evaluation import make_cases
from physical_evaluation import profile_spec
import benchmark_parallel4096 as paired

NAME = 'flat_reference_qualification_20260919'
OUT = ROOT / 'logs/transfer' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
PROTOCOL = ROOT / 'docs/REFERENCE_QUALIFICATION.md'
FINAL = ROOT / 'docs/results/2026-09-19-reference-qualification-final.json'
DEVELOPMENT = ROOT / 'docs/results/2026-09-19-reference-upright-final.json'
SEEDS = (54, 55, 56)
BATCHES = ((54, 55), (56,))
UPDATES = (50, 100, 200)
EVALUATIONS = {'nominal': 2026091961, 'bounded_v1': 2026091962}
SOURCES = tuple(sorted(set(base.SOURCES) | {Path(__file__).name}))
read = base.read


def training_spec(seed, segment, previous=None):
    if seed not in SEEDS or segment not in range(3):
        raise ValueError('Unregistered seed/stage')
    start = sum(UPDATES[:segment])
    if (previous is None) != (segment == 0):
        raise ValueError('Fresh first stage and own parent required')
    if previous and (previous['seed'] != seed or previous['ending_runner_iteration'] != start - 1):
        raise ValueError('Wrong parent seed or restart boundary')
    spec = {'arm': f'seed{seed}', 'seed': seed, 'num_envs': 4096,
            'iterations': UPDATES[segment], 'starting_runner_iteration': start,
            'run_name': f'{NAME}_s{seed}_stage{segment}',
            'extra_args': ['--reference_init', str(base.REFERENCE), '--critic_warmup_updates', '50',
                           '--reference_drift_limit', '0.25', '--pure_yaw_fraction', '0.25'],
            'expected_manifest': {'seed': seed, 'num_steps_per_env': 24, 'starting_learning_rate': 1e-4,
                                  'starting_runner_iteration': start, 'pure_yaw_fraction': .25,
                                  'effective_yaw_tracking_weight': 1.5, 'effective_undesired_contact_weight': -1.,
                                  'effective_base_height_weight': 0., 'flat_upright_resets': segment == 2}}
    if previous:
        spec.update(checkpoint=previous['final_checkpoint'], checkpoint_sha256=previous['final_checkpoint_sha256'])
    if segment == 2:
        spec['extra_args'] += ['--flat_upright_resets', '--reference_update_probe']
    return spec


def qualification_decision(results):
    if set(results) != {'reference', *(f'seed{s}' for s in SEEDS)} or any(set(v) != set(EVALUATIONS) for v in results.values()):
        raise ValueError('Incomplete final qualification matrix')
    passes = {name: {profile: base.summary_pass(summary) for profile, summary in profiles.items()}
              for name, profiles in results.items()}
    good = all(all(profiles.values()) for profiles in passes.values())
    return {'all_gates_pass': good, 'per_policy_profile_pass': passes,
            'flat_transfer_gate_passed': good, 'final_updates_per_seed': 350,
            'fresh_from_scratch_acceptance': False, 'hardware_release_accepted': False,
            'automatic_rough_promotion': False}


def verify_recipe(run, template):
    import yaml
    directories = [base.project_file(item['training_manifest']).parent for item in (run, template)]
    for filename, ignored in [('env.yaml', ('seed', 'log_dir')), ('agent.yaml', ('seed', 'run_name'))]:
        values = [yaml.load((directory / 'params' / filename).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
                  for directory in directories]
        for value in values:
            for key in ignored:
                value.pop(key, None)
        if values[0] != values[1]:
            changed = [k for k in set(values[0]) | set(values[1]) if values[0].get(k) != values[1].get(k)]
            raise ValueError(f'Recipe differs from successful development {filename}: {changed}')
    return {'environment_and_agent_match_development': True,
            'allowed_metadata_changes': ['seed', 'log_dir', 'run_name']}


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    base.assert_idle_project(Path(__file__))
    development = read(DEVELOPMENT)
    if development['status'] != 'completed' or not development['decision']['final_candidate']:
        raise RuntimeError('Development final350 did not pass')
    prior = read(base.project_file(development['prior_job']))
    templates = [prior['train_to_50']['runs'][0], prior['train_to_150']['runs'][0], development['train_to_350']['runs'][0]]
    for path in (ROOT / 'logs/rsl_rl').glob('*/*/manifest.json'):
        if read(path).get('seed') in SEEDS:
            raise RuntimeError('Qualification training seed already used: ' + str(path))
    for path in (ROOT / 'logs/qualification').rglob('*.json'):
        value = read(path)
        if isinstance(value, dict) and value.get('evaluation_seed') in EVALUATIONS.values():
            raise RuntimeError('Evaluation seed already disclosed: ' + str(path))
    # Native training/evaluation code must equal the successful run. Only orchestration changes.
    for name, digest in development['frozen_sha256'].items():
        if Path(name).name in set(base.SOURCES) - {'run_reference_transfer.py'}:
            if sha256(base.project_file(name)) != digest:
                raise RuntimeError('Successful recipe source changed: ' + name)
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    protocol = {'training_seeds': SEEDS, 'batches': BATCHES, 'segment_updates': UPDATES,
                'cumulative_milestones': [50, 150, 350], 'num_envs': 4096, 'rollout_steps': 24,
                'total_training_transitions': 3 * 350 * 4096 * 24,
                'initialization': 'Shared reference actor; three fresh critics, optimizers and RNG seeds',
                'reset_roll_pitch_by_segment': [[-3.14, 3.14], [-3.14, 3.14], [-.1, .1]],
                'critic_only_first_updates': 50, 'reference_drift_limit': .25,
                'evaluation_seeds': EVALUATIONS, 'profiles': {p: profile_spec(p) for p in EVALUATIONS},
                'cases': {p: make_cases(100, s, heldout=True) for p, s in EVALUATIONS.items()},
                'evaluation_scope': 'New cases, final350 once only; no intermediate candidate selection',
                'automatic_extension': False, 'automatic_rough_promotion': False}
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'protocol': protocol, 'exports': {}, 'evaluations': {}, 'final_runs': {}}
    save = lambda: write_json(OUT / 'job.json', report)
    try:
        files = [ROOT / 'scripts' / n for n in SOURCES] + [PROTOCOL, DEVELOPMENT,
                ROOT / 'vendor/manifest.json', ROOT / base.REFERENCE, base.project_file(development['prior_job'])]
        for run in templates:
            files += [base.project_file(run['training_manifest']).parent / 'params' / f for f in ('env.yaml', 'agent.yaml')]
        report['frozen_sha256'] = {str(p.relative_to(ROOT)): sha256(p) for p in files}
        (OUT / 'source').mkdir()
        for name in SOURCES:
            shutil.copyfile(ROOT / 'scripts' / name, OUT / 'source' / name)
        shutil.copyfile(PROTOCOL, OUT / 'protocol.md')
        write_json(OUT / 'protocol.json', protocol)
        save()

        def frozen():
            for name, digest in report['frozen_sha256'].items():
                if sha256(base.project_file(name)) != digest:
                    raise RuntimeError('Frozen artifact changed: ' + name)

        paired.OUT = OUT
        for batch in BATCHES:
            previous = {}
            for segment in range(3):
                frozen()
                memory = device_sample('nvidia-smi')
                if not math.isfinite(memory['gpu_headroom_fraction']) or memory['gpu_headroom_fraction'] < .5:
                    raise RuntimeError('Requires50% free VRAM before training')
                report['latest_preflight_memory'] = memory
                phase = f'batch{batch[0]}_to_{sum(UPDATES[:segment + 1])}'
                report['status'] = phase
                save()
                data = paired.run_pair([training_spec(seed, segment, previous.get(seed)) for seed in batch],
                                       phase, report, save, 3600, benchmark=True, minimum_gpu_headroom=.05)
                if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                    report['child_failures'] = [
                        {'seed': run['seed'], 'exit_code': run['external_exit_code'],
                         'manifest': read(base.project_file(run['training_manifest'])) if run.get('training_manifest') else None}
                        for run in data['runs']]
                    raise RuntimeError(data.get('error', 'Training/telemetry validation failed'))
                frozen()
                previous = {run['seed']: run for run in data['runs']}
                for run in previous.values():
                    run['recipe_check'] = verify_recipe(run, templates[segment])
                    run['transfer_check'] = base.checkpoint_actor_check(run, frozen=segment == 0)
                    if segment == 2 and run['transfer_check']['actor_exactly_matches_reference']:
                        raise RuntimeError('Final actor did not change')
                save()
            report['final_runs'].update({str(s): r for s, r in previous.items()})
            save()

        policies = {'reference': ROOT / base.REFERENCE}
        for seed, run in report['final_runs'].items():
            frozen()
            label = 'seed' + seed
            dest = QUAL / label / 'export/report.json'
            stage = {'name': 'export_' + label}
            report['exports'][label] = stage
            report['status'] = stage['name']
            base.guarded_supervise([base.PYTHON, '-B', '-u', 'scripts/check_policy_contract.py',
                '--training-checkpoint', str(base.project_file(run['final_checkpoint'])), '--report', str(dest)],
                OUT / stage['name'], 600, stage, save)
            value = read(dest)['training_export']
            policy = base.project_file(value['export'])
            if value['status'] != 'passed' or value['checkpoint_sha256'] != run['final_checkpoint_sha256'] or value['export_sha256'] != sha256(policy):
                raise RuntimeError('Export parity/provenance failed')
            stage.update(report=str(dest.relative_to(ROOT)), report_sha256=sha256(dest), policy_sha256=sha256(policy))
            policies[label] = policy
            save()
        results, properties = {}, {}
        for label, policy in policies.items():
            results[label] = {}
            for profile, evaluation_seed in EVALUATIONS.items():
                frozen()
                key = label + '_' + profile
                stage = {'name': key}
                report['evaluations'][key] = stage
                report['status'] = 'evaluating_' + key
                dest = QUAL / label / (profile + '.json')
                base.guarded_supervise([base.PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py',
                    '--suite', 'flat100', '--num_envs', '100', '--seed', str(evaluation_seed),
                    '--physical_profile', profile, '--policy', str(policy), '--report', str(dest)],
                    OUT / key, 900, stage, save)
                value = read(dest)
                summary = base.verify_evaluation(value, sha256(policy), profile, protocol['cases'][profile],
                                                 properties, evaluation_seed=evaluation_seed)
                stage.update(report=str(dest.relative_to(ROOT)), report_sha256=sha256(dest), policy_sha256=sha256(policy),
                             summary=summary, first_failures=value['first_failures'], physical_properties_sha256=properties[profile])
                results[label][profile] = summary
                save()
        frozen()
        report['decision'] = qualification_decision(results)
        report['status'] = 'completed' if report['decision']['all_gates_pass'] else 'stopped_quality_gate'
    except BaseException as exc:
        report.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()
        write_json(FINAL, report)

if __name__ == '__main__':
    main()
