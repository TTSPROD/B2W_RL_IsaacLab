"""Fail closed before PPO if the declared repair changes protected configuration."""
import json
from pathlib import Path

import yaml

from b2w_training_audit import differences


def audit_repair(cfg,parent_folder,run_path):
    from isaaclab.utils.io import dump_yaml
    destination=Path(run_path)/'repair_environment.yaml'
    dump_yaml(str(destination),cfg)
    saved=yaml.load((parent_folder/'env.yaml').read_text(),Loader=yaml.BaseLoader)
    current=yaml.load(destination.read_text(),Loader=yaml.BaseLoader)
    changes=[]
    for section in ('observations','actions','events','rewards','terminations','curriculum','commands','sim','decimation','episode_length_s'):
        changes.extend(differences(saved[section],current[section],section))
    for section in ('actuators','init_state','spawn'):
        changes.extend(differences(saved['scene']['robot'][section],current['scene']['robot'][section],'robot.'+section))
    changes.extend(differences(saved['scene']['terrain']['terrain_generator'],current['scene']['terrain']['terrain_generator'],'terrain_generator'))
    allowed={
        'commands.base_velocity.class_type':('b2w_regression500_cfg:RegressionVelocityCommand','b2w_repair501_cfg:RepairVelocityCommand'),
        'rewards.track_lin_vel_xy_exp.func':('robot_lab.tasks.manager_based.locomotion.velocity.mdp.rewards:track_lin_vel_xy_exp','b2w_repair501_rewards:track_linear'),
        'rewards.track_ang_vel_z_exp.func':('b2w_correction_cfg:track_moderate_yaw','b2w_repair501_rewards:track_angular'),
        'rewards.track_lin_vel_xy_exp.params.zero_std':(None,'0.15'),
        'rewards.track_ang_vel_z_exp.params.zero_std':(None,'0.15'),
        'rewards.joint_pos_limits.weight':('-5.0','-7.5'),
    }
    unexpected=[item for item in changes if (item['saved'],item['current'])!=allowed.get(item['path'])]
    missing=set(allowed)-{item['path'] for item in changes}
    report={'status':'passed' if not unexpected and not missing else 'failed',
            'declared_changes':changes,'unexpected':unexpected,'missing':sorted(missing),
            'scope':'24499 physics, robot, ABI, events, terrains and non-declared rewards unchanged'}
    (Path(run_path)/'repair_config_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('REPAIR_CONFIG_AUDIT='+json.dumps(report),flush=True)
    if unexpected or missing: raise RuntimeError('Repair config audit failed before any PPO update')
