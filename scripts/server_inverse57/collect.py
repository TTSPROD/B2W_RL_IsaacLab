"""Windows delivery worker; keeps the machine awake only while awaiting results."""
import ctypes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
HOST = 'user@10.126.161.7'
REMOTE = '/home/user/B2W_RL_IsaacLab_Server/logs/inverse57_4gpu_20260923'
OUT = ROOT/'artifacts/upstream/inverse57_4gpu_20260923'

def shell(args, timeout=120):
    return subprocess.check_output(args, timeout=timeout, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        while True:
            try:
                state=json.loads(shell(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15', HOST, f'cat {REMOTE}/status.json']))
                (OUT/'server_status.json').write_text(json.dumps(state,indent=2))
                print(state['phase'],state.get('completed_updates'),flush=True)
                if state['phase'] in ('complete','failed'):
                    break
            except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
                print('Awaiting SSH/status:',str(exc),flush=True)
            time.sleep(180)
        archive=OUT/'delivery.tar.gz'
        shell(['scp','-o','BatchMode=yes',f'{HOST}:{REMOTE}/delivery.tar.gz',str(archive)],timeout=1200)
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==state['archive_sha256']
        with tarfile.open(archive) as tar:
            for m in tar.getmembers():
                path=(OUT/m.name).resolve()
                assert path.is_relative_to(OUT.resolve()) and not m.issym() and not m.islnk()
            tar.extractall(OUT, filter='data')
        report=json.loads((OUT/'final/report.json').read_text())
        checkpoint=OUT/'final/selected_policy.pt'
        assert hashlib.sha256(checkpoint.read_bytes()).hexdigest()==report['selected_sha256']
        if not report['selected_is_parent']:
            logs=ROOT/'logs/inverse57_local_verification_20260923'
            logs.mkdir(exist_ok=True)
            for kind,seed,n in [('flat',1005,128),('rough',2009,512),('rough',2010,512)]:
                cli=['scripts/smoke_b2w.py','--checkpoint',str(checkpoint),'--terrain',kind,'--seed',str(seed),'--num-envs',str(n),'--steps','1000']
                if kind=='rough': cli+=['--terrain-level','9','--reset-tilt-limit','.3']
                run(cli,logs/f'{kind}{seed}.log')
            run(['scripts/eval_stair_suite.py','--checkpoint',str(checkpoint),'--label','inverse57_final_20260923',
                '--config','configs/stair_eval_v3.json','--split','development','--num-envs','128','--horizon','900',
                '--brake-profile','--brake-distance','1.2','--brake-min-speed','.25'],logs/'stairs.log')
            stairs=[json.loads(p.read_text()) for p in (ROOT/'logs/stair_benchmark').glob('inverse57_final_20260923_cycle_*.json')]
            assert len(stairs)==6 and all(s['policy_sha256']==report['selected_sha256'] for s in stairs)
            local=dict(stair_cycles=sum(s['success'] for s in stairs),stair_unsafe=sum(s['unsafe'] for s in stairs),
                       stair_stop_failed=sum(s['stop_failed'] for s in stairs))
            for kind,seed,n in [('flat',1005,128),('rough',2009,512),('rough',2010,512)]:
                text=(logs/f'{kind}{seed}.log').read_text(errors='replace')
                line=re.findall(r'^POLICY_EVAL .+$',text,re.M)[-1]
                local[kind+str(seed)+'_safe']=n-int(re.search(r'unsafe_envs=(\d+)',line)[1])
            (OUT/'local_verification.json').write_text(json.dumps(local,indent=2))
            with (OUT/'final/report.md').open('a',encoding='utf-8') as f:
                f.write('\n## Локальная перепроверка выбранной модели\n\n'+json.dumps(local,ensure_ascii=False)+'\n')
        else:
            (OUT/'local_verification.json').write_text(json.dumps(dict(skipped=True,reason='Selected unchanged parent10000; prior local nine-case evaluation exists.')))
        (OUT/'DELIVERY_COMPLETE.json').write_text(json.dumps(dict(completed=time.time(),sha256=report['selected_sha256'],server_phase=state['phase'])))
        print('DELIVERY_COMPLETE',flush=True)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

def run(cli, log):
    if log.exists(): raise FileExistsError(log)
    with log.open('w',encoding='utf-8') as stream:
        p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/run_local.ps1'),*cli],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=1800,creationflags=subprocess.CREATE_NO_WINDOW)
    if p.returncode: raise RuntimeError(str(log))
    if cli[0].endswith('smoke_b2w.py'):
        text=log.read_text(errors='replace')
        assert 'B2W_SMOKE_PASS' in text and 'B2W_SMOKE_EXCEPTION=' not in text

if __name__=='__main__':
    try:
        main()
    except BaseException:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'DELIVERY_ERROR.txt').write_text(traceback.format_exc())
        raise
