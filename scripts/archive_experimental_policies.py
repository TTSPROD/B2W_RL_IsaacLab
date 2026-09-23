"""Archive latest saved non-smoke runs, without claiming training completion."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'policies/experimental'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify:
        manifest=json.loads((DEST/'manifest.json').read_text())
        for row in manifest['policies']:
            p=DEST/row['file']
            assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],p
            for name,digest in row['config_sha256'].items(): assert sha(p.parent/name)==digest
        print('Verified',len(manifest['policies']),'experimental snapshots')
        return
    import torch
    sources=[]
    for family in sorted((ROOT/'logs/rsl_rl').iterdir()):
        if not family.is_dir():continue
        for run in sorted(family.iterdir()):
            if not run.is_dir() or 'smoke' in run.name:continue
            points=list(run.glob('model_*.pt'))
            if not points:continue
            point=max(points,key=lambda p:int(p.stem.split('_')[-1]))
            sources.append(('local',point,Path('local')/family.name/run.name))
    for n in [5000,10000,15000,18100,19999]:
        point=ROOT/f'artifacts/upstream/2026-09-23_model_{n}/upstream_model_{n}.pt'
        sources.append(('server',point,Path('server')/f'upstream_{n}'))
    reports={str(p.relative_to(ROOT)).replace('\\','/'):p.read_text(encoding='utf-8') for p in (ROOT/'docs/results').glob('*.md')}
    rows=[]
    for location,source,subdir in sources:
        digest=sha(source)
        data=torch.load(source,map_location='cpu',weights_only=True)
        state=data['model_state_dict']
        actor_dim=int(state['actor.0.weight'].shape[1])
        action_dim=int(state['actor.6.weight'].shape[0])
        folder=DEST/subdir
        folder.mkdir(parents=True,exist_ok=True)
        target=folder/source.name
        if target.exists(): assert sha(target)==digest,target
        else: shutil.copy2(source,target)
        config_hashes={}
        for name in ['env.yaml','agent.yaml','stair_parent.json','provenance.json','server_completion.json']:
            candidates=[source.parent/name,source.parent/'params'/name]
            cfg=next((p for p in candidates if p.is_file()),None)
            if cfg:
                shutil.copy2(cfg,folder/name)
                config_hashes[name]=sha(folder/name)
        agent=(folder/'agent.yaml').read_text() if (folder/'agent.yaml').exists() else ''
        seed=re.search(r'^seed:\s*(\d+)',agent,re.M)
        row=dict(file=str(target.relative_to(DEST)).replace('\\','/'),source=str(source.relative_to(ROOT)).replace('\\','/'),
                 location=location,sha256=digest,bytes=target.stat().st_size,saved_iteration=data.get('iter'),
                 actor_inputs=actor_dim,actions=action_dim,seed=int(seed[1]) if seed else None,
                 status='experimental_not_accepted',snapshot_kind='latest_saved_non_smoke_run' if location=='local' else 'evaluated_upstream_milestone',
                 training_completion='not_inferred_from_checkpoint',evaluation_reports=[p for p,text in reports.items() if digest in text],
                 config_sha256=config_hashes)
        (folder/'archive_metadata.json').write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
        rows.append(row)
    reference=ROOT/'vendor/rl_sar/policy/b2w/robot_lab/policy.pt'
    manifest=dict(schema='b2w_experimental_policy_archive_v1',snapshot_date='2026-09-23',
        note='Not approved for deployment. Presence does not prove completed training or passing evaluation. Smoke checkpoints and intermediate periodic saves are not duplicated.',
        reference=dict(file=str(reference.relative_to(ROOT)).replace('\\','/'),sha256=sha(reference),status='external_reference_not_project_trained'),policies=rows)
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    lines=['# Экспериментальные политики — НЕ ПРИНЯТЫ', '',
        'Архив снимков на 23 сентября 2026. Ни один файл здесь не является принятым релизом или разрешением управления роботом.',
        'Сохранены последние доступные checkpoints локальных non-smoke запусков (включая остановленные/неполные), а также пять проверенных серверных milestones. Промежуточные periodic saves и smoke здесь не дублируются. Файл не доказывает успешного окончания обучения; результаты и ограничения указаны в отчётах.',
        '57→16 — текущий контракт. Исторические basevel60 snapshots имеют 60 входов: они отдельно маркированы и несовместимы с 57-входовым контроллером.',
        'Новый серверный inverse57 ещё работает; его политика в этот снимок не включена. Автоматическая доставка не публикует файлы в Git.',
        '', '[Общий статус и сравнения](../../docs/TRAINING_STATUS.md) · [Manifest с SHA-256 и происхождением](manifest.json) · [Референс rl_sar](../../vendor/rl_sar/policy/b2w/robot_lab/policy.pt)',
        '', 'Файлы — полные RSL-RL checkpoints с optimizer, не экспортированный TorchScript. Для воспроизведения нужны соответствующие конфиги, runtime и ABI. Исходные лицензии upstream находятся в vendor; архивирование не меняет правовой статус производных весов.',
        '', '| Место | Checkpoint | ABI | Seed | Сохранённая итерация |', '|---|---|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['location']} | [{r['file']}]({r['file']}) | {r['actor_inputs']}→{r['actions']} | {r['seed']} | {r['saved_iteration']} |")
    lines+=['',f"Всего {len(rows)} snapshots, {sum(r['bytes'] for r in rows)/2**20:.1f} MiB до Git compression.",
            'Проверка целостности: `python scripts/archive_experimental_policies.py --verify`.','']
    (DEST/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Archived',len(rows),'snapshots;',sum(r['bytes'] for r in rows),'bytes')

if __name__=='__main__':main()
