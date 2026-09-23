"""Discard-only wheel-corridor fixture and exact own 2+2 PPO/resume smoke."""
from __future__ import annotations

import argparse
import copy
import math
import os
from pathlib import Path
import shutil
import sys
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import sha256, write_json, utc_now
from run_rough_r0 import own_child, PYTHON, read
from rough_training_protocol import SOURCES as BASE_SOURCES, ANCHOR, verify_run

PROTOCOL = ROOT/'docs/ROUGH_WHEEL_CORRIDOR.md'
SOURCES = tuple(dict.fromkeys((*BASE_SOURCES, 'rough_route_commands.py',
    'rough_precision_tracking.py', 'rough_wheel_corridor.py', 'trace_rough_b2w.py',
    'run_rough_corridor_trace.py', 'run_rough_route_correction.py',
    'run_reference_transfer.py', 'run_rough_corridor_preflight.py',
    'run_rough_corridor_training.py')))
BASELINE = ROOT/'docs/results/rough_reference_baseline_20260920.json'
ROUTE_PREFLIGHT = ROOT/'docs/results/rough_route_preflight_20260920_1.json'
ROUTE_ORIGINAL = ROOT/'docs/results/rough_route_correction_20260920.json'
ROUTE_FINAL = ROOT/'docs/results/rough_route_continue_20260920.json'
PRECISION_FINAL = ROOT/'docs/results/rough_precision_training_20260920.json'
TRACE = ROOT/'docs/results/rough_corridor_trace_20260920.json'


def require_finite(value, label='evidence'):
    """Reject JSON NaN/Infinity anywhere in numeric evidence."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite '+label)
    if isinstance(value, dict):
        for key, item in value.items():
            require_finite(item, label+'.'+str(key))
    elif isinstance(value, (list, tuple)):
        for item in value:
            require_finite(item, label)


def historical_route_manifest(smoke, stage_index=0):
    """Use same-size/stage historical route configuration, never failed PPO weights."""
    report = ROUTE_PREFLIGHT if smoke else ROUTE_FINAL if stage_index == 2 else ROUTE_ORIGINAL
    label = 'train' if smoke else 's59_to'+str((50, 150, 350)[stage_index])
    stages = [s for s in read(report)['stages'] if s['name'] == label]
    if len(stages) != 1 or stages[0]['status'] != 'completed' or stages[0]['external_exit_code'] != 0:
        raise ValueError('Missing completed historical route configuration')
    record = stages[0]
    path = (ROOT/record['validation']['training_manifest']).resolve()
    if not path.is_relative_to((ROOT/'logs').resolve()):
        raise ValueError('Historical manifest outside project logs')
    if sha256(path) != record['route_validation']['training_manifest_sha256']:
        raise ValueError('Historical route manifest changed')
    return path


def frozen_inputs():
    """Bind every source and historical config consumed by the new verifier."""
    paths = [ROOT/'scripts'/name for name in SOURCES]
    paths += [PROTOCOL, BASELINE, ROUTE_PREFLIGHT, ROUTE_ORIGINAL, ROUTE_FINAL, PRECISION_FINAL, TRACE, ANCHOR]
    for smoke, stage in ((True, 0), (False, 0), (False, 1), (False, 2)):
        manifest = historical_route_manifest(smoke, stage)
        paths += [manifest, manifest.parent/'params/env.yaml', manifest.parent/'params/agent.yaml']
    return {str(path.relative_to(ROOT)): sha256(path) for path in paths}


def verify_corridor_run(path, smoke):
    """Compare full effective env, allowing inherited precision std and the new wheel terminal."""
    import yaml
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT/'logs').resolve()):
        raise ValueError('Training manifest outside project logs')
    manifest = read(path)
    require_finite(manifest, 'training_manifest')
    if (manifest.get('status') != 'completed' or not manifest.get('rough_transfer')
            or not manifest.get('rough_wheel_corridor') or not manifest.get('rough_precision_tracking') or not manifest.get('rough_route_commands')
            or not manifest.get('rough_tilt_termination') or manifest.get('init_at_random_ep_len') is not False
            or manifest['num_envs'] != (64 if smoke else 4096)):
        raise ValueError('Precision/route/tilt/workload contract missing')
    baseline_path = historical_route_manifest(smoke, manifest['rough_stage'])
    load = lambda p: yaml.load(p.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    before = load(baseline_path.parent/'params/env.yaml')
    after = load(path.parent/'params/env.yaml')
    normalized = copy.deepcopy(after)
    changed = []
    for term, weight in (('track_lin_vel_xy_exp', 3.), ('track_ang_vel_z_exp', 1.5)):
        old, new = before['rewards'][term], after['rewards'][term]
        if (float(old['params']['std']) != .5 or float(new['params']['std']) != .25
                or float(old['weight']) != weight or float(new['weight']) != weight
                or old['func'] != new['func']):
            raise ValueError('Incorrect precision kernel or reward weight: '+term)
        normalized['rewards'][term]['params']['std'] = old['params']['std']
        changed.append('rewards.'+term+'.params.std')
    terminal = normalized['terminations'].pop('rough_wheel_corridor', None)
    expected_terminal = dict(func='rough_wheel_corridor:wheel_corridor_terminal', params={}, time_out='false')
    if terminal != expected_terminal:
        raise ValueError('Incorrect wheel corridor terminal or timeout semantics')
    if manifest['rough_curriculum'].get('wheel_corridor_enabled') is not True:
        raise ValueError('Wheel-aware curriculum state missing')
    # Seeds and output folders identify fresh experiments; no dynamics field is normalized.
    for config in (before, normalized):
        config.pop('seed', None)
        config.pop('log_dir', None)
    if before != normalized:
        differing = sorted(k for k in before.keys() | normalized.keys() if before.get(k) != normalized.get(k))
        raise ValueError('Unregistered MDP change beyond precision std and wheel terminal: '+', '.join(differing))
    agents = [load(p.parent/'params/agent.yaml') for p in (baseline_path, path)]
    for key in ('algorithm', 'policy', 'obs_groups', 'num_steps_per_env', 'clip_actions'):
        if agents[0][key] != agents[1][key]:
            raise ValueError('Unregistered PPO change: '+key)
    if int(agents[1]['num_steps_per_env']) != 24:
        raise ValueError('Rollout budget changed')
    for key in ('reference_transfer', 'flat_bank_drift'):
        if key not in manifest:
            raise ValueError('Missing drift evidence: '+key)
    transfer = manifest['reference_transfer']
    if (transfer['drift_limit'] != .25 or transfer['fixed_action_std'] != .1
            or transfer['critic_warmup_updates'] != (1 if smoke else 50)):
        raise ValueError('Transfer guards changed')
    if any(drift['raw_action_rms'] > .25 for drift in (transfer['latest_drift'], manifest['flat_bank_drift'])):
        raise ValueError('Drift guard exceeded')
    if smoke:
        for key in ('precision_tracking_fixture', 'route_command_fixture', 'tilt_termination_fixture', 'wheel_corridor_fixture'):
            if manifest.get(key, {}).get('passed') is not True:
                raise ValueError('Native fixture missing or failed: '+key)
    return dict(reward_changes_from_historical_route=changed, old_std=.5, new_std=.25,
                precision_recipe_preserved=True, wheel_corridor_terminal=True,
                wheel_corridor_fixture=manifest.get('wheel_corridor_fixture'),
                weights={'linear': 3., 'yaw': 1.5}, reward_scope='all Flat and Rough environments',
                constraint_scope='Rough terrain columns3-9 only',
                complete_mdp_comparison_passed=True, ppo_preserved=True,
                historical_route_manifest=str(baseline_path.relative_to(ROOT)),
                historical_route_manifest_sha256=sha256(baseline_path),
                native_fixture=manifest.get('precision_tracking_fixture'),
                training_manifest_sha256=sha256(path),
                env_yaml_sha256=sha256(path.parent/'params/env.yaml'),
                agent_yaml_sha256=sha256(path.parent/'params/agent.yaml'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, default=1, choices=range(1, 5))
    args = parser.parse_args()
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    name = f'rough_corridor_preflight_20260920_{args.attempt}'
    out = ROOT/'logs/rough'/name
    published = ROOT/'docs/results'/f'{name}.json'
    if out.exists() or published.exists():
        raise ValueError('Preflight attempt already exists; no overwrite')
    if read(BASELINE)['status'] != 'completed_diagnostic':
        raise ValueError('Completed reference/anchor baseline required')
    trace = read(TRACE)
    if trace['status'] != 'completed_diagnostic' or set(trace['summaries']) != {'61', '62'}:
        raise ValueError('Both passive traces must be complete')
    for record in trace['summaries'].values():
        if not record['original_rows_identical'] or sha256(ROOT/record['report']) != record['sha256']:
            raise ValueError('Passive trace evidence mismatch')
    frozen = frozen_inputs()
    seed = 6300+args.attempt
    for path in (ROOT/'logs/rsl_rl').glob('*/*/manifest.json'):
        if read(path).get('seed') == seed:
            raise ValueError('Technical seed already used; no automatic retry')
    out.mkdir(parents=True, exist_ok=False)
    (out/'source').mkdir()
    job = dict(status='running', started_utc=utc_now(), supervisor_pid=os.getpid(), stages=[],
               route_commands=True, precision_tracking=True, wheel_corridor=True, seed=seed,
               scope='Native wheel corridor/precision/route/tilt fixtures and 2+2 PPO/resume; discard all weights',
               policy_quality_accepted=False, automatic_extension=False,
               num_envs=64, max_training_transitions=4*64*24,
               baseline=str(BASELINE.relative_to(ROOT)), baseline_sha256=sha256(BASELINE),
               protocol=str(PROTOCOL.relative_to(ROOT)), protocol_sha256=sha256(PROTOCOL),
               source_sha256=frozen)
    save = lambda: write_json(out/'job.json', job)
    for source in SOURCES:
        shutil.copyfile(ROOT/'scripts'/source, out/'source'/source)
    shutil.copyfile(PROTOCOL, out/'source'/PROTOCOL.name)
    save()
    try:
        previous = None
        for label, start in (('train', 0), ('resume', 2)):
            suffix = name+'_'+label
            command = [PYTHON, '-B', '-u', 'scripts/train_b2w_desktop.py', '--rough_transfer',
                '--rough_tilt_termination', '--rough_route_commands', '--rough_precision_tracking', '--rough_wheel_corridor',
                '--headless', '--device', 'cuda:0', '--num_envs', '64', '--seed', str(seed),
                '--max_iterations', '2', '--run_name', suffix, '--reference_init', str(ANCHOR),
                '--pure_yaw_fraction', '.25', '--reference_update_probe', '--critic_warmup_updates', '1',
                '--reference_drift_limit', '.25', '--rough_stage', '0']
            if previous:
                if sha256(ROOT/previous['checkpoint']) != previous['checkpoint_sha256']:
                    raise ValueError('Own smoke resume checkpoint changed')
                command += ['--resume', str(ROOT/previous['checkpoint'])]
            stage = own_child(command, out/label, job, save)
            stage['validation'] = previous = verify_run(suffix, 64, start, 2, seed, False)
            stage['corridor_validation'] = verify_corridor_run(ROOT/previous['training_manifest'], smoke=True)
            save()
        job['status'] = 'passed'
        return 0
    except BaseException as exc:
        job.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        return 1
    finally:
        job['finished_utc'] = utc_now()
        save()
        write_json(published, job)


if __name__ == '__main__':
    raise SystemExit(main())
