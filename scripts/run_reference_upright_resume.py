"""Registered upright-reset continuation after a diagnosed reference drift stop."""
from pathlib import Path
import json, os, shutil, sys, traceback
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
import benchmark_parallel4096 as paired
import run_reference_transfer as original

NAME = 'flat_reference_upright_resume_20260919'
OUT = ROOT / 'logs/transfer' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
PRIOR = ROOT / 'logs/transfer/flat_reference_transfer_20260919/job.json'
DIAG = ROOT / 'docs/results/2026-09-19-reference-resume-diagnosis.json'
UPRIGHT = ROOT / 'docs/results/2026-09-19-reference-resume-upright-diagnosis.json'
FINAL = ROOT / 'docs/results/2026-09-19-reference-upright-final.json'
PROTOCOL = ROOT / 'docs/REFERENCE_RESUME.md'
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
SOURCES = tuple(sorted(set(original.SOURCES) | {'run_reference_upright_resume.py', 'diagnose_reference_resume.py'}))
read = original.read

def training_spec(previous):
    if previous['seed'] not in (52, 53) or previous['ending_runner_iteration'] != 149:
        raise ValueError('Requires original validated update150 parent')
    spec = original.training_spec(previous['seed'], 2, previous)
    spec['run_name'] = f'flat_ref_upright_s{previous["seed"]}_20260919'
    spec['extra_args'] += ['--flat_upright_resets', '--reference_update_probe']
    spec['expected_manifest']['flat_upright_resets'] = True
    return spec

def verify_reset_only(run):
    import yaml
    new_dir = original.project_file(run['training_manifest']).parent
    old_dir = original.project_file(run['checkpoint']).parent
    configs = [yaml.load((directory / 'params/env.yaml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
               for directory in (old_dir, new_dir)]
    before, after = configs
    path = ('events', 'randomize_reset_base', 'params', 'pose_range')
    left, right = before, after
    for key in path:
        left, right = left[key], right[key]
    for key in ('roll', 'pitch'):
        if tuple(map(float, left[key])) != (-3.14, 3.14) or tuple(map(float, right[key])) != (-.1, .1):
            raise ValueError('Wrong reset orientation change')
        left[key] = right[key]
    for cfg in configs:
        cfg.pop('log_dir', None)
    if before != after:
        raise ValueError('An unregistered environment field changed')
    agents = [yaml.safe_load((directory / 'params/agent.yaml').read_text(encoding='utf-8'))
              for directory in (old_dir, new_dir)]
    for key in ('algorithm', 'policy', 'obs_groups', 'num_steps_per_env', 'clip_actions'):
        if agents[0][key] != agents[1][key]:
            raise ValueError('Unregistered PPO change: ' + key)
    return {'only_environment_changes': ['log_dir', 'reset_pose.roll', 'reset_pose.pitch'],
            'ppo_preserved': True}

def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    original.assert_idle_project(Path(__file__))
    prior, diagnosis, upright = read(PRIOR), read(DIAG), read(UPRIGHT)
    if prior['status'] != 'failed' or not prior['milestones'][-1]['all_gates_pass'] or prior['milestones'][-1]['cumulative_updates'] != 150:
        raise RuntimeError('Expected failed final stage after passing update150')
    if diagnosis['status'] != 'completed' or upright['status'] != 'completed':
        raise RuntimeError('Both diagnostic comparisons must complete')
    bad = next(r for r in diagnosis['runs'] if r['seed'] == 53)
    if (bad['result']['before_update_reference_drift']['raw_action_rms'] <= .25 or
            bad['result']['after_update_reference_drift']['raw_action_rms'] >
            bad['result']['before_update_reference_drift']['raw_action_rms']):
        raise RuntimeError('Diagnosis does not establish pre-update drift violation')
    if {r['seed'] for r in upright['runs']} != {52, 53}:
        raise RuntimeError('Incomplete upright resume smoke')
    for run in upright['runs']:
        if run['external_exit_code'] != 0 or run['result']['after_update_reference_drift']['raw_action_rms'] >= .25:
            raise RuntimeError('Upright resume smoke failed')
        for key in ('manifest', 'probe'):
            if sha256(original.project_file(run[key])) != run[key + '_sha256']:
                raise RuntimeError('Diagnostic artifact changed')
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'prior_job': str(PRIOR.relative_to(ROOT)), 'diagnosis': str(DIAG.relative_to(ROOT)),
              'protocol': {'parent_updates': 150, 'new_updates_per_seed': 200, 'final_updates': 350,
                           'seeds': [52, 53], 'num_envs': 4096, 'rollout_steps': 24,
                           'new_training_transitions': 2 * 200 * 4096 * 24,
                           'reset_roll_pitch': [-.1, .1], 'reference_drift_limit': .25,
                           'other_mdp_and_ppo_settings': 'unchanged', 'only_final350_candidate': True,
                           'discarded_diagnostic_transitions': 4 * 4096 * 24,
                           'evaluation_scope': 'Same disclosed development cases; no release acceptance'},
              'exports': {}, 'evaluations': {}, 'release_accepted': False,
              'automatic_extension': False, 'automatic_rough_promotion': False}
    save = lambda: write_json(OUT / 'job.json', report)
    save()
    try:
        parents = prior['train_to_150']['runs']
        if len(parents) != 2 or {r['seed'] for r in parents} != {52, 53}:
            raise RuntimeError('Incomplete parent pair')
        files = [ROOT / 'scripts' / name for name in SOURCES] + [
            PRIOR, DIAG, UPRIGHT, PROTOCOL, ROOT / 'vendor/manifest.json', ROOT / original.REFERENCE]
        for parent in parents:
            if sha256(original.project_file(parent['final_checkpoint'])) != parent['final_checkpoint_sha256']:
                raise RuntimeError('Parent checkpoint changed')
            files += [ROOT / parent['final_checkpoint'], ROOT / parent['training_manifest']]
        properties, controls = {}, {}
        for key, stage in prior['evaluations'].items():
            if key.startswith('controls_') or key.startswith('updates150_'):
                path = original.project_file(stage['report'])
                if sha256(path) != stage['report_sha256'] or stage['external_exit_code'] != 0:
                    raise RuntimeError('Prior gate report changed')
                value = read(path)
                for source, digest in value['source_sha256'].items():
                    if sha256(ROOT / source) != digest:
                        raise RuntimeError('Prior evaluation source changed: ' + source)
                profile = 'bounded_v1' if key.endswith('bounded_v1') else 'nominal'
                summary = original.verify_evaluation(value, stage['policy_sha256'], profile,
                    prior['protocol']['cases'][profile], properties)
                if not original.summary_pass(summary):
                    raise RuntimeError('Prior comparison gate not passed')
                files.append(path)
                controls[key] = {'report': stage['report'], 'sha256': stage['report_sha256'],
                                 'summary': summary, 'reused': True}
        report['reused_prior_gates'] = controls
        report['frozen_sha256'] = {str(path.relative_to(ROOT)): sha256(path) for path in files}
        (OUT / 'source').mkdir()
        for name in SOURCES:
            shutil.copyfile(ROOT / 'scripts' / name, OUT / 'source' / name)
        shutil.copyfile(PROTOCOL, OUT / 'protocol.md')
        save()
        def frozen():
            for name, digest in report['frozen_sha256'].items():
                if sha256(original.project_file(name)) != digest:
                    raise RuntimeError('Frozen artifact changed: ' + name)
        report['preflight_memory'] = device_sample('nvidia-smi')
        if report['preflight_memory']['gpu_headroom_fraction'] < .5:
            raise RuntimeError('Requires at least50% free VRAM')
        paired.OUT = OUT
        report['status'] = 'training_to_350'
        save()
        stage = paired.run_pair([training_spec(parent) for parent in parents], 'train_to_350',
                                report, save, 3600, benchmark=True, minimum_gpu_headroom=.05)
        if stage['status'] != 'validated' or stage['resources']['telemetry_errors']:
            reasons = []
            for run in stage['runs']:
                if run.get('training_manifest'):
                    value = read(ROOT / run['training_manifest'])
                    reasons.append({'seed': run['seed'], 'manifest_status': value['status'], 'error': value.get('error'),
                                    'exit_code': run['external_exit_code']})
            report['child_failures'] = reasons
            raise RuntimeError(stage.get('error', 'Training validation failed'))
        frozen()
        policies = {}
        for run in stage['runs']:
            run['configuration_check'] = verify_reset_only(run)
            run['transfer_check'] = original.checkpoint_actor_check(run, frozen=False)
            label = f'seed{run["seed"]}'
            dest = QUAL / label / 'export/report.json'
            export_stage = {'name': 'export_' + label}
            report['exports'][label] = export_stage
            report['status'] = 'exporting'
            original.guarded_supervise([PYTHON, '-B', '-u', 'scripts/check_policy_contract.py',
                '--training-checkpoint', str(ROOT / run['final_checkpoint']), '--report', str(dest)],
                OUT / ('export_' + label), 600, export_stage, save)
            result = read(dest)['training_export']
            policy = original.project_file(result['export'])
            if result['status'] != 'passed' or result['checkpoint_sha256'] != run['final_checkpoint_sha256'] or sha256(policy) != result['export_sha256']:
                raise RuntimeError('Export parity/provenance failed')
            export_stage.update(report=str(dest.relative_to(ROOT)), report_sha256=sha256(dest), policy_sha256=sha256(policy))
            policies[label] = policy
            save()
        results = {}
        for label, policy in policies.items():
            results[label] = {}
            for profile, eval_seed in original.EVALUATIONS.items():
                frozen()
                key = label + '_' + profile
                report['status'] = 'evaluating_' + key
                ev = {'name': key}
                report['evaluations'][key] = ev
                dest = QUAL / label / (profile + '.json')
                original.guarded_supervise([PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py',
                    '--suite', 'flat100', '--num_envs', '100', '--seed', str(eval_seed),
                    '--physical_profile', profile, '--policy', str(policy), '--report', str(dest)],
                    OUT / key, 900, ev, save)
                value = read(dest)
                summary = original.verify_evaluation(value, sha256(policy), profile,
                    prior['protocol']['cases'][profile], properties)
                ev.update(report=str(dest.relative_to(ROOT)), report_sha256=sha256(dest), summary=summary,
                          first_failures=value['first_failures'], policy_sha256=sha256(policy),
                          physical_properties_sha256=properties[profile])
                results[label][profile] = summary
                save()
        frozen()
        report['decision'] = original.milestone_decision(results, 350)
        report['status'] = 'completed' if report['decision']['final_candidate'] else 'stopped_quality_gate'
    except BaseException as exc:
        report.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()
        write_json(FINAL, report)

if __name__ == '__main__':
    main()

