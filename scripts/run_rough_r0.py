"""Bounded sequential Rough R0: mesh/physics, 2+2 PPO, then two 50-update benchmarks.

All resulting policies are discarded. This coordinator cannot start R1 or stairs.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import (sha256, write_json, utc_now, device_sample, host_sample,
    stop_owned_process_tree, validate_checkpoints, validate_tensorboard, resource_summary)
from b2w_rough_runtime import ANCHOR_SHA256, flat_bank_path

SOURCES = ('run_rough_r0.py', 'smoke_rough_b2w.py', 'train_b2w_desktop.py', 'b2w_rough_runtime.py',
           'b2w_rough_terrain.py', 'b2w_runtime.py', 'reference_transfer.py',
           'b2w_yaw_commands.py', 'yaw_command_sampling.py', 'benchmark_b2w.py', 'smoke_b2w_desktop.py')
PYTHON = str(ROOT/'.venv/Scripts/python.exe')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def own_child(command, directory, job, save, timeout_seconds=3600):
    import psutil
    if not 0 < timeout_seconds <= 3600:
        raise ValueError('Stage timeout must be within the registered 3600s ceiling')
    for name, digest in job['source_sha256'].items():
        if sha256(ROOT/name) != digest:
            raise RuntimeError('Frozen source changed: '+name)
    initial = device_sample('nvidia-smi')
    if initial['gpu_headroom_fraction'] < .5:
        raise RuntimeError('Requires at least 50% VRAM free before each stage')
    stage = dict(name=directory.name, status='starting', command=command, timeout_seconds=timeout_seconds,
                 started_utc=utc_now(), initial_device=initial)
    job['stages'].append(stage)
    directory.mkdir(parents=True, exist_ok=False)
    save()
    child = owned = None
    samples = []
    started = time.monotonic()
    try:
        with (directory/'console.log').open('w', encoding='utf-8') as console, (directory/'resources.jsonl').open('w') as stream:
            child = subprocess.Popen(command, cwd=ROOT, stdout=console, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            owned = psutil.Process(child.pid)
            stage.update(pid=child.pid, status='running'); save()
            while child.poll() is None:
                sample = dict(utc=utc_now(), elapsed_seconds=time.monotonic()-started,
                              **host_sample(owned, psutil), **device_sample('nvidia-smi'))
                samples.append(sample); stream.write(json.dumps(sample)+'\n'); stream.flush()
                if sample['gpu_headroom_fraction'] < .05:
                    raise RuntimeError('Whole-device VRAM headroom below 5%')
                if sample['elapsed_seconds'] > timeout_seconds:
                    raise TimeoutError('Registered stage timeout')
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        if child.returncode:
            raise RuntimeError(f'{directory.name} exited {child.returncode}; see console.log')
        stage['status'] = 'completed'
    except BaseException as exc:
        stage.update(status='failed', error=str(exc))
        if child and child.poll() is None:
            stop_owned_process_tree(owned, psutil); child.wait(timeout=10)
        raise
    finally:
        stage.update(external_exit_code=None if child is None else child.poll(),
                     elapsed_seconds=time.monotonic()-started, finished_utc=utc_now())
        if samples:
            stage['resources'] = resource_summary(samples)
        save()
    return stage


def verify_training(directory, label, count, updates, start, parent, anchor):
    import torch
    matches = list((ROOT/'logs/rsl_rl/unitree_b2w_rough_r0').glob('*_'+label+'/manifest.json'))
    if len(matches) != 1:
        raise ValueError('Expected exactly one Rough child manifest')
    path = matches[0]; manifest = read(path)
    if (manifest['status'] != 'completed' or manifest['starting_runner_iteration'] != start
            or manifest['ending_runner_iteration'] != start+updates-1 or manifest['num_envs'] != count
            or manifest['validated_contract'] != dict(actor_observations=57, critic_observations=247, actions=16)):
        raise ValueError('Rough child did not complete the registered workload/ABI')
    checkpoint = path.parent/f'model_{start+updates-1}.pt'
    saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
    state = saved['model_state_dict']
    reference = torch.jit.load(str(anchor), map_location='cpu').actor.state_dict()
    if not torch.equal(state['std'], torch.full_like(state['std'], .1)) or state['critic.0.weight'].shape[1] != 247:
        raise ValueError('Rough critic/std contract failed')
    actor_equal = all(torch.equal(state['actor.'+k], v) for k, v in reference.items())
    if actor_equal:
        raise ValueError('2+2 smoke did not exercise actor optimization')
    before_path = parent if parent else path.parent/'model_0.pt'
    before = torch.load(before_path, map_location='cpu', weights_only=True)
    if not any(not torch.equal(state[k], before['model_state_dict'][k]) for k in state if k.startswith('critic.')):
        raise ValueError('Critic did not learn')
    steps = [float(v['step']) for v in saved['optimizer_state_dict']['state'].values() if 'step' in v]
    if not steps or {float(g['lr']) for g in saved['optimizer_state_dict']['param_groups']} != {1e-4}:
        raise ValueError('Missing optimizer state or changed LR')
    if parent:
        previous_steps = [float(v['step']) for v in before['optimizer_state_dict']['state'].values() if 'step' in v]
        if max(steps) <= max(previous_steps):
            raise ValueError('Optimizer did not advance across resume')
    result = dict(training_manifest=str(path.relative_to(ROOT)), checkpoint=str(checkpoint.relative_to(ROOT)),
                  checkpoint_sha256=sha256(checkpoint), actor_equal_to_parent=actor_equal,
                  critic_changed=True, optimizer_max_step=max(steps), export_parity=manifest['export_parity'],
                  latest_rough_drift=manifest['reference_transfer']['latest_drift'],
                  latest_flat_bank_drift=manifest['flat_bank_drift'],
                  checkpoint_validation=validate_checkpoints(path.parent, manifest),
                  timings=validate_tensorboard(path.parent, manifest, updates, 0 if updates == 2 else 5))
    write_json(directory/'validated.json', result)
    return result, checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='rough_r0_20260919')
    args = parser.parse_args()
    import re
    if not re.fullmatch('[a-zA-Z0-9_-]{1,40}', args.name):
        raise ValueError('Unsafe run name')
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    # These seeds are for discarded R0 only, never development/qualification seeds.
    for path in (ROOT/'logs/rsl_rl').glob('*/*/manifest.json'):
        if read(path).get('seed') in (5700, 5701, 5702):
            raise ValueError('R0 seeds already used; register a new technical attempt')
    out = ROOT/'logs/rough'/args.name
    out.mkdir(parents=True, exist_ok=False)
    final = ROOT/'docs/results'/f'{args.name}.json'
    if final.exists():
        raise ValueError('Refusing existing result')
    verification = ROOT/'docs/results/2026-09-19-reference-qualification-verification.json'
    anchor = ROOT/'logs/qualification/flat_reference_qualification_20260919_resume1/seed54/export/policy-contract-export/policy.pt'
    parent = ROOT/read(verification)['finals']['54']['checkpoint']
    if sha256(anchor) != ANCHOR_SHA256 or sha256(parent) != read(verification)['finals']['54']['sha256']:
        raise ValueError('Qualified parent hash mismatch')
    job = dict(status='starting', started_utc=utc_now(), supervisor_pid=os.getpid(), stages=[],
               scope='R0 only; discard all weights; no R1/stairs/hardware acceptance',
               parent=str(parent.relative_to(ROOT)), parent_sha256=sha256(parent),
               anchor=str(anchor.relative_to(ROOT)), anchor_sha256=sha256(anchor),
               flat_bank_sha256=sha256(flat_bank_path()), geometry_seed=2026091970,
               seeds=[5700, 5701, 5702], training_budget_updates=[2, 2, 50, 50],
               num_envs=[64, 64, 1024, 2048], physics_smoke_steps=10000,
               source_sha256={f'scripts/{n}': sha256(ROOT/'scripts'/n) for n in SOURCES},
               protocol_sha256=sha256(ROOT/'docs/ROUGH_R0.md'), r1_permitted=False)
    save = lambda: write_json(out/'job.json', job)
    (out/'source').mkdir()
    for name in SOURCES:
        shutil.copyfile(ROOT/'scripts'/name, out/'source'/name)
    shutil.copyfile(ROOT/'docs/ROUGH_R0.md', out/'source/ROUGH_R0.md')
    save()
    try:
        from b2w_rough_terrain import geometry_fixtures
        job['geometry_fixtures'] = geometry_fixtures(); save()
        smoke_report = out/'physics.json'
        own_child([PYTHON, '-B', '-u', 'scripts/smoke_rough_b2w.py', '--headless', '--device', 'cuda:0',
                   '--policy', str(anchor), '--report', str(smoke_report)], out/'physics', job, save)
        smoke = read(smoke_report)
        if smoke['status'] != 'passed' or smoke['physics_steps_completed'] != 10000:
            raise ValueError('Rough physics smoke failed')
        job['physics_report'] = str(smoke_report.relative_to(ROOT)); save()
        previous = None
        for label, count, seed, updates, start, warmup in [('train',64,5700,2,0,1), ('resume',64,5700,2,2,1),
                                                          ('bench1024',1024,5701,50,0,1), ('bench2048',2048,5702,50,0,1)]:
            suffix = args.name+'_'+label
            command = [PYTHON, '-B', '-u', 'scripts/train_b2w_desktop.py', '--rough_r0', '--headless', '--device', 'cuda:0',
                       '--num_envs', str(count), '--seed', str(seed), '--max_iterations', str(updates), '--run_name', suffix,
                       '--reference_init', str(anchor), '--pure_yaw_fraction', '.25', '--reference_update_probe',
                       '--critic_warmup_updates', str(warmup), '--reference_drift_limit', '.25']
            parent_checkpoint = previous if start else None
            if parent_checkpoint:
                command += ['--resume', str(parent_checkpoint)]
            stage = own_child(command, out/label, job, save)
            stage['validation'], previous = verify_training(out/label, suffix, count, updates, start, parent_checkpoint, anchor)
            save()
        job.update(status='completed_runtime_tests', r0_full_gate_passed=False,
                   remaining_before_r1=['safe traversal curriculum', 'Rough route/clearance/energy evaluator',
                                        'bounded physics readback on Rough', 'Flat regression against frozen parent'],
                   policy_quality_evaluated=False)
        return 0
    except BaseException as exc:
        job.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        return 1
    finally:
        job['finished_utc'] = utc_now(); save(); write_json(final, job)


if __name__ == '__main__':
    raise SystemExit(main())
