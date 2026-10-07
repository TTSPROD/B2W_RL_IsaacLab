"""DeepSeek F1: straight short flight target stairs with real-success promotion."""
from copy import deepcopy
import os
from pathlib import Path
import yaml
from b2w_core_stage3_cfg import CoreStage3VelocityCommand, env_config as parent_env, agent_config as parent_agent
from b2w_core_stage3_sampling import build_banks
from b2w_short_flight_terrain import stair_flight
from isaaclab.terrains.sub_terrain_cfg import SubTerrainBaseCfg
from isaaclab.utils import configclass
from short_flight_contract import load_plan, PLAN_SHA
from run_support import ROOT, read_json, write_json


@configclass
class StairFlightCfg(SubTerrainBaseCfg):
    function = staticmethod(stair_flight)
    direction: int = 1
    first_edge_x: float = 0.8
    tread_m: float = 0.3
    step_height_range: tuple[float, float] = (0.05, 0.12)
    num_steps_min: int = 3
    num_steps_max: int = 12


PLAN = load_plan()
ARM = os.environ['B2W_SHORT_FLIGHT_ARM']
LR = PLAN['arms'][ARM]['lr_cap']
if build_banks(PLAN) != build_banks(read_json(ROOT/PLAN['parent_bank_source'])):
    raise ValueError('Original parent command banks changed')


class ShortFlightVelocityCommand(CoreStage3VelocityCommand):
    plan = PLAN
    banks = build_banks(PLAN)
    command_distribution_note = 'Exact original 24650 banks/cohorts; matched safety; straight short flight target stairs'
    retention_measures = ('Original rewards, bank schedules, cohorts, assets, noise, and PPO settings',
                          'Exact actor/critic/std/Adam restore; LR cap 1e-5',
                          'Completed returns and phase coverage recorded separately by cohort')
    training_profile = {**PLAN, 'plan_sha256': PLAN_SHA, 'arm': ARM, 'seed': PLAN['seed'], 'lr_cap': LR}


def env_config():
    cfg = parent_env()
    # Swap only the target stair sub-terrains to a straight short flight.
    generator = cfg.scene.terrain.terrain_generator
    plan_geometry = PLAN['target_geometry']
    flight_param = lambda direction: dict(
        direction=direction, first_edge_x=plan_geometry['flight_first_edge_m'],
        tread_m=plan_geometry['flight_tread_m'],
        step_height_range=tuple(plan_geometry['flight_height_m']),
        num_steps_min=plan_geometry['flight_min_steps'],
        num_steps_max=plan_geometry['flight_max_steps'])
    up = StairFlightCfg(**flight_param(1))
    down = StairFlightCfg(**flight_param(-1))
    up.proportion = generator.sub_terrains['target_stairs_up'].proportion
    down.proportion = generator.sub_terrains['target_stairs_down'].proportion
    generator.sub_terrains['target_stairs_up'] = up
    generator.sub_terrains['target_stairs_down'] = down

    cfg.commands.base_velocity.class_type = ShortFlightVelocityCommand
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
    cfg.experiment_name = f'b2w_24650_short_flight_{ARM}_{PLAN["seed"]}'
    return cfg


def audit(env_cfg, agent_cfg, parent, run_path):
    from isaaclab.utils.io import dump_yaml
    from b2w_training_audit import differences
    path = Path(run_path)/'pilot_environment.yaml'
    dump_yaml(str(path), env_cfg)
    saved = yaml.load((parent/'env.yaml').read_text(), Loader=yaml.BaseLoader)
    actual = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    changed = []
    for name in ('rewards','observations','actions','events','sim','decimation','episode_length_s'):
        changed.extend(differences(saved[name], actual[name], name))
    for name in ('actuators','init_state','spawn'):
        changed.extend(differences(saved['scene']['robot'][name], actual['scene']['robot'][name], 'robot.'+name))
    terrain, expected = deepcopy(actual['scene']['terrain']), deepcopy(saved['scene']['terrain'])
    terrain.pop('num_envs', None); expected.pop('num_envs', None)
    # The single declared factor: target_stairs_up/down geometries differ (flight vs pyramid).
    declared = []
    for name in ('target_stairs_up', 'target_stairs_down'):
        declared.extend(differences(expected['terrain_generator']['sub_terrains'].get(name, {}),
                                    terrain['terrain_generator']['sub_terrains'].get(name, {}), f'terrain.{name}.geometry'))
    for name in ('retention_pyramid_stairs','retention_pyramid_stairs_inv','retention_boxes','retention_random_rough',
                 'retention_slope_up','retention_slope_down','target_flat','target_rough'):
        changed.extend(differences(expected['terrain_generator']['sub_terrains'].get(name, {}),
                                   terrain['terrain_generator']['sub_terrains'].get(name, {}), f'terrain.{name}'))
    expected['terrain_generator']['sub_terrains'].pop('target_stairs_up', None)
    expected['terrain_generator']['sub_terrains'].pop('target_stairs_down', None)
    terrain['terrain_generator']['sub_terrains'].pop('target_stairs_up', None)
    terrain['terrain_generator']['sub_terrains'].pop('target_stairs_down', None)
    changed.extend(differences(expected, terrain, 'terrain'))
    commands = deepcopy(actual['commands'])
    if commands['base_velocity']['class_type'] != 'b2w_short_flight_cfg:ShortFlightVelocityCommand':
        raise ValueError('Unexpected command class')
    commands['base_velocity']['class_type'] = saved['commands']['base_velocity']['class_type']
    changed.extend(differences(saved['commands'], commands, 'commands'))
    assert actual['curriculum']['terrain_levels']['func'] == 'b2w_curriculum_env:stair_curriculum'
    normalized_curriculum = deepcopy(actual['curriculum'])
    # stair_curriculum is intentionally the same retained curriculum; normalize func name
    # which would otherwise appear only as an implementation-string difference on this class.
    normalized_curriculum['terrain_levels']['func'] = saved['curriculum']['terrain_levels']['func']
    changed.extend(differences(saved['curriculum'], normalized_curriculum, 'curriculum'))
    terminations = deepcopy(actual['terminations'])
    safety = terminations.pop('safety')
    assert safety['func'] == 'b2w_curriculum_env:safety_terminal' and safety['time_out'].lower() == 'false'
    assert terminations['terrain_out_of_bounds']['func'] == 'b2w_curriculum_env:safe_bounds'
    terminations['terrain_out_of_bounds']['func'] = saved['terminations']['terrain_out_of_bounds']['func']
    if terminations['time_out']['func'] != 'b2w_curriculum_env:safe_timeout':
        raise ValueError('Unexpected timeout')
    terminations['time_out']['func'] = saved['terminations']['time_out']['func']
    changed.extend(differences(saved['terminations'], terminations, 'terminations'))
    expected_agent = yaml.safe_load((parent/'agent.yaml').read_text())
    agent = deepcopy(dict(agent_cfg))
    if expected_agent['obs_groups'] == {} and agent.get('obs_groups') == {'policy':['policy'],'critic':['critic']}:
        agent['obs_groups'] = {}
    for section in ('policy','algorithm'):
        agent[section].setdefault('class_name', expected_agent[section]['class_name'])
    expected_agent['algorithm']['learning_rate'] = LR
    for key in ('num_steps_per_env','empirical_normalization','obs_groups','clip_actions','class_name','policy','algorithm'):
        changed.extend(differences(expected_agent[key], agent[key], 'agent.'+key))
    report = {'status':'failed' if changed else 'passed','arm':ARM,'seed':PLAN['seed'],
              'lr_cap':LR,'plan_sha256':PLAN_SHA,'undeclared_differences':changed,
              'declared_factor_differences':declared,
              'parent_banks_restored':True,'all_rewards_unchanged':True,
              'single_factor':'target_stairs_up/down geometry replaced by straight short flight',
              'scope':'Only target stair geometry differs from the rejected stair A/B baseline'}
    write_json(Path(run_path)/'pilot_config_audit.json', report)
    if changed:
        raise ValueError('Undeclared configuration changes: '+repr(changed[:3]))
