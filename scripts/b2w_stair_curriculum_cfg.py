"""Matched safety baseline and adaptive target stair curriculum."""
from copy import deepcopy
import os
from pathlib import Path
import yaml
from b2w_core_stage3_cfg import CoreStage3VelocityCommand, env_config as parent_env, agent_config as parent_agent
from b2w_core_stage3_sampling import build_banks
from stair_curriculum_contract import load_plan, PLAN_SHA
from run_support import ROOT, read_json, write_json

PLAN = load_plan()
ARM = os.environ['B2W_STAIR_ARM']
LR = PLAN['arms'][ARM]['lr_cap']
if build_banks(PLAN) != build_banks(read_json(ROOT/PLAN['parent_bank_source'])):
    raise ValueError('Original parent command banks changed')


class StairCurriculumVelocityCommand(CoreStage3VelocityCommand):
    plan = PLAN
    banks = build_banks(PLAN)
    command_distribution_note = 'Exact original 24650 banks/cohorts; matched safety; stair level adaptation differs'
    retention_measures = ('Original rewards, bank schedules, cohorts, assets, noise, and PPO settings',
                          'Exact actor/critic/std/Adam restore; LR cap 1e-5 in both arms',
                          'Completed returns and phase coverage recorded separately by cohort')
    training_profile = {**PLAN,'plan_sha256':PLAN_SHA,'arm':ARM,'seed':PLAN['seed'],'lr_cap':LR}


def env_config():
    cfg = parent_env()
    cfg.commands.base_velocity.class_type = StairCurriculumVelocityCommand
    from isaaclab.managers import TerminationTermCfg, CurriculumTermCfg
    from b2w_curriculum_env import safety_terminal, safe_timeout, safe_bounds, stair_curriculum
    cfg.terminations.safety = TerminationTermCfg(func=safety_terminal, time_out=False)
    cfg.terminations.time_out.func = safe_timeout
    cfg.terminations.terrain_out_of_bounds.func = safe_bounds
    cfg.curriculum.terrain_levels = CurriculumTermCfg(func=stair_curriculum)
    return cfg


def agent_config():
    cfg = parent_agent()
    cfg.seed = PLAN['seed']
    cfg.max_iterations = PLAN['additional_updates']
    cfg.save_interval = PLAN['checkpoint_interval']
    cfg.algorithm.learning_rate = LR
    cfg.experiment_name = f'b2w_24650_stair_{ARM}_{PLAN["seed"]}'
    return cfg


def audit(env_cfg, agent_cfg, parent, run_path):
    from isaaclab.utils.io import dump_yaml
    from b2w_training_audit import differences
    path = Path(run_path)/'pilot_environment.yaml'
    dump_yaml(str(path),env_cfg)
    saved = yaml.load((parent/'env.yaml').read_text(),Loader=yaml.BaseLoader)
    actual = yaml.load(path.read_text(),Loader=yaml.BaseLoader)
    changed = []
    for name in ('rewards','observations','actions','events','sim','decimation','episode_length_s'):
        changed.extend(differences(saved[name],actual[name],name))
    for name in ('actuators','init_state','spawn'):
        changed.extend(differences(saved['scene']['robot'][name],actual['scene']['robot'][name],'robot.'+name))
    terrain, expected = deepcopy(actual['scene']['terrain']),deepcopy(saved['scene']['terrain'])
    terrain.pop('num_envs',None); expected.pop('num_envs',None)
    changed.extend(differences(expected,terrain,'terrain'))
    commands = deepcopy(actual['commands'])
    if commands['base_velocity']['class_type'] != 'b2w_stair_curriculum_cfg:StairCurriculumVelocityCommand':
        raise ValueError('Unexpected command class')
    commands['base_velocity']['class_type'] = saved['commands']['base_velocity']['class_type']
    changed.extend(differences(saved['commands'],commands,'commands'))
    assert actual['curriculum']['terrain_levels']['func']=='b2w_curriculum_env:stair_curriculum'
    normalized_curriculum=deepcopy(actual['curriculum'])
    normalized_curriculum['terrain_levels']['func']=saved['curriculum']['terrain_levels']['func']
    changed.extend(differences(saved['curriculum'],normalized_curriculum,'curriculum'))
    terminations = deepcopy(actual['terminations'])
    safety=terminations.pop('safety')
    assert safety['func']=='b2w_curriculum_env:safety_terminal' and safety['time_out'].lower()=='false'
    assert terminations['terrain_out_of_bounds']['func']=='b2w_curriculum_env:safe_bounds'
    terminations['terrain_out_of_bounds']['func']=saved['terminations']['terrain_out_of_bounds']['func']
    if terminations['time_out']['func'] != 'b2w_curriculum_env:safe_timeout':
        raise ValueError('Unexpected timeout')
    terminations['time_out']['func'] = saved['terminations']['time_out']['func']
    changed.extend(differences(saved['terminations'],terminations,'terminations'))
    expected_agent = yaml.safe_load((parent/'agent.yaml').read_text())
    agent = deepcopy(dict(agent_cfg))
    if expected_agent['obs_groups'] == {} and agent.get('obs_groups') == {'policy':['policy'],'critic':['critic']}:
        agent['obs_groups'] = {}
    for section in ('policy','algorithm'):
        agent[section].setdefault('class_name',expected_agent[section]['class_name'])
    expected_agent['algorithm']['learning_rate'] = LR
    for key in ('num_steps_per_env','empirical_normalization','obs_groups','clip_actions','class_name','policy','algorithm'):
        changed.extend(differences(expected_agent[key],agent[key],'agent.'+key))
    report = {'status':'failed' if changed else 'passed','arm':ARM,'seed':PLAN['seed'],
              'lr_cap':LR,'plan_sha256':PLAN_SHA,'undeclared_differences':changed,
              'parent_banks_restored':True,'all_rewards_unchanged':True,
              'scope':'Common safety task; only target stair level adaptation differs'}
    write_json(Path(run_path)/'pilot_config_audit.json',report)
    if changed:
        raise ValueError('Undeclared configuration changes: '+repr(changed[:3]))
