"""Freeze the development protocol, then execute independent local simulators."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from locomotion57_protocol import (
    ROOT, POLICIES, CHECKPOINT_SHA, TERRAINS, cases_for, protocol_manifest, sha256,
)

BASE = ROOT / 'logs/locomotion57_upstream_20260925'
CONFIG = ROOT / 'configs/locomotion57_v1_upstream_development.json'
SOURCES = ('locomotion57_protocol.py', 'eval_locomotion57_isaac.py', 'eval_locomotion57_mujoco.py')


def freeze():
    protocol = protocol_manifest()
    protocol['frozen_at_utc'] = datetime.now(timezone.utc).isoformat()
    protocol['source_sha256'] = {name: sha256(ROOT/'scripts'/name) for name in SOURCES}
    protocol['exports'] = {}
    for policy in POLICIES:
        checkpoint = ROOT/f'artifacts/upstream/2026-09-23_model_{policy}/upstream_model_{policy}.pt'
        assert sha256(checkpoint) == CHECKPOINT_SHA[policy]
        report = json.loads((BASE/f'export{policy}/report.json').read_text())
        export = report['training_export']
        assert export['checkpoint_sha256'] == CHECKPOINT_SHA[policy]
        assert export['status'] == 'passed' and export['max_abs_error'] <= 1e-5
        assert sha256(ROOT/export['export']) == export['export_sha256']
        protocol['exports'][str(policy)] = export
    if CONFIG.exists():
        raise FileExistsError(CONFIG)
    CONFIG.write_text(json.dumps(protocol, indent=2)+'\n', encoding='utf-8')
    count = sum(len(cases_for(terrain)) for terrain in TERRAINS)
    print(f'FROZEN {CONFIG} sha256={sha256(CONFIG)} cases={count} episodes={count*16*3*2}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('freeze', 'isaac', 'mujoco'))
    args = parser.parse_args()
    if args.mode == 'freeze':
        freeze()
        return
    frozen = json.loads(CONFIG.read_text())
    for name in SOURCES:
        assert sha256(ROOT/'scripts'/name) == frozen['source_sha256'][name], f'Evaluator changed: {name}'
    for export in frozen['exports'].values():
        assert sha256(ROOT/export['export']) == export['export_sha256']
    output = BASE/'development'
    output.mkdir(parents=True, exist_ok=True)
    commands = []
    if args.mode == 'isaac':
        for terrain in TERRAINS:
            commands.append((terrain, ['powershell.exe', '-NoProfile', '-File', str(ROOT/'scripts/run_local.ps1'),
                'scripts/eval_locomotion57_isaac.py', '--terrain', terrain, '--seeds', '16',
                '--output', str(output/f'isaac_{terrain}.json')]))
    else:
        commands.append(('all', [sys.executable, '-B', 'scripts/eval_locomotion57_mujoco.py',
                                 '--output-dir', str(output), '--workers', '4', '--seeds', '16']))
    for label, command in commands:
        log = output/f'{args.mode}_{label}.log'
        if log.exists():
            raise FileExistsError(log)
        print(f'RUN {args.mode} {label}', flush=True)
        with log.open('w', encoding='utf-8') as stream:
            subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
        print(f'DONE {args.mode} {label}', flush=True)


if __name__ == '__main__':
    main()
