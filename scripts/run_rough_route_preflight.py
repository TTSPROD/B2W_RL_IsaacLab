"""Discard-only native route fixture and 2+2 PPO/resume before the new recipe."""
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
from rough_training_protocol import SOURCES as BASE_SOURCES, ANCHOR, verify_run

SOURCES = (*BASE_SOURCES, 'rough_route_commands.py', 'run_rough_route_preflight.py')


def verify_route_run(path, smoke):
    """Check serialized effective configuration, not only a requested flag."""
    import yaml
    m = read(path)
    cfg = yaml.load((path.parent/'params/env.yaml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    agent = yaml.load((path.parent/'params/agent.yaml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    if not m.get('rough_route_commands') or not m.get('rough_tilt_termination') or m.get('init_at_random_ep_len') is not False:
        raise ValueError('Route/tilt/episode-clock contract missing')
    if float(cfg['episode_length_s']) != 22 or 'rough_route_commands' not in cfg['commands']['base_velocity']['class_type']:
        raise ValueError('Effective route config mismatch')
    if 'rough_route_commands' not in cfg['events']['randomize_reset_base']['func'] or 'rough_route_commands' not in cfg['terminations']['time_out']['func']:
        raise ValueError('Route reset or per-tile time limit missing')
    if float(agent['algorithm']['learning_rate']) != 1e-4 or float(agent['algorithm']['clip_param']) != .1 or float(agent['algorithm']['entropy_coef']) != 0:
        raise ValueError('PPO changed')
    prior=read(ROOT/'docs/results/rough_r1_preflight_20260920_7.json')
    prior_manifest=ROOT/next(v['validation']['training_manifest'] for v in prior['stages'] if v['name']=='train')
    before=yaml.load((prior_manifest.parent/'params/env.yaml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    for key in ('rewards','observations','actions','sim','curriculum'):
        if cfg[key]!=before[key]:
            raise ValueError('Unregistered configuration change: '+key)
    for key,value in before['events'].items():
        if key!='randomize_reset_base' and cfg['events'].get(key)!=value:
            raise ValueError('Randomization event changed: '+key)
    if smoke and (not m['route_command_fixture']['passed'] or not m['tilt_termination_fixture']['passed']):
        raise ValueError('Native fixture failed')
    return dict(route_distribution_verified=True, episode_clock_randomized=False, ppo_preserved=True,
                native_fixture=m.get('route_command_fixture'), training_manifest_sha256=sha256(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=int, default=1, choices=range(1, 5))
    args = parser.parse_args()
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    name = f'rough_route_preflight_20260920_{args.attempt}'
    out = ROOT/'logs/rough'/name
    out.mkdir(parents=True, exist_ok=False)
    (out/'source').mkdir()
    seed = 5900 + args.attempt
    baseline = ROOT/'docs/results/rough_reference_baseline_20260920.json'
    if read(baseline)['status'] != 'completed_diagnostic':
        raise ValueError('Complete current reference/anchor evaluation first')
    job = dict(status='running', started_utc=utc_now(), stages=[], route_commands=True, seed=seed,
               scope='Native route and tilt fixtures plus 2+2 PPO/resume; all weights discarded',
               baseline=str(baseline.relative_to(ROOT)), baseline_sha256=sha256(baseline),
               source_sha256={f'scripts/{n}':sha256(ROOT/'scripts'/n) for n in SOURCES})
    save = lambda: write_json(out/'job.json', job)
    for n in SOURCES:
        shutil.copyfile(ROOT/'scripts'/n, out/'source'/n)
    save()
    try:
        previous = None
        for label, start in [('train', 0), ('resume', 2)]:
            suffix = name+'_'+label
            cmd = [PYTHON, '-B', '-u', 'scripts/train_b2w.py', '--rough_transfer', '--rough_tilt_termination',
                   '--rough_route_commands', '--headless', '--device', 'cuda:0', '--num_envs', '64',
                   '--seed', str(seed), '--max_iterations', '2', '--run_name', suffix,
                   '--reference_init', str(ANCHOR), '--pure_yaw_fraction', '.25', '--reference_update_probe',
                   '--critic_warmup_updates', '1', '--reference_drift_limit', '.25', '--rough_stage', '0']
            if previous:
                cmd += ['--resume', str(ROOT/previous['checkpoint'])]
            stage = own_child(cmd, out/label, job, save)
            stage['validation'] = previous = verify_run(suffix, 64, start, 2, seed, False)
            stage['route_validation'] = verify_route_run(ROOT/previous['training_manifest'], smoke=True)
            save()
        job['status'] = 'passed'
        return 0
    except BaseException as exc:
        job.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        return 1
    finally:
        job['finished_utc'] = utc_now()
        save()
        write_json(ROOT/'docs/results'/f'{name}.json', job)


if __name__ == '__main__':
    raise SystemExit(main())
