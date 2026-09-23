"""Bounded server experiment. Only its own process groups are terminated."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import traceback

ROOT = Path('/run-output')
CODE = ROOT/'code'
EVAL = ROOT/'eval_workspace'
PARENT = ROOT/'parent/model_10000.pt'
PARENT_SHA = '611dba2dfbb53f828c2a6e005a44c612970a5ca42e8f9261bb22b5f9c4659caa'
KIT = '--ext-folder=/cache/exts --/app/extensions/registryEnabled=false --/app/settings/persistent=false'
STATUS = {}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, indent=2)+'\n')
    tmp.replace(path)

def status(phase, **extra):
    STATUS.update(phase=phase, updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra)
    write(ROOT/'status.json', STATUS)
    print(json.dumps(STATUS), flush=True)

def command(cmd, log, timeout, gpu=None):
    env = os.environ.copy()
    if gpu is not None:
        env['CUDA_VISIBLE_DEVICES'] = str(gpu)
    env['PYTHONPATH'] = '/vendor/robot_lab/source/robot_lab:'+str(CODE)+':'+str(EVAL/'scripts')
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.exists():
        raise FileExistsError(log)
    start = time.time()
    with log.open('w') as stream:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=max(1, timeout))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=25)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise TimeoutError(f'Time limit: {log}')
    write(log.with_suffix('.run.json'), dict(command=cmd, gpu=gpu, returncode=code, seconds=time.time()-start))
    if code:
        raise RuntimeError(f'Exit {code}: {log}')
    return log.read_text(errors='replace')

def train(parent, output, updates, initial, timeout, previous=None):
    output.mkdir(parents=True, exist_ok=False)
    cmd = [sys.executable, '-m', 'torch.distributed.run', '--standalone', '--nnodes=1', '--nproc_per_node=4',
           str(CODE/'train.py'), '--headless', '--distributed', '--parent', str(parent),
           '--parent-sha256', sha(parent), '--updates', str(updates), '--output', str(output), '--kit_args='+KIT]
    if initial:
        cmd.append('--initial')
    if previous:
        cmd.extend(['--previous-terrain', str(previous)])
    command(cmd, output/'console.log', timeout)
    for rank in range(4):
        proof = json.loads((output/f'audit_rank{rank}.json').read_text())
        assert proof['model_equal'] and proof['actor_inputs'] == 57 and proof['actions'] == 16
        assert (output/f'completed_rank{rank}.json').exists()
    return max(output.glob('model_*.pt'), key=lambda p:int(p.stem.split('_')[1]))

def evaluate(checkpoint, label, validation=False, deadline=None):
    dest = ROOT/'evaluations'/label
    dest.mkdir(parents=True, exist_ok=False)
    suite_path = EVAL/'configs/stair_eval_v3.json'
    suite = json.loads(suite_path.read_text())
    suite_digest = sha(suite_path)
    jobs = []
    for terrain, seed, n in [('flat', 1005, 128), ('rough', 2009, 512), ('rough', 2010, 512)]:
        if validation:
            seed += 50000
        cli = ['--checkpoint', str(checkpoint), '--terrain', terrain, '--seed', str(seed),
               '--num-envs', str(n), '--steps', '1000']
        if terrain == 'rough':
            cli += ['--reset-tilt-limit', '.3', '--terrain-level', '9']
        jobs.append((terrain+str(seed), 'smoke_b2w.py', cli, None))
    for case in suite['development']:
        seed = case['seed'] + (50000 if validation else 0)
        for direction in suite['directions']:
            name = f"{direction}_{round(case['rise_m']*100)}_{seed}"
            result = dest/(name+'.json')
            cli = ['--checkpoint', str(checkpoint), '--direction', direction, '--rise', str(case['rise_m']),
                   '--run', str(case['run_m']), '--num-steps', str(case['num_steps']), '--speed', str(case['speed_m_s']),
                   '--seed', str(seed), '--num-envs', '128', '--horizon', '900', '--cycle', '--cycle-protocol-v3',
                   '--hold-steps', '100', '--stop-speed', '.15', '--max-stop-drift', '.35', '--restart-distance', '.35',
                   '--brake-profile', '--brake-distance', '1.2', '--brake-min-speed', '.25',
                   '--suite-sha256', suite_digest, '--output', str(result)]
            jobs.append((name, 'eval_stair_b2w.py', cli, result))
    def lane(gpu, work):
        results = []
        for name, script, cli, result in work:
            timeout = min(1200, deadline-time.time()) if deadline else 1200
            text = command([sys.executable, str(CODE/'eval_bootstrap.py'), str(EVAL/'scripts'/script), *cli],
                           dest/(name+'.log'), timeout, gpu=gpu)
            if result:
                data = json.loads(result.read_text())
                assert data['schema']=='b2w_stair_eval_v3' and data['policy_sha256']==sha(checkpoint)
                assert data['num_envs']==128 and data['horizon_policy_steps']==900
                assert data['policy_actor_observation_dim']==57 and data['suite_sha256']==suite_digest
                assert sum(data[k] for k in ['success','unsafe','stop_failed','timeouts','incomplete'])==128
                results.append(dict(name=name, kind='stairs', **data))
            else:
                assert 'B2W_SMOKE_PASS' in text and 'B2W_SMOKE_EXCEPTION=' not in text
                line = re.findall(r'^POLICY_EVAL .+$', text, re.M)[-1]
                unsafe = int(re.search(r'unsafe_envs=(\d+)', line)[1])
                rms = json.loads(re.search(r'rms_vx_vy_yaw=(\[[^]]+\])', line)[1])
                assert all(math.isfinite(v) for v in rms)
                matches = re.findall(r'^TERRAIN_FAMILIES=(.+)$', text, re.M)
                results.append(dict(name=name, kind='rough' if matches else 'flat', unsafe=unsafe,
                                    rms=rms, families=json.loads(matches[-1]) if matches else None))
        return results
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(lane, 0, jobs[::2]); b=pool.submit(lane, 2, jobs[1::2])
        results = a.result()+b.result()
    rough = sorted([r for r in results if r['kind']=='rough'], key=lambda r:r['name'])
    stairs = sorted([r for r in results if r['kind']=='stairs'], key=lambda r:r['name'])
    inverse = [r['families']['pyramid_stairs_inv']['envs']-r['families']['pyramid_stairs_inv']['unsafe_envs'] for r in rough]
    summary = dict(label=label, checkpoint=str(checkpoint), sha256=sha(checkpoint), validation=validation,
        flat_safe=128-next(r['unsafe'] for r in results if r['kind']=='flat'),
        rough_safe=1024-sum(r['unsafe'] for r in rough), inverse=inverse,
        rough_gate=all(v>=97 for v in inverse) and all((f['envs']-f['unsafe_envs'])/f['envs']>=.95 for r in rough for f in r['families'].values()),
        stair_cycles=sum(r['success'] for r in stairs), stair_unsafe=sum(r['unsafe'] for r in stairs),
        stair_stop_failed=sum(r['stop_failed'] for r in stairs), stair_passage=sum(r['passage_success'] for r in stairs),
        worst_stair=min(r['success'] for r in stairs), stair_gate=all(r['success']/128>=.95 for r in stairs), results=results)
    write(dest/'summary.json', summary)
    return summary

def eligible(m, base):
    return m['flat_safe']==128 and m['rough_safe']>=base['rough_safe'] and m['stair_cycles']>=base['stair_cycles'] and m['stair_unsafe']<=base['stair_unsafe']

def score(m):
    return (m['rough_gate'], min(m['inverse']), sum(m['inverse']), m['rough_safe'], m['worst_stair'], m['stair_cycles'], -m['stair_unsafe'])

def progress(m, base):
    return m['flat_safe']==128 and m['rough_safe']>=base['rough_safe']-3 and m['stair_cycles']>=base['stair_cycles']-8 and m['stair_unsafe']<=base['stair_unsafe']+4 and (min(m['inverse'])>min(base['inverse']) or sum(m['inverse'])>=sum(base['inverse'])+2)

def package(history, selected, reason, validation, error=None):
    final = ROOT/'final'
    final.mkdir(exist_ok=True)
    source = Path(selected['checkpoint']) if selected else PARENT
    target = final/'selected_policy.pt'
    shutil.copy2(source, target)
    info = dict(reason=reason, selected_sha256=sha(target), selected_source=str(source),
                selected_is_parent=sha(target)==PARENT_SHA, validation=validation, error=error,
                history=history, selected=selected, completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    write(final/'report.json', info)
    lines = ['# Inverse57: автономное дообучение', '', f'Причина остановки: {reason}',
             f'Выбран исходный checkpoint: {info["selected_is_parent"]}',
             'Серверные показатели; предыдущие Windows-результаты не считаются парным контролем.', '',
             '| Checkpoint | Flat /128 | Rough /1024 | Inverse /102 | Cycle /768 | Unsafe | Stop failed |',
             '|---|---:|---:|---|---:|---:|---:|']
    for m in history:
        lines.append(f"| {m['label']} | {m['flat_safe']} | {m['rough_safe']} | {m['inverse']} | {m['stair_cycles']} | {m['stair_unsafe']} | {m['stair_stop_failed']} |")
    if error:
        lines += ['', 'Ошибка: '+error]
    lines += ['', 'Выбор сделан по development. Validation не используется для выбора другого кандидата.',
              'ABI 57→16; rewards/commands/actions неизменны; fixed LR 1e-4; inverse 35%; половина сред level7–9.',
              'Optimizer и actor/critic перенесены; между блоками среды перезапускаются, terrain levels сохранены по rank.',
              'Подробности validation и все исходные числа: report.json.']
    (final/'report.md').write_text('\n'.join(lines)+'\n')
    write(final/'provenance.json', dict(sha256=sha(target), parent_sha256=PARENT_SHA, inputs=57, actions=16,
                                     source=str(source), server_run=ROOT.name, selection_reason=reason))
    for name in ['env.yaml','agent.yaml']:
        src = source.parent/name
        if src.exists(): shutil.copy2(src, final/name)
    archive = ROOT/'delivery.tar.gz'
    with tarfile.open(archive.with_suffix('.tmp'), 'w:gz') as tar:
        for item in [final, ROOT/'evaluations', ROOT/'experiment.json', ROOT/'source_manifest.json']:
            if item.exists(): tar.add(item, arcname=item.relative_to(ROOT))
    archive.with_suffix('.tmp').replace(archive)
    return sha(archive)

def main():
    assert sha(PARENT)==PARENT_SHA
    for relative, digest in json.loads((ROOT/'source_manifest.json').read_text()).items():
        assert sha(ROOT/relative)==digest, relative
    budget_file=ROOT/'budget.json'
    started = json.loads(budget_file.read_text())['start_epoch'] if budget_file.exists() else time.time()
    write(budget_file, dict(start_epoch=started))
    deadline = started+15*3600
    train_deadline = started+11*3600
    write(ROOT/'experiment.json', dict(start_epoch=started, deadline_epoch=deadline, train_deadline_epoch=train_deadline,
        parent_sha256=PARENT_SHA, max_updates=8000, eval_every=500, fixed_lr=1e-4, envs_total=4096,
        validation_rough=[52009,52010], validation_flat=51005, validation_stairs=[53001,53003,53002],
        note='Validation seeds fixed before training; geometry unchanged; closed seeds 4101–4104 unused.'))
    history=[]; best=None; validation=None; reason='not_started'; error=None
    try:
        status('qualifying', deadline_epoch=deadline, training_deadline_epoch=train_deadline)
        train(PARENT, ROOT/'qualification', 2, True, 900)
        status('parent_evaluation')
        base=evaluate(PARENT, 'parent10000', deadline=train_deadline)
        history.append(base); best=base
        status('parent_evaluation_complete', baseline={k:v for k,v in base.items() if k!='results'})
        parent=PARENT; previous=None; stale=0; bad=0; improved=False
        for completed in range(500,8001,500):
            if time.time()+4200>train_deadline:
                reason='training_wallclock_budget'; break
            output=ROOT/'training'/f'updates_{completed:05d}'
            status('training', target_updates=completed, last_checkpoint=str(parent))
            parent=train(parent, output, 500, previous is None, min(4800, train_deadline-time.time()), previous)
            previous=output
            status('development_evaluation', completed_updates=completed)
            m=evaluate(parent, f'updates{completed:05d}', deadline=train_deadline)
            history.append(m)
            improved = improved or progress(m,base)
            if eligible(m,base) and score(m)>score(best):
                best=m; stale=0
            else:
                stale+=1
            regression=m['flat_safe']<128 or m['rough_safe']<base['rough_safe']-10 or m['stair_cycles']<base['stair_cycles']-24 or m['stair_unsafe']>base['stair_unsafe']+12
            bad=bad+1 if regression else 0
            write(ROOT/'history.json', history)
            status('development_evaluation_complete', latest={k:v for k,v in m.items() if k!='results'}, selected=best['label'])
            if bad>=2:
                reason='repeated_regression'; break
            if completed>=1000 and not improved:
                reason='pilot_no_measured_progress'; break
            if completed>=2000 and stale>=4:
                reason='development_plateau'; break
        else:
            reason='max_updates'
        status('validation', stop_reason=reason, selected=best['label'])
        parent_val=evaluate(PARENT, 'validation_parent', True, deadline)
        selected_val=parent_val if best['sha256']==PARENT_SHA else evaluate(Path(best['checkpoint']), 'validation_selected', True, deadline)
        validation=dict(parent=parent_val, selected=selected_val,
            accepted=best['sha256']!=PARENT_SHA and selected_val['rough_gate'] and eligible(selected_val,parent_val),
            release_gate=selected_val['rough_gate'] and selected_val['stair_gate'] and selected_val['flat_safe']==128)
    except BaseException:
        error=traceback.format_exc(); print(error, flush=True); reason='error_or_timeout'
    status('packaging', stop_reason=reason)
    archive_sha=package(history,best,reason,validation,error)
    status('failed' if error else 'complete', stop_reason=reason, archive_sha256=archive_sha,
           selected=best['label'] if best else 'parent10000', validation_accepted=bool(validation and validation['accepted']))
    return 1 if error else 0

if __name__=='__main__':
    sys.exit(main())
