"""Same upright task; only native algorithm.schedule differs between arms."""
import os
from copy import deepcopy
from pathlib import Path
import yaml
import b2w_reset_pilot_cfg as baseline
from schedule_pilot_contract import load_plan,load_spec,audit_agent
from run_support import ROOT,read_json,write_json

PLAN=load_plan()
ARM=os.environ['B2W_SCHEDULE_ARM']


class ScheduleVelocityCommand(baseline.ResetVelocityCommand):
    plan=PLAN
    training_profile={**PLAN,'arm':ARM,'adaptive':False}


def env_config():
    cfg=baseline.env_config()
    cfg.commands.base_velocity.class_type=ScheduleVelocityCommand
    cfg.seed=PLAN['seed']
    return cfg


def agent_config():
    cfg=baseline.agent_config()
    cfg.seed=PLAN['seed'];cfg.algorithm.schedule=ARM
    cfg.experiment_name=f'b2w_24650_schedule_{ARM}_{PLAN["seed"]}'
    audit_agent(cfg.to_dict(),ARM)
    if os.environ.get('B2W_RESET_OUTPUT'):
        write_json(Path(os.environ['B2W_RESET_OUTPUT'])/'agent_audit.json',
            {'status':'passed','arm':ARM,'schedule':ARM,'seed':PLAN['seed'],
             'policy':cfg.to_dict()['policy'],'algorithm':cfg.to_dict()['algorithm']})
    return cfg


def audit_environment(cfg,output):
    # The original audit proves robot/ABI/rewards/events unchanged from parent,
    # with the declared upright reset and common safety adapter only.
    baseline.audit_environment(cfg,output)
    from b2w_training_audit import differences
    folder=Path(output)
    current=yaml.load((folder/'reset_environment.yaml').read_text(),Loader=yaml.BaseLoader)
    spec=load_spec();expected=yaml.load((ROOT/spec['common_mdp']['executed_upright_env']).read_text(),Loader=yaml.BaseLoader)
    current=deepcopy(current);expected=deepcopy(expected)
    for d in (current,expected):
        for key in ('seed','log_dir'):d.pop(key,None)
        d['scene'].pop('num_envs',None);d['scene']['terrain'].pop('num_envs',None)
        d['commands']['base_velocity'].pop('class_type',None)
    drift=differences(expected,current,'upright_mdp')
    report=read_json(folder/'config_audit.json')
    report.update(arm=ARM,status='failed' if drift else 'passed',upright_mdp_differences=drift,
        schedule=ARM,specification_sha256=PLAN['specification_sha256'])
    write_json(folder/'config_audit.json',report)
    if drift:raise ValueError('Upright MDP drift: '+repr(drift[:5]))
