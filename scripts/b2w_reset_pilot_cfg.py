"""Reset-only task overrides around the retained 24650 task, standard PPO."""
from copy import deepcopy
import os
from pathlib import Path
import yaml
from b2w_core_stage3_cfg import CoreStage3VelocityCommand, env_config as parent_env
from b2w_core_stage3_sampling import build_banks
from reset_pilot_contract import load_plan
from run_support import ROOT, write_json, sha256

PLAN=load_plan()
ARM=os.environ['B2W_RESET_ARM']


class ResetVelocityCommand(CoreStage3VelocityCommand):
    plan=PLAN
    banks=build_banks(PLAN)
    training_profile={**PLAN,'arm':ARM,'adaptive':False}


def env_config():
    cfg=parent_env()
    cfg.commands.base_velocity.class_type=ResetVelocityCommand
    from isaaclab.managers import TerminationTermCfg, CurriculumTermCfg
    from b2w_curriculum_env import safety_terminal, safe_timeout, safe_bounds, stair_curriculum
    cfg.terminations.safety=TerminationTermCfg(func=safety_terminal,time_out=False)
    cfg.terminations.time_out.func=safe_timeout
    cfg.terminations.terrain_out_of_bounds.func=safe_bounds
    cfg.curriculum.terrain_levels=CurriculumTermCfg(func=stair_curriculum)
    if ARM=='upright':
        cfg.events.randomize_reset_base.params['pose_range']['roll']=(-.1,.1)
        cfg.events.randomize_reset_base.params['pose_range']['pitch']=(-.1,.1)
    return cfg


def agent_config():
    from robot_lab.tasks.manager_based.locomotion.velocity.config.wheeled.unitree_b2w.agents.rsl_rl_ppo_cfg import UnitreeB2WRoughPPORunnerCfg
    saved=yaml.safe_load((ROOT/'policies/local/core_24650/agent.yaml').read_text())
    cfg=UnitreeB2WRoughPPORunnerCfg()
    for key,value in saved.items():
        if key in ('policy','algorithm'):
            for field,v in value.items():setattr(getattr(cfg,key),field,v)
        else:setattr(cfg,key,value)
    cfg.obs_groups={'policy':['policy'],'critic':['critic']}
    cfg.seed=PLAN['seed'];cfg.max_iterations=PLAN['updates'];cfg.save_interval=50
    cfg.experiment_name=f'b2w_24650_reset_{ARM}_{PLAN["seed"]}'
    cfg.run_name=os.environ.get('B2W_RESET_RUN_NAME','pilot')
    cfg.resume=True;cfg.load_run='_parent';cfg.load_checkpoint='model_24650.pt'
    return cfg


def audit_environment(cfg, output):
    from isaaclab.utils.io import dump_yaml
    from b2w_training_audit import differences
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=output/'reset_environment.yaml';dump_yaml(str(path),cfg)
    actual=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
    parent=yaml.load((ROOT/'policies/local/core_24650/env.yaml').read_text(),Loader=yaml.BaseLoader)
    changes=[]
    for name in ('rewards','observations','actions','events','sim','decimation','episode_length_s'):
        expected=deepcopy(parent[name]);current=deepcopy(actual[name])
        if name=='events' and ARM=='upright':
            for axis in ('roll','pitch'):
                expected['randomize_reset_base']['params']['pose_range'][axis]=['-0.1','0.1']
        changes.extend(differences(expected,current,name))
    for name in ('actuators','init_state','spawn'):
        changes.extend(differences(parent['scene']['robot'][name],actual['scene']['robot'][name],'robot.'+name))
    terrain=deepcopy(actual['scene']['terrain']);expected=deepcopy(parent['scene']['terrain'])
    for d in (terrain,expected):d.pop('num_envs',None)
    changes.extend(differences(expected,terrain,'terrain'))
    commands=deepcopy(actual['commands'])
    commands['base_velocity']['class_type']=parent['commands']['base_velocity']['class_type']
    changes.extend(differences(parent['commands'],commands,'commands'))
    write_json(output/'config_audit.json',{'status':'failed' if changes else 'passed',
        'arm':ARM,'undeclared_differences':changes,'parent_sha256':PLAN['parent_sha256'],
        'declared_common_changes':['physics-tick true safety terminal','standard OnPolicyRunner'],
        'intervention':'roll/pitch initial distribution only','environment_sha256':sha256(path)})
    if changes:raise ValueError('Reset task drift: '+repr(changes[:4]))
