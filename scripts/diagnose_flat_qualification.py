"""Summarize recorded qualification failures and training tails; no simulation."""
from collections import Counter
import json
from pathlib import Path
import statistics

from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import sha256, utc_now, write_json

JOB = ROOT / 'logs/qualification_runs/flat_headroom5_20260917/job.json'
OUTPUT = ROOT / 'docs/results/2026-09-18-flat-diagnosis.json'


def main():
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    job = json.loads(JOB.read_text())
    report = {'created_utc': utc_now(), 'source_job': str(JOB.relative_to(ROOT)),
              'source_job_sha256': sha256(JOB), 'evaluations': {}, 'training_tails': {}}
    all_failures = []
    for name, stage in job['evaluations'].items():
        path = ROOT / stage['report']
        result = json.loads(path.read_text())
        if sha256(path) != stage['report_sha256'] or result['status'] != 'completed':
            raise RuntimeError('Evaluation provenance mismatch')
        failures = result['first_failures']
        counts = Counter(body for f in failures for body in f['contact_bodies'])
        report['evaluations'][name] = {
            'report': stage['report'], 'sha256': sha256(path), 'summary': result['summary'],
            'failure_scenarios': dict(Counter(f['scenario'] for f in failures)),
            'contact_bodies': dict(counts),
            'first_contact_force_range_n': [min(f['contact_n'] for f in failures),
                                            max(f['contact_n'] for f in failures)] if failures else None,
            'raw_action_saturation_steps': result['raw_action_saturation_steps'],
            'max_abs_raw_action': max(r['max_abs_raw_action'] for r in result['results']),
            'live_observation_max_error': result['live_observation_max_error'],
            'live_action_target_max_error': result['live_action_target_max_error'],
            'signed_bias_by_scenario': {
                s: [statistics.mean(r['signed_tracking_bias_vx_vy_yaw'][axis]
                                    for r in result['results'] if r['scenario'] == s)
                    for axis in range(3)] for s in result['summary']['by_scenario']},
        }
        if name.startswith('seed'):
            all_failures.extend(failures)
    tags = ('Metrics/base_velocity/error_vel_xy', 'Metrics/base_velocity/error_vel_yaw',
            'Episode_Reward/undesired_contacts', 'Train/mean_reward', 'Train/mean_episode_length')
    for phase in ('parallel_training', 'resume_seed47'):
        for run in job[phase]['runs']:
            directory = (ROOT / run['training_manifest']).parent
            events = EventAccumulator(str(directory), size_guidance={'scalars': 0})
            events.Reload()
            windows = {}
            for low, high in ((2200, 2299), (2300, 2399), (2400, 2499)):
                values = {}
                for tag in tags:
                    rows = [r for r in events.Scalars(tag) if low <= r.step <= high]
                    if len(rows) != 100:
                        raise RuntimeError('Incomplete diagnostic window')
                    values[tag] = statistics.mean(r.value for r in rows)
                windows[f'{low}-{high}'] = values
            report['training_tails'][run['arm']] = {
                'manifest': run['training_manifest'], 'windows': windows,
                'env_config_sha256': sha256(directory / 'params/env.yaml'),
                'checkpoint': run['final_checkpoint'], 'checkpoint_sha256': run['final_checkpoint_sha256'],
            }
    report['failure_total'] = len(all_failures)
    report['failure_scenarios'] = dict(Counter(f['scenario'] for f in all_failures))
    report['contact_bodies'] = dict(Counter(b for f in all_failures for b in f['contact_bodies']))
    report['interpretation'] = {
        'raw_action_clipping_explains_failures': False,
        'actuator_torque_saturation_excluded': False,
        'training_contact_threshold_n': 1.0, 'training_contact_weight': -1.0,
        'illegal_contact_termination': None,
        'evaluation_contact_threshold_n': 1.0,
        'contact_objective_gap': 'Training penalizes contacts but continues; evaluation records sticky failure at each physics substep.',
        'model_or_evaluator_bug_established': False,
        'causal_conclusion': 'No causal diagnosis from aggregate curves alone. Test command schedule at equal budget; retain unchanged reward and evaluator.',
        'metrics_caveat': 'Training command-error metrics are not held-out RMS; randomization, noise and sampling differ. Torque saturation is separate from raw-action clipping.',
        'new_experiment': 'Seed48, constant mix versus 2500 upstream + 1500 mix; both 4000 updates with matched restart after update2500.',
    }
    write_json(OUTPUT, report)
    print(json.dumps({k: report[k] for k in ('failure_total', 'failure_scenarios', 'contact_bodies', 'training_tails')}, indent=2))


if __name__ == '__main__':
    main()
