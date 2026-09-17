"""Adopt this project's running seed43 and start seed44 concurrently on GPU0.

Windows process handles preserve independently observed exit codes. Only the
verified old coordinator is terminated during handoff; its trainer stays alive.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
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
from benchmark_b2w import (write_json, utc_now, sha256, device_sample, host_sample,
                           validate_checkpoints, validate_tensorboard, stop_owned_process_tree)
from run_flat_baseline import supervise


class ProcessHandle:
    def __init__(self, pid):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetExitCodeProcess.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
    def poll(self):
        state = self.kernel.WaitForSingleObject(self.handle, 0)
        if state == 258:
            return None
        if state != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value
    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def main():
    import psutil
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    output = ROOT/'logs/baselines/flat_parallel_20260917'
    old_path = ROOT/'logs/baselines/flat_3seeds_20260917/job.json'
    old = json.loads(old_path.read_text())
    if old['status'] != 'training' or old['active_seed'] != 43 or len(old['jobs']) != 1:
        raise RuntimeError('Handoff requires only seed43 active in the original queue')
    original_stage = old['jobs'][0]['stages'][0]
    coordinator = psutil.Process(old['supervisor_pid'])
    trainer = psutil.Process(original_stage['pid'])
    if coordinator.cwd().lower() != str(ROOT).lower() or trainer.cwd().lower() != str(ROOT).lower():
        raise RuntimeError('Unexpected process workspace')
    if 'scripts/run_flat_baseline.py' not in coordinator.cmdline() or 'flat_3seeds_20260917' not in coordinator.cmdline():
        raise RuntimeError('Coordinator identity mismatch')
    if trainer.cmdline()[1:] != original_stage['command'][1:] or trainer.ppid() != coordinator.pid:
        raise RuntimeError('Trainer identity/parent mismatch')
    for name, digest in old['source_sha256'].items():
        if sha256(ROOT/'scripts'/name) != digest:
            raise RuntimeError(f'Source changed before handoff: {name}')
    matches=list((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob('*_flat_3seeds_20260917_seed43/manifest.json'))
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one existing seed43 run')
    manifest43 = matches[0]
    if json.loads(manifest43.read_text())['status'] not in ('running','training'):
        raise RuntimeError('Seed43 manifest must be active')
    sample = device_sample('nvidia-smi')
    if sample['gpu_headroom_fraction'] < .55 or psutil.virtual_memory().available < 12*1024**3:
        raise RuntimeError('Insufficient measured headroom to attempt a second trainer')
    # Open the handle BEFORE changing the coordinator: preserves exit status even
    # if the process exits between subsequent polls. No trainer restart or resume.
    handle43 = ProcessHandle(trainer.pid)
    if handle43.poll() is not None:
        raise RuntimeError('Seed43 finished during handoff preflight')
    output.mkdir(parents=True, exist_ok=False)
    (output/'source').mkdir()
    for name in [*old['source_sha256'], 'parallel_flat_baseline.py']:
        shutil.copyfile(ROOT/'scripts'/name, output/'source'/name)
    shutil.copyfile(old_path, output/'original_queue.json')
    start43 = json.loads((manifest43.parent/'progress.json').read_text())
    job = {'schema_version':1,'status':'handoff_prepared','started_utc':utc_now(),
           'supervisor_pid':os.getpid(),'mode':'two independent seeds on the same GPU',
           'num_envs_per_seed':2048,'iterations_per_seed':5000,'evaluation_seed':20260917,
           'release_acceptance_complete':False,'original_queue':str(old_path.relative_to(ROOT)),
           'source_sha256':{p.name:sha256(p) for p in (output/'source').iterdir()},
           'handoff':{'old_supervisor_pid':coordinator.pid,'old_supervisor_create_time':coordinator.create_time(),
                      'trainer_pid':trainer.pid,'trainer_create_time':trainer.create_time(),
                      'progress_before':start43,'trainer_restarted':False},
           'jobs':[{'seed':43,'status':'training','training_manifest':str(manifest43.relative_to(ROOT)),
                    'stages':[{**original_stage,'adopted_without_restart':True}]}]}
    save=lambda:write_json(output/'job.json',job)
    save()
    # Windows TerminateProcess affects this verified coordinator only. Do not call
    # the recursive owned-tree stop here: the trainer must remain untouched.
    coordinator.terminate()
    coordinator.wait(timeout=10)
    if handle43.poll() is not None or not trainer.is_running():
        job.update(status='handoff_failed', error='Trainer exited during coordinator handoff')
        save()
        raise RuntimeError(job['error'])
    old.update(status='handed_off_to_parallel_coordinator',handoff_utc=utc_now(),
               replacement_job=str((output/'job.json').relative_to(ROOT)),replacement_supervisor_pid=os.getpid(),
               active_seed=None, queued_seed44_cancelled=True)
    write_json(old_path,old)
    job.update(status='starting_seed44')
    save()
    python=str(ROOT/'.venv/Scripts/python.exe')
    suffix44='flat_parallel_20260917_seed44'
    command=[python,'-B','-u','scripts/train_b2w.py','--headless','--device','cuda:0',
             '--num_envs','2048','--seed','44','--max_iterations','5000','--run_name',suffix44]
    child44 = owned44 = None
    console44 = (output/'seed44_console.log').open('w',encoding='utf-8')
    child44=subprocess.Popen(command,cwd=ROOT,stdout=console44,stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    owned44=psutil.Process(child44.pid)
    run44={'seed':44,'status':'training','stages':[{'name':'train','status':'running','started_utc':utc_now(),
           'command':command,'pid':child44.pid,'timeout_seconds':21600}]}
    job['jobs'].append(run44)
    job.update(status='parallel_training')
    save()
    started = time.monotonic()
    try:
        with (output/'resources.jsonl').open('w',encoding='utf-8') as telemetry:
            while True:
                codes=[handle43.poll(), child44.poll()]
                for run, code in zip(job['jobs'], codes):
                    if code is not None and run['status']=='training':
                        run.update(status='training_completed' if code==0 else 'training_failed')
                        run['stages'][0].update(status='completed' if code==0 else 'failed',external_exit_code=code,finished_utc=utc_now())
                        save()
                if all(code is not None for code in codes):
                    break
                record={'utc':utc_now(),'elapsed_seconds':time.monotonic()-started,
                        'seed43':host_sample(trainer,psutil),'seed44':host_sample(owned44,psutil)}
                try:
                    record.update(device_sample('nvidia-smi'))
                except Exception as exc:
                    record['telemetry_error']=str(exc)
                telemetry.write(json.dumps(record)+'\n')
                telemetry.flush()
                if time.monotonic()-started > 21600:
                    # These are both explicitly verified project-owned trainers.
                    if codes[0] is None: stop_owned_process_tree(trainer,psutil)
                    if codes[1] is None: stop_owned_process_tree(owned44,psutil)
                    raise TimeoutError('Parallel phase exceeded 6 hours')
                time.sleep(5)
        # Evaluate serially after both simulations release GPU memory.
        for run in job['jobs']:
            if run['status'] != 'training_completed':
                continue
            seed=run['seed']
            matches=[manifest43] if seed==43 else list((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob(f'*_{suffix44}/manifest.json'))
            if len(matches)!=1: raise RuntimeError('Training manifest mismatch')
            manifest_path=matches[0]
            manifest=json.loads(manifest_path.read_text())
            if manifest['status']!='completed' or manifest['starting_runner_iteration']!=0 or manifest['ending_runner_iteration']!=4999 or manifest['resume'] is not None:
                raise RuntimeError('Incomplete or non-independent training')
            run['training_manifest']=str(manifest_path.relative_to(ROOT))
            run['checkpoint_validation']=validate_checkpoints(manifest_path.parent,manifest)
            run['training_metrics']=validate_tensorboard(manifest_path.parent,manifest,5000,10)
            checkpoint=manifest_path.parent/'model_4999.pt'
            report_dir=ROOT/'logs/qualification/flat_parallel_20260917'/f'seed{seed}'
            export_report=report_dir/'export/report.json'
            stage={'name':'export'};run['stages'].append(stage)
            job['status']=run['status']='exporting';save()
            supervise([python,'-B','-u','scripts/check_policy_contract.py','--training-checkpoint',str(checkpoint),'--report',str(export_report)],output/f'seed{seed}'/'export',600,stage,save)
            export=json.loads(export_report.read_text())['training_export']
            if export['status']!='passed' or export['checkpoint_sha256']!=sha256(checkpoint):
                raise RuntimeError('Export checkpoint mismatch')
            policy=ROOT/export['export']
            if sha256(policy)!=export['export_sha256']:raise RuntimeError('Export hash mismatch')
            eval_report=report_dir/'flat100.json'
            stage={'name':'flat100'};run['stages'].append(stage)
            job['status']=run['status']='evaluating';save()
            supervise([python,'-B','-u','scripts/replay_reference_b2w.py','--suite','flat100','--num_envs','100','--seed','20260917','--policy',str(policy),'--report',str(eval_report)],output/f'seed{seed}'/'flat100',1800,stage,save)
            evaluated=json.loads(eval_report.read_text())
            if evaluated['status']!='completed' or evaluated['policy_sha256']!=export['export_sha256'] or evaluated['physics_steps_completed']!=4400:
                raise RuntimeError('Evaluation validation failed')
            run.update(status='completed',evaluation_report=str(eval_report.relative_to(ROOT)),evaluation_summary=evaluated['summary'])
            save()
        job['status']='completed_baseline_measurements' if all(run['status']=='completed' for run in job['jobs']) else 'completed_with_training_failure'
    except BaseException as exc:
        job.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        # Do not kill a healthy training run solely for a post-processing failure.
        job['remaining_training_processes']={'seed43':handle43.poll(),'seed44':child44.poll()}
        raise
    finally:
        job['finished_utc']=utc_now();save();handle43.close();console44.close()


if __name__=='__main__':
    main()
