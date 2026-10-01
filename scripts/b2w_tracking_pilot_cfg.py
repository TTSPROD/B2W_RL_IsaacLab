"""Matched A/B continuation from 24650; only the declared pose term differs."""
from copy import deepcopy
import os
from pathlib import Path
import json
import hashlib

from b2w_core_stage3_cfg import (CoreStage3VelocityCommand, env_config as reconstruct_parent,
                               agent_config as previous_agent)
from b2w_core_stage3_sampling import build_banks
from b2w_tracking_posture import posture_multiplier
from robot_lab.tasks.manager_based.locomotion.velocity.mdp.rewards import joint_pos_penalty

ROOT=Path(__file__).resolve().parents[1]
PLAN_PATH=ROOT/'configs/24650_tracking_posture_ab_20260930.json'
PLAN_SHA='d0ff80ce32f24dc0aa42a9a1d1a892a524bc5e9b7bfb1634d4be41d794ed1777'
if hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()!=PLAN_SHA:
    raise RuntimeError('Pilot plan changed')
PLAN=json.loads(PLAN_PATH.read_text())
ARM=os.environ['B2W_PILOT_ARM']
SEED=int(os.environ['B2W_PILOT_SEED'])
if ARM not in ('control','posture') or SEED not in PLAN['seeds']:
    raise RuntimeError('Undeclared pilot arm/seed')


class TrackingPilotVelocityCommand(CoreStage3VelocityCommand):
    plan=PLAN
    banks=build_banks(PLAN)
    command_distribution_note='Exact original 24650 bank weights and schedules; equal across A/B.'
    retention_measures=('Original 24650 banks, cohorts, geometry, noise and actuators retained',
                        'Zero, longitudinal and stairs rewards unchanged',
                        'Only small pure-axis target-cohort pose regularization differs between arms')
    training_profile={**PLAN,'plan_sha256':PLAN_SHA,'arm':ARM,'seed':SEED}


def focused_posture_penalty(env, command_name, asset_cfg, stand_still_scale,
                            velocity_threshold, command_threshold):
    original=joint_pos_penalty(env,command_name,asset_cfg,stand_still_scale,
                               velocity_threshold,command_threshold)
    term=env.command_manager.get_term(command_name)
    cohort=term.target_masks['flat'] | term.target_masks['rough']
    return original*posture_multiplier(term.command,cohort,PLAN['factor']['treatment_scale'])


def env_config():
    cfg=reconstruct_parent()
    cfg.commands.base_velocity.class_type=TrackingPilotVelocityCommand
    if ARM=='posture':
        cfg.rewards.joint_pos_penalty.func=focused_posture_penalty
    return cfg


def agent_config():
    cfg=previous_agent()
    cfg.seed=SEED
    cfg.max_iterations=PLAN['additional_updates']
    cfg.save_interval=PLAN['checkpoint_interval']
    cfg.algorithm.learning_rate=PLAN['lr_cap']
    cfg.experiment_name=f'b2w_24650_tracking_{ARM}_{SEED}'
    return cfg


def audit(env_cfg,agent_cfg,parent,run_path):
    import yaml
    from isaaclab.utils.io import dump_yaml
    from b2w_training_audit import differences
    from run_support import write_json
    path=Path(run_path)/'pilot_environment.yaml'
    dump_yaml(str(path),env_cfg)
    saved=yaml.load((parent/'env.yaml').read_text(),Loader=yaml.BaseLoader)
    actual=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
    changed=[]
    rewards=deepcopy(actual['rewards'])
    expected_func=('b2w_tracking_pilot_cfg:focused_posture_penalty' if ARM=='posture'
                   else saved['rewards']['joint_pos_penalty']['func'])
    if rewards['joint_pos_penalty']['func']!=expected_func:
        raise RuntimeError('Unexpected reward implementation')
    rewards['joint_pos_penalty']['func']=saved['rewards']['joint_pos_penalty']['func']
    changed.extend(differences(saved['rewards'],rewards,'rewards'))
    for name in ('observations','actions','events','curriculum','sim','decimation','episode_length_s'):
        changed.extend(differences(saved[name],actual[name],name))
    for name in ('actuators','init_state','spawn'):
        changed.extend(differences(saved['scene']['robot'][name],actual['scene']['robot'][name],'robot.'+name))
    terrain=deepcopy(actual['scene']['terrain']);oldterrain=deepcopy(saved['scene']['terrain'])
    terrain.pop('num_envs',None);oldterrain.pop('num_envs',None)
    changed.extend(differences(oldterrain,terrain,'terrain'))
    commands=deepcopy(actual['commands'])
    commands['base_velocity']['class_type']=saved['commands']['base_velocity']['class_type']
    changed.extend(differences(saved['commands'],commands,'commands'))
    termination=deepcopy(actual['terminations'])
    if termination['time_out']['func']!='b2w_core_stage3_cfg:core_stage3_timeout':
        raise RuntimeError('Unexpected timeout')
    termination['time_out']['func']=saved['terminations']['time_out']['func']
    changed.extend(differences(saved['terminations'],termination,'terminations'))
    a=yaml.safe_load((parent/'agent.yaml').read_text());b=deepcopy(dict(agent_cfg))
    if a['obs_groups']=={} and b.get('obs_groups')=={'policy':['policy'],'critic':['critic']}:
        b['obs_groups']={}
    for section in ('policy','algorithm'):
        b[section].setdefault('class_name',a[section]['class_name'])
    for key in ('num_steps_per_env','empirical_normalization','obs_groups','clip_actions','class_name','policy','algorithm'):
        changed.extend(differences(a[key],b[key],'agent.'+key))
    report={'status':'failed' if changed else 'passed','arm':ARM,'seed':SEED,
            'undeclared_differences':changed,'plan_sha256':PLAN_SHA,
            'changed_reward_function':expected_func,'parent_banks_restored':True,
            'scope':'Protected physics/robot/ABI/events/rewards/PPO audited before updating'}
    write_json(Path(run_path)/'pilot_config_audit.json',report)
    if changed:
        raise RuntimeError('Pilot config differs beyond declared intervention: '+repr(changed[:3]))
