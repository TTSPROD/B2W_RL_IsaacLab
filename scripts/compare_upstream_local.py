"""Run the fixed open comparison requested on 2026-09-23; never train policies."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'logs/upstream_comparison_18100_20260923'
ART = ROOT / 'artifacts/upstream/2026-09-23_model_18100'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--milestones', action='store_true')
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    if args.milestones:
        OUT = ROOT / 'logs/upstream_milestones_20260923'
    if args.final:
        OUT = ROOT / 'logs/upstream_final_20260923'
    OUT.mkdir(parents=True, exist_ok=True)
    models = {
        'upstream18100': ('--checkpoint', ART / 'upstream_model_18100.pt'),
        'reference': ('--policy', ROOT / 'vendor/rl_sar/policy/b2w/robot_lab/policy.pt'),
    }
    for seed in (54, 55):
        matches = list((ROOT / 'logs/rsl_rl/unitree_b2w_stair').glob(
            f'*_stair_moving_anchor10_2048_20260923_seed{seed}_full/model_422.pt'))
        assert len(matches) == 1, matches
        models[f'anchor{seed}'] = ('--checkpoint', matches[0])
    expected = {
        'upstream18100': 'cc3ff9a993d18979c8874005565ebfc7503fc7b529e80e4eb64556912dadddf7',
        'reference': '38155076408e8eccb22690c6c5be14bd1dcb9149245ca5e493308a9f6ff93b34',
        'anchor54': '2218a5d1da95605533d05dbba85283e9558d3e1d71c9753af71478a59b259182',
        'anchor55': '5495047af0aa01f757198c05e330eb8c2c4ca3b4b67cfe6b248eba831de669c7',
    }
    prefix = 'cmp18100'
    if args.milestones:
        models = {f'upstream{n}': ('--checkpoint', ROOT /
            f'artifacts/upstream/2026-09-23_model_{n}/upstream_model_{n}.pt')
            for n in (5000, 10000, 15000)}
        expected = {
            'upstream5000': '316b845412d171a77a529345d72e2ca8fc6344c3092a3e153cd5cde95867ded2',
            'upstream10000': '611dba2dfbb53f828c2a6e005a44c612970a5ca42e8f9261bb22b5f9c4659caa',
            'upstream15000': '9d97dfa997f5d759d8bbf1e63a558321fa0dbf455df27a77dd10b6d8732c654c',
        }
        prefix = 'cmpmilestones'
    if args.final:
        models = {'upstream19999': ('--checkpoint', ROOT / 'artifacts/upstream/2026-09-23_model_19999/upstream_model_19999.pt')}
        expected = {'upstream19999': 'e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc'}
        prefix = 'cmpfinal'
    sources = ['scripts/smoke_b2w.py', 'scripts/eval_stair_b2w.py',
               'scripts/eval_stair_suite.py', 'scripts/local_b2w_assets.py',
               'scripts/stair_cycle_protocol.py', 'scripts/stair_command_profile.py',
               'scripts/stair_terrain.py', 'configs/stair_eval_v3.json']
    hashes = {s: sha(ROOT / s) for s in sources}
    if args.milestones or args.final:
        previous = json.loads((ROOT / 'logs/upstream_comparison_18100_20260923/manifest.json').read_text())
        assert hashes == previous['source_sha256'], 'Evaluator differs from the 18100 comparison'
    manifest = {'models': {}, 'source_sha256': hashes,
                'protocol': 'flat1005 128x1000; rough2009/2010 level9 512x1000; open stair v3 6x128x900, brake1.2 min0.25; no held-out cases',
                'upstream_snapshot_iteration': 18100}
    if args.milestones:
        manifest.pop('upstream_snapshot_iteration')
        manifest['upstream_snapshot_iterations'] = [5000, 10000, 15000]
    if args.final:
        manifest['upstream_snapshot_iteration'] = 19999
        manifest['completed_training_updates'] = 20000
    for name, (flag, path) in models.items():
        digest = sha(path)
        assert digest == expected[name], (name, digest)
        manifest['models'][name] = {'path': str(path), 'sha256': digest, 'flag': flag}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    for name, (_, path) in models.items():
        if name.startswith('upstream'):
            (path.parent / 'provenance.json').write_text(json.dumps({
                **manifest['models'][name],
                'source_host': 'user@10.126.161.7',
                'source_run': 'upstream_b2w_20000_4gpu_20260922',
                'iteration': int(name.removeprefix('upstream')),
                'upstream_commit': '09f6a9dfdf48f32f38bb851dfa3a7d44db32b270',
                'runtime_notes': 'URDF compatibility adapter, distributed resume, debug visualization disabled',
            }, indent=2))

    def execute(name, scenario, cli):
        log = OUT / f'{name}_{scenario}.log'
        if log.exists():
            raise FileExistsError(log)
        for src, digest in hashes.items():
            assert sha(ROOT / src) == digest, f'Evaluator changed: {src}'
        cmd = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
               '-File', str(ROOT / 'scripts/run_local.ps1'), *cli]
        print('START', name, scenario, flush=True)
        start = time.time()
        with log.open('w', encoding='utf-8') as stream:
            p = subprocess.run(cmd, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        data = {'model': name, 'scenario': scenario, 'returncode': p.returncode,
                'elapsed_seconds': time.time()-start, 'log': str(log), 'command': cmd}
        (OUT / f'{name}_{scenario}.run.json').write_text(json.dumps(data, indent=2))
        assert p.returncode == 0, f'Failed: {log}'
        text = log.read_text(encoding='utf-8', errors='replace')
        if scenario != 'stairs':
            assert 'B2W_SMOKE_PASS' in text and 'B2W_SMOKE_EXCEPTION=' not in text, log
            line = re.findall(r'^POLICY_EVAL .+$', text, re.M)[-1]
            data['policy_eval'] = line
            for key in ['DYNAMICS', 'UNSAFE_TIMING', 'TERRAIN_FAMILIES']:
                matches = re.findall('^'+key+r'=(.+)$', text, re.M)
                if matches:
                    data[key.lower()] = json.loads(matches[-1])
            if scenario.startswith('rough'):
                assert 'terrain_families' in data, log
        else:
            paths = sorted((ROOT / 'logs/stair_benchmark').glob(f'{prefix}_{name}_cycle_*.json'))
            assert len(paths) == 6, paths
            data['cases'] = [json.loads(p.read_text()) for p in paths]
            for case in data['cases']:
                assert case['policy_sha256'] == expected[name]
                assert case['num_envs'] == 128 and case['horizon_policy_steps'] == 900
                assert case['suite_sha256'] == hashes['configs/stair_eval_v3.json']
            data['case_files'] = [str(p) for p in paths]
        (OUT / f'{name}_{scenario}.result.json').write_text(json.dumps(data, indent=2))
        print('DONE', name, scenario, round(data['elapsed_seconds'], 1), flush=True)
        return data

    def evaluate(name):
        flag, path = models[name]
        results = []
        results.append(execute(name, 'flat1005', ['scripts/smoke_b2w.py', flag, str(path),
            '--terrain', 'flat', '--seed', '1005', '--num-envs', '128', '--steps', '1000']))
        for seed in (2009, 2010):
            results.append(execute(name, f'rough{seed}', ['scripts/smoke_b2w.py', flag, str(path),
                '--terrain', 'rough', '--seed', str(seed), '--num-envs', '512', '--steps', '1000',
                '--reset-tilt-limit', '0.3', '--terrain-level', '9']))
        results.append(execute(name, 'stairs', ['scripts/eval_stair_suite.py', flag, str(path),
            '--label', f'{prefix}_{name}', '--config', 'configs/stair_eval_v3.json',
            '--split', 'development', '--num-envs', '128', '--horizon', '900',
            '--brake-profile', '--brake-distance', '1.2', '--brake-min-speed', '0.25']))
        return results

    combined = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(evaluate, name): name for name in models}
        for future in as_completed(pending):
            name = pending[future]
            combined[name] = future.result()
    for src, digest in hashes.items():
        assert sha(ROOT / src) == digest, f'Evaluator changed during comparison: {src}'
    (OUT / 'results.json').write_text(json.dumps(combined, indent=2))
    print('COMPARISON_COMPLETE', flush=True)

if __name__ == '__main__':
    main()
