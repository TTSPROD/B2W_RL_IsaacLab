"""Sequential independent Flat seeds with bounded jobs, export and held-out evaluation.

Uses only the dedicated local project. A failed quality threshold is a measured
baseline outcome; process/finite/hash failures stop the queue. No robot IO.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import (write_json, sha256, utc_now, host_sample, device_sample,
                           stop_owned_process_tree, validate_checkpoints, validate_tensorboard)


def supervise(command, directory, timeout_seconds, stage, save):
    import psutil
    directory.mkdir(parents=True, exist_ok=False)
    stage.update(status='starting', started_utc=utc_now(), command=command, timeout_seconds=timeout_seconds)
    save()
    child = owned = None
    started = time.monotonic()
    try:
        with (directory/'console.log').open('w', encoding='utf-8') as console, (directory/'resources.jsonl').open('w', encoding='utf-8') as resources:
            child = subprocess.Popen(command, cwd=ROOT, stdout=console, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            owned = psutil.Process(child.pid)
            stage.update(status='running', pid=child.pid)
            save()
            while child.poll() is None:
                sample = {'utc': utc_now(), 'elapsed_seconds':time.monotonic()-started, **host_sample(owned, psutil)}
                try:
                    sample.update(device_sample('nvidia-smi'))
                except Exception as exc:
                    sample['telemetry_error'] = str(exc)
                resources.write(json.dumps(sample)+'\n')
                resources.flush()
                if sample['elapsed_seconds'] > timeout_seconds:
                    raise TimeoutError(f'Owned {stage["name"]} job exceeded its timeout')
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        stage['external_exit_code'] = child.returncode
        if child.returncode != 0:
            raise RuntimeError(f'{stage["name"]} exited {child.returncode}')
        stage['status'] = 'completed'
    except BaseException as exc:
        stage.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        if child is not None and child.poll() is None:
            stop_owned_process_tree(owned, psutil)
            child.wait(timeout=10)
        if child is not None:
            stage['external_exit_code'] = child.returncode
        raise
    finally:
        stage.update(finished_utc=utc_now(), wall_seconds=time.monotonic()-started)
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', nargs='+', type=int, default=[43,44])
    parser.add_argument('--iterations', type=int, default=5000)
    parser.add_argument('--num_envs', type=int, default=2048)
    parser.add_argument('--evaluation_seed', type=int, default=20260917)
    parser.add_argument('--name', required=True)
    args=parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds) or any(s < 0 for s in args.seeds):
        parser.error('Seeds must be distinct nonnegative integers')
    if args.iterations <= 10 or args.num_envs != 2048 or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.name):
        parser.error('Requires >10 updates, qualified 2048 environments and a safe run name')
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA']='YES'
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    if os.environ.get('CUDA_VISIBLE_DEVICES','0') != '0':
        raise ValueError('Requires local GPU 0')
    # Existing qualification is evidence for this exact project/runtime, not other jobs.
    pilot=json.loads((ROOT/'logs/pilots/flat_seed42_20260917/job.json').read_text())
    if pilot['external_exit_code'] != 0 or pilot['status'] != 'completed_pending_policy_evaluation':
        raise ValueError('First pilot must have completed and passed integrity validation')
    evaluation=json.loads((ROOT/'logs/qualification/flat_seed42_final/flat100.json').read_text())
    exits=json.loads((ROOT/'logs/qualification/flat_seed42_final/external_exits.json').read_text())
    if evaluation['status'] != 'completed' or exits['flat100'] != 0:
        raise ValueError('The first policy must have a completed evaluation with external exit 0')
    output=ROOT/'logs/baselines'/args.name
    output.mkdir(parents=True, exist_ok=False)
    job={'schema_version':1, 'status':'starting', 'started_utc':utc_now(), 'supervisor_pid':os.getpid(),
         'arguments':vars(args), 'jobs':[], 'scope':'independent seed replication, unchanged upstream Flat rewards/PPO',
         'first_seed_quality_thresholds_met':evaluation['summary']['single_policy_flat_thresholds_met'],
         'release_acceptance_complete':False,
         'seed42_comparability_note':'seed42 used 210 benchmark updates plus optimizer resume; seeds here run from scratch without that simulator/RNG restart.'}
    source_names=['train_b2w_desktop.py','b2w_runtime.py','check_policy_contract.py','replay_reference_b2w.py','check_stand_b2w.py','flat_evaluation.py','run_flat_baseline.py','benchmark_b2w.py','smoke_b2w_desktop.py']
    (output/'source').mkdir()
    job['source_sha256']={}
    for name in source_names:
        shutil.copyfile(ROOT/'scripts'/name, output/'source'/name)
        job['source_sha256'][name]=sha256(ROOT/'scripts'/name)
    save=lambda:write_json(output/'job.json',job)
    save()
    python=str(ROOT/'.venv/Scripts/python.exe')
    try:
        for seed in args.seeds:
            for name,digest in job['source_sha256'].items():
                if sha256(ROOT/'scripts'/name) != digest:
                    raise RuntimeError(f'Queued source changed: {name}; refusing unrecorded code')
            suffix=f'{args.name}_seed{seed}'
            if len(suffix)>64:
                raise ValueError('Training suffix too long')
            run={'seed':seed,'status':'training','stages':[]}
            job['jobs'].append(run)
            job.update(status='training',active_seed=seed)
            stage={'name':'train'}
            run['stages'].append(stage)
            command=[python,'-B','-u','scripts/train_b2w_desktop.py','--headless','--device','cuda:0','--num_envs',str(args.num_envs), '--seed',str(seed),'--max_iterations',str(args.iterations),'--run_name',suffix]
            supervise(command, output/f'seed{seed}'/'train', 21600, stage,save)
            matches=list((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob(f'*_{suffix}/manifest.json'))
            if len(matches)!=1:
                raise RuntimeError('Expected exactly one training manifest')
            manifest_path=matches[0]
            manifest=json.loads(manifest_path.read_text())
            if manifest['status']!='completed' or manifest['starting_runner_iteration']!=0 or manifest['ending_runner_iteration']!=args.iterations-1 or manifest['resume'] is not None:
                raise RuntimeError('Incomplete or non-independent training run')
            run['training_manifest']=str(manifest_path.relative_to(ROOT))
            run['checkpoint_validation']=validate_checkpoints(manifest_path.parent,manifest)
            run['training_metrics']=validate_tensorboard(manifest_path.parent,manifest,args.iterations,10)
            checkpoint=manifest_path.parent/f'model_{args.iterations-1}.pt'
            report_dir=ROOT/'logs/qualification'/args.name/f'seed{seed}'
            export_report=report_dir/'export/report.json'
            stage={'name':'export'}
            run['stages'].append(stage)
            job['status']=run['status']='exporting'
            supervise([python,'-B','-u','scripts/check_policy_contract.py','--training-checkpoint',str(checkpoint),'--report',str(export_report)],output/f'seed{seed}'/'export',600,stage,save)
            export=json.loads(export_report.read_text())['training_export']
            if export['status']!='passed' or export['checkpoint_sha256']!=sha256(checkpoint):
                raise RuntimeError('Export validation mismatch')
            policy=ROOT/export['export']
            if sha256(policy)!=export['export_sha256']:
                raise RuntimeError('Export file hash mismatch')
            eval_report=report_dir/'flat100.json'
            stage={'name':'flat100'}
            run['stages'].append(stage)
            job['status']=run['status']='evaluating'
            supervise([python,'-B','-u','scripts/replay_reference_b2w.py','--suite','flat100','--num_envs','100','--seed',str(args.evaluation_seed),'--policy',str(policy),'--report',str(eval_report)],output/f'seed{seed}'/'flat100',1800,stage,save)
            evaluated=json.loads(eval_report.read_text())
            if evaluated['status']!='completed' or evaluated['policy_sha256']!=export['export_sha256'] or evaluated['physics_steps_completed']!=4400:
                raise RuntimeError('Evaluation incomplete or policy hash mismatch')
            run.update(status='completed',evaluation_report=str(eval_report.relative_to(ROOT)), evaluation_summary=evaluated['summary'])
            save()
        job.update(status='completed_baseline_measurements',active_seed=None)
    except BaseException as exc:
        job.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        job['finished_utc']=utc_now()
        save()


if __name__=='__main__':
    main()
