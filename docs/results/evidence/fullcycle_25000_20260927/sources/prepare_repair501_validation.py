"""Audit the completed 501-update run and freeze 24499/25000 evaluation."""
import json
import shutil

import torch
import yaml

from b2w_training_audit import differences
from prepare_rehearsal500_validation import equal_state
from fullcycle_eval_protocol import protocol_manifest
from locomotion57_protocol import ROOT,sha256
from operating57_protocol import canonical_hash

BASE=ROOT/'logs/fullcycle25000_validation_20260927'
RUN=ROOT/'logs/rsl_rl/b2w_24499_repair501_local/2026-09-27_21-35-40_zero_safety_repair'
PARENT=ROOT/'policies/local/rehearsal_24499'
CANDIDATE=ROOT/'policies/local/repair_25000'


def main():
    progress=json.loads((RUN/'progress.json').read_text())
    assert progress['status']=='completed' and progress['completed_updates']==progress['target_updates']==501
    assert progress['iteration']==25000
    assert sha256(RUN/'model_25000.pt')=='a8a51a251aea2fc79c627a0df24f0dca31b39d6d81f454777a89a57ea28406ba'
    parent=torch.load(PARENT/'model_24499.pt',map_location='cpu',weights_only=True)
    restored=torch.load(RUN/'model_24499.pt',map_location='cpu',weights_only=True)
    assert equal_state(parent['model_state_dict'],restored['model_state_dict'])
    for a,b in zip(restored['optimizer_state_dict']['param_groups'],parent['optimizer_state_dict']['param_groups']):
        assert a['lr']==min(b['lr'],5e-6)
        a['lr']=b['lr']
    assert equal_state(parent['optimizer_state_dict'],restored['optimizer_state_dict'])
    final=torch.load(RUN/'model_25000.pt',map_location='cpu',weights_only=True)
    assert final['iter']==25000 and final['infos']['additional_updates']==501
    assert all(v.isfinite().all() for v in final['model_state_dict'].values())
    old=yaml.load((PARENT/'env.yaml').read_text(),Loader=yaml.BaseLoader)
    new=yaml.load((RUN/'params/env.yaml').read_text(),Loader=yaml.BaseLoader)
    changes=[]
    for key in ('observations','actions','events','rewards','terminations','curriculum','commands','sim','decimation','episode_length_s'):
        changes.extend(differences(old[key],new[key],key))
    for key in ('actuators','init_state','spawn'):
        changes.extend(differences(old['scene']['robot'][key],new['scene']['robot'][key],'robot.'+key))
    changes.extend(differences(old['scene']['terrain']['terrain_generator'],new['scene']['terrain']['terrain_generator'],'terrain_generator'))
    declared=json.loads((RUN/'repair_config_audit.json').read_text())
    assert declared['status']=='passed' and changes==declared['declared_changes']
    validation=json.loads((BASE/'contract/policy-contract-export/manifest.json').read_text())['export_validation']
    assert validation['status']=='passed' and validation['checkpoint_iteration']==25000 and validation['max_abs_error']==0
    audit={'model_state_exact':True,'adam_state_exact_except_declared_lr':True,'completed_updates':501,
        'checkpoint_iteration':25000,'final_model_finite':True,'declared_config_changes':changes,
        'unexpected_config_changes':[],'parent_sha256':sha256(PARENT/'model_24499.pt'),
        'checkpoint_sha256':sha256(RUN/'model_25000.pt'),
        'training_audit_sha256':sha256(RUN/'repair_config_audit.json')}
    (BASE/'training_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    assert not CANDIDATE.exists()
    (CANDIDATE/'export').mkdir(parents=True)
    for source,target in ((RUN/'model_25000.pt',CANDIDATE/'model_25000.pt'),
        (RUN/'params/agent.yaml',CANDIDATE/'agent.yaml'),(RUN/'params/env.yaml',CANDIDATE/'env.yaml'),
        (BASE/'contract/policy-contract-export/policy.pt',CANDIDATE/'export/policy.pt'),
        (BASE/'contract/policy-contract-export/manifest.json',CANDIDATE/'export/manifest.json')):
        shutil.copyfile(source,target)
    provenance={'checkpoint_iteration':25000,'additional_updates':501,'source_run':RUN.relative_to(ROOT).as_posix(),
        'parent_checkpoint':'policies/local/rehearsal_24499/model_24499.pt','parent_sha256':audit['parent_sha256'],
        'training_seed':9705,'num_envs':4096,'evaluation':'docs/experiments/25000_full_validation_20260927.md',
        'status':'evaluation_pending','hardware_approval':False,'accepted':False,'no_regression_demonstrated':False,
        'files_sha256':{p.relative_to(CANDIDATE).as_posix():sha256(p) for p in CANDIDATE.rglob('*') if p.is_file()}}
    (CANDIDATE/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    selection={24499:'policies/local/rehearsal_24499/export',25000:'policies/local/repair_25000/export'}
    plan=protocol_manifest({key:ROOT/value for key,value in selection.items()})
    previous=json.loads((ROOT/'logs/fullcycle24499_validation_20260927/declared_plan.json').read_text())
    for key in ('terrain_seeds','flat_seeds','flat_protocol','terrains','gates','episodes_total'):
        assert canonical_hash(plan[key])==canonical_hash(previous[key]),key
    for name,value in (('policy_map.json',selection),('declared_plan.json',plan)):
        (BASE/name).write_text(json.dumps(value,indent=2)+'\n')
    sources=('evaluation_policy.py','fullcycle_eval_protocol.py','eval_fullcycle_terrain.py',
        'eval_candidate_operating57_isaac.py','eval_operating57_isaac.py','operating57_protocol.py',
        'locomotion57_protocol.py','local_b2w_assets.py','b2w_runtime.py','check_policy_contract.py',
        'run_candidate_fullcycle.ps1','prepare_repair501_validation.py','prepare_rehearsal500_validation.py')
    (BASE/'sources').mkdir(exist_ok=True)
    for name in sources: shutil.copyfile(ROOT/'scripts'/name,BASE/'sources'/name)
    (BASE/'source_manifest.json').write_text(json.dumps({name:sha256(BASE/'sources'/name) for name in sources},indent=2)+'\n')
    print(json.dumps({'completed_updates':501,'checkpoint_iteration':25000,'export':validation,'episodes':plan['episodes_total']},indent=2))


if __name__=='__main__': main()
