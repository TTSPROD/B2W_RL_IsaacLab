"""Verify the completed 500-update run and freeze its paired development test."""
import json
from pathlib import Path
import shutil

import torch
import yaml

from b2w_training_audit import differences
from fullcycle_eval_protocol import protocol_manifest
from locomotion57_protocol import ROOT, sha256
from operating57_protocol import canonical_hash

BASE = ROOT/'logs/fullcycle24499_validation_20260927'
RUN = ROOT/'logs/rsl_rl/b2w_23999_rehearsal500_local/2026-09-27_20-27-29_regression_rehearsal'
PARENT = ROOT/'policies/local/recovery_23999'
CANDIDATE = ROOT/'policies/local/rehearsal_24499'


def equal_state(a, b):
    if isinstance(a, torch.Tensor):
        return isinstance(b, torch.Tensor) and torch.equal(a, b)
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal_state(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(equal_state(x, y) for x, y in zip(a, b))
    return a == b


def main():
    progress = json.loads((RUN/'progress.json').read_text())
    assert progress['status'] == 'completed' and progress['completed_updates'] == progress['target_updates'] == 500
    assert progress['iteration'] == 24499
    assert sha256(RUN/'model_24499.pt') == 'c6c6494780d11ffc822bc08447a759e3a57945e71e6588befd8bc709cd031368'
    parent = torch.load(PARENT/'model_23999.pt', map_location='cpu', weights_only=True)
    restored = torch.load(RUN/'model_23999.pt', map_location='cpu', weights_only=True)
    assert equal_state(parent['model_state_dict'], restored['model_state_dict'])
    restored_lr = [g['lr'] for g in restored['optimizer_state_dict']['param_groups']]
    for a,b in zip(restored['optimizer_state_dict']['param_groups'],parent['optimizer_state_dict']['param_groups']):
        assert a['lr'] == min(b['lr'], 1e-5)
        a['lr'] = b['lr']
    assert equal_state(parent['optimizer_state_dict'],restored['optimizer_state_dict'])
    final = torch.load(RUN/'model_24499.pt', map_location='cpu', weights_only=True)
    assert final['iter'] == 24499 and final['infos']['additional_updates'] == 500
    assert all(v.isfinite().all() for v in final['model_state_dict'].values())
    previous_cfg = yaml.load((PARENT/'env.yaml').read_text(), Loader=yaml.BaseLoader)
    final_cfg = yaml.load((RUN/'params/env.yaml').read_text(), Loader=yaml.BaseLoader)
    changes = []
    for key in ('observations','actions','events','rewards','terminations','curriculum','sim','decimation','episode_length_s'):
        changes.extend(differences(previous_cfg[key], final_cfg[key], key))
    for key in ('actuators','init_state','spawn'):
        changes.extend(differences(previous_cfg['scene']['robot'][key],final_cfg['scene']['robot'][key],'robot.'+key))
    assert not changes, changes
    audit = {'model_state_exact':True,'adam_state_exact_except_declared_lr':True,'restored_lr':restored_lr,
             'completed_updates':500,'checkpoint_iteration':24499,'final_model_finite':True,
             'protected_config_differences':changes,'parent_sha256':sha256(PARENT/'model_23999.pt'),
             'checkpoint_sha256':sha256(RUN/'model_24499.pt')}
    (BASE/'training_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    validation = json.loads((BASE/'contract/policy-contract-export/manifest.json').read_text())['export_validation']
    assert validation['status'] == 'passed' and validation['checkpoint_iteration'] == 24499
    assert validation['max_abs_error'] == 0
    assert not CANDIDATE.exists()
    (CANDIDATE/'export').mkdir(parents=True)
    for source,target in ((RUN/'model_24499.pt',CANDIDATE/'model_24499.pt'),
            (RUN/'params/agent.yaml',CANDIDATE/'agent.yaml'),(RUN/'params/env.yaml',CANDIDATE/'env.yaml'),
            (BASE/'contract/policy-contract-export/policy.pt',CANDIDATE/'export/policy.pt'),
            (BASE/'contract/policy-contract-export/manifest.json',CANDIDATE/'export/manifest.json')):
        shutil.copyfile(source,target)
    provenance = {'checkpoint_iteration':24499,'additional_updates':500,'source_run':RUN.relative_to(ROOT).as_posix(),
        'parent_checkpoint':'policies/local/recovery_23999/model_23999.pt','parent_sha256':audit['parent_sha256'],
        'training_seed':9704,'num_envs':4096,'evaluation':'docs/experiments/24499_full_validation_20260927.md',
        'status':'evaluation_pending','hardware_approval':False,'accepted':False,'no_regression_demonstrated':False,
        'files_sha256':{p.relative_to(CANDIDATE).as_posix():sha256(p) for p in CANDIDATE.rglob('*') if p.is_file()}}
    (CANDIDATE/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    selection = {23999:'policies/local/recovery_23999/export',24499:'policies/local/rehearsal_24499/export'}
    plan = protocol_manifest({key:ROOT/value for key,value in selection.items()})
    previous = json.loads((ROOT/'logs/fullcycle23999_validation_20260927/declared_plan.json').read_text())
    for key in ('terrain_seeds','flat_seeds','flat_protocol','terrains','gates','episodes_total'):
        assert canonical_hash(plan[key]) == canonical_hash(previous[key]),key
    for name,value in (('policy_map.json',selection),('declared_plan.json',plan)):
        (BASE/name).write_text(json.dumps(value,indent=2)+'\n')
    sources = ('evaluation_policy.py','fullcycle_eval_protocol.py','eval_fullcycle_terrain.py',
        'eval_candidate_operating57_isaac.py','eval_operating57_isaac.py','operating57_protocol.py',
        'locomotion57_protocol.py','local_b2w_assets.py','b2w_runtime.py','check_policy_contract.py',
        'run_candidate_fullcycle.ps1','prepare_rehearsal500_validation.py')
    (BASE/'sources').mkdir(exist_ok=True)
    for name in sources: shutil.copyfile(ROOT/'scripts'/name,BASE/'sources'/name)
    (BASE/'source_manifest.json').write_text(json.dumps({name:sha256(BASE/'sources'/name) for name in sources},indent=2)+'\n')
    print(json.dumps({'training_audit':audit,'export':validation,'episodes':plan['episodes_total']},indent=2))


if __name__ == '__main__': main()
