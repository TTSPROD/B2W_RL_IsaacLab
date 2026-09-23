"""Registered T0: discard64 2+2, then sequential teacher67/68 1024x100.

Technical completion is not Rough, route, stairs or hardware acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import traceback

from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import sha256, write_json, utc_now
from run_rough_r0 import own_child
from run_reference_transfer import assert_idle_project

PYTHON = str(ROOT / '.venv/Scripts/python.exe')
SOURCES = (
    'run_locomotion_teacher_pilot.py', 'train_locomotion_teacher.py',
    'b2w_locomotion_teacher.py', 'b2w_rough_runtime.py', 'b2w_rough_terrain.py',
    'b2w_runtime.py', 'b2w_yaw_commands.py', 'yaw_command_sampling.py',
    'reference_transfer.py', 'train_b2w_desktop.py', 'benchmark_b2w.py',
    'run_rough_r0.py', 'run_reference_transfer.py', 'smoke_b2w_desktop.py',
)


def verify_output(output, *, seed, count, start, updates):
    import torch
    manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    if (manifest['status'] != 'completed' or manifest['seed'] != seed
            or manifest['num_envs'] != count or manifest['starting_runner_iteration'] != start
            or manifest['ending_runner_iteration'] != start+updates-1
            or manifest['export_parity']['max_abs_error'] > 1e-5):
        raise ValueError('Incomplete teacher child')
    checkpoint = output/f'model_{start+updates-1}.pt'
    saved = torch.load(checkpoint, map_location='cpu', weights_only=False)
    info = saved.get('infos', {}).get('teacher_pilot', {})
    if (info.get('seed') != seed or info.get('num_envs') != count
            or manifest['requested_updates'] != updates
            or manifest['checkpoint_sha256'] != sha256(checkpoint)):
        raise ValueError('Workload/provenance/checkpoint hash mismatch')
    state = saved['model_state_dict']
    if saved['iter'] != start+updates-1:
        raise ValueError('Wrong final checkpoint iteration')
    if state['actor.0.weight'].shape != (512, 247) or state['critic.0.weight'].shape != (512, 247):
        raise ValueError('Wrong teacher ABI')
    if not all(bool(torch.isfinite(t).all()) for t in state.values()):
        raise ValueError('Nonfinite teacher checkpoint')
    steps = [float(x['step']) for x in saved['optimizer_state_dict']['state'].values() if 'step' in x]
    if not steps or not bool((state['std'] > 0).all()):
        raise ValueError('Missing optimizer or invalid exploration')
    if float(state['actor.0.weight'][:,57:].norm()) <= 0:
        raise ValueError('New teacher input columns did not learn')
    progress = json.loads((output/'progress.json').read_text(encoding='utf-8'))
    if progress['iteration'] != start+updates-1:
        raise ValueError('Wrong progress iteration')
    return dict(seed=seed, num_envs=count, updates=updates,
        checkpoint=str(checkpoint.relative_to(ROOT)), checkpoint_sha256=sha256(checkpoint),
        manifest=str((output/'manifest.json').relative_to(ROOT)), manifest_sha256=sha256(output/'manifest.json'),
        optimizer_max_step=max(steps), extra_input_weight_norm=float(state['actor.0.weight'][:,57:].norm()),
        std_range=[float(state['std'].min()),float(state['std'].max())],
        policy_quality_accepted=False)


def main():
    raise RuntimeError("Teacher247 rejected by user: actor ABI must remain57->16; do not restart this historical pilot")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=range(1,10), default=1)
    parser.add_argument('--smoke_only', action='store_true')
    args = parser.parse_args()
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    assert_idle_project(__file__)
    name = f'locomotion_teacher_t0_20260920_{args.attempt}'
    out = ROOT/'logs/teacher'/name
    published = ROOT/'docs/results'/f'{name}.json'
    if out.exists() or published.exists():
        raise ValueError('Attempt exists; refusing overwrite')
    # Development seeds cannot be silently retried after a partial pilot.
    if not args.smoke_only:
        for path in (ROOT/'logs/teacher').glob('*/seed*/manifest.json'):
            if json.loads(path.read_text(encoding='utf-8')).get('seed') in (67,68):
                raise ValueError('Development seed already used; register a new recipe')
    out.mkdir(parents=True)
    protocol = ROOT/'docs/ROUGH_TEACHER_REDESIGN.md'
    files = [ROOT/'scripts'/n for n in SOURCES] + [protocol,ROOT/'vendor/manifest.json']
    frozen = {str(p.relative_to(ROOT)).replace('\\','/'):sha256(p) for p in files}
    snapshots = out/'source';snapshots.mkdir()
    for path in files:
        shutil.copyfile(path,snapshots/path.name)
    job = dict(status='running',started_utc=utc_now(),supervisor_pid=os.getpid(),
        stages=[],source_sha256=frozen,protocol_sha256=sha256(protocol),
        seeds=[] if args.smoke_only else [67,68],
        technical_seed=6700+args.attempt,smoke_only=args.smoke_only,
        max_training_transitions=6144+(0 if args.smoke_only else 4915200),
        scope='T0 architecture pilot: fixedlevel0 teacher247; no quality acceptance or automatic continuation',
        policy_quality_accepted=False,automatic_extension=False)
    def save():
        write_json(out/'job.json',job)
        write_json(published,job)
    save()
    previous = None
    try:
        schedule=[('smoke_train',6700+args.attempt,64,2,1,0),('smoke_resume',6700+args.attempt,64,2,1,2)]
        if not args.smoke_only:
            schedule += [('seed67',67,1024,100,25,0),('seed68',68,1024,100,25,0)]
        for label,seed,count,updates,warmup,start in schedule:
            output=out/label
            command=[PYTHON,'-B','-u','scripts/train_locomotion_teacher.py',
                '--output',str(output),'--seed',str(seed),'--num_envs',str(count),
                '--updates',str(updates),'--warmup',str(warmup),'--headless','--device','cuda:0']
            if label=='smoke_resume':
                command += ['--resume',str(ROOT/previous['checkpoint'])]
            if count==1024:
                command += ['--probe_steps','1000']
            stage=own_child(command,out/(label+'_process'),job,save)
            result=verify_output(output,seed=seed,count=count,start=start,updates=updates)
            if label=='smoke_resume' and result['optimizer_max_step']<=previous['optimizer_max_step']:
                raise ValueError('Optimizer did not advance on resume')
            stage['validation']=result;previous=result;save()
        job['status']='completed_technical' if args.smoke_only else 'completed_pilot'
        return 0
    except BaseException as exc:
        job.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        return 1
    finally:
        job['finished_utc']=utc_now();save()


if __name__=='__main__':
    raise SystemExit(main())
