"""Frozen D1.1 specification and audits; no simulator or runner hooks."""
from copy import deepcopy
from run_support import ROOT,read_json,sha256
from reset_pilot_contract import load_plan as reset_plan

SPEC_PATH=ROOT/'configs/24650_upright_schedule_ab_20261001.json'
SPEC_SHA='5dc6fa17a5f51eb6b895fc90bd8bd7d7f65fea377e2259d90279508c4ede87b6'
ARMS=('adaptive','fixed')


def load_spec():
    if sha256(SPEC_PATH)!=SPEC_SHA:raise ValueError('Frozen schedule specification changed')
    spec=read_json(SPEC_PATH)
    for group,path_key,hash_key in (
        ('basis','review','review_sha256'),('parent','checkpoint','sha256'),
        ('training','standard_train','standard_train_sha256'),
        ('common_mdp','basis_recipe','basis_recipe_sha256'),
        ('common_mdp','executed_upright_env','executed_upright_env_sha256')):
        d=spec[group]
        if sha256(ROOT/d[path_key])!=d[hash_key]:raise ValueError('Schedule input changed: '+path_key)
    for name in ('agent','env'):
        if sha256(ROOT/f'policies/local/core_24650/{name}.yaml')!=spec['parent'][name+'_sha256']:
            raise ValueError('Parent config changed')
    t=spec['training']
    if (t['seed'],t['num_envs'],t['updates_per_arm'],t['steps_per_update'])!=(9911,4096,300,24):
        raise ValueError('Unexpected schedule budget/seed')
    return spec


def load_plan():
    spec=load_spec();plan=deepcopy(reset_plan());t=spec['training']
    plan.update(seed=t['seed'],num_envs=t['num_envs'],updates=t['updates_per_arm'],
        preflight_steps=spec['preflight']['policy_steps'],
        evaluation_policies=['24650','scheduleadaptive_24949','schedulefixed_24949'],
        experiment='upright_native_schedule_ab',specification_sha256=SPEC_SHA)
    # "adaptive" here names the PPO schedule; target terrain curriculum stays fixed.
    plan['arms']={arm:{**deepcopy(plan['arms']['upright']),'adaptive':False} for arm in ARMS}
    return plan


def audit_agent(agent,arm,seed=9911):
    if arm not in ARMS:raise ValueError('Unknown schedule arm')
    spec=load_spec();expected=deepcopy(spec['common_algorithm_config']);expected['schedule']=arm
    if (agent['algorithm']!=expected or agent['policy']!=spec['common_policy_config']
        or agent['class_name']!='OnPolicyRunner' or agent['num_steps_per_env']!=24
        or agent['max_iterations']!=300 or agent['seed']!=seed or agent['clip_actions'] is not None):
        raise ValueError('Undeclared agent/algorithm difference')


def preflight_decision(results):
    reasons=[]
    from b2w_core_stage3_sampling import build_banks
    banks=build_banks(load_plan())
    for arm in ARMS:
        r=results[arm];d=r['reset_diagnostics']
        if (r.get('status')!='completed' or r.get('updates')!=0 or r.get('policy_steps')!=3600
            or not all(r.get(k) for k in ('parent_state_exact','adam_state_exact','terminal_overrides_timeout'))):
            reasons.append(arm+': incomplete restore/terminal preflight')
        if any(d['initial_invalid'].values()) or d['stale_contact_resets']:
            reasons.append(arm+': invalid initial state/contact buffer')
        for name,bank in banks.items():
            c=r['coverage'][name]
            zeros=[(i,k) for i,case in enumerate(bank) for k,s in enumerate(case['segments'])
                   if s['seconds']>=12 and not any(s['command'])]
            if (not any(sum(row[1:]) for row in c['segment_attempts']) or
                not any(c['segment_completions'][i][k] for i,k in zeros)):
                reasons.append(arm+'/'+name+': missing noninitial/long zero coverage')
    if (results['adaptive']['runtime']!=results['fixed']['runtime'] or
        results['adaptive']['runner_source_sha256']!=results['fixed']['runner_source_sha256']):
        reasons.append('Preflight runtime drift')
    return {'train_allowed':not reasons,'reasons':reasons,'updates':0,'automatic_promotion':False}


def decision(records):
    from run_reset_pilot import retention_decision
    spec=load_spec();out=retention_decision(records,load_plan());m=out['metrics']
    b=m['schedulefixed_24949'];a=m['scheduleadaptive_24949']
    reasons=out['reasons']
    for cell,floor in spec['retention']['per_cell_success_minimum'].items():
        if b['cells'].get(cell,0)<floor:reasons.append(cell+': below frozen parent floor')
    for axis,floor in spec['retention']['observed_parent_response_floor'].items():
        if b['targets'][axis] is None or b['targets'][axis]<floor:
            reasons.append(axis+': below frozen parent floor')
    def descent_success(row):return sum(v for k,v in row['cells'].items() if k.startswith('stairs_down'))
    def progress(policy):
        rows=[r['terrain_exposure']['progress_ratio'] for r in records
              if str(r['policy'])==policy and r['terrain']=='stairs_down_18' and r['case']=='stop_restart_0.5']
        if len(rows)!=5:raise ValueError('Incomplete tempo evidence')
        return sum(rows)/len(rows)
    gain=descent_success(b)-descent_success(a)
    tempo=progress('schedulefixed_24949')-progress('scheduleadaptive_24949')
    out.update(retention_pass=not reasons,hypothesis_supported=not reasons and (gain>=2 or tempo>=.05),
        descent_success_gain=gain,descent_stop_restart_progress_gain=tempo,
        automatic_budget_extension=False)
    return out
