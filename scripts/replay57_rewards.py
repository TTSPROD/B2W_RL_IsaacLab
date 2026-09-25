"""Replay the actual saved upstream reward functions, without a learned critic."""
import importlib
import re
from types import SimpleNamespace
import numpy as np
import torch
from replay57_protocol import reward_terms, BODY_NAMES, DT
from check_policy_contract import load_contract


def resolved_function(path):
    module, name = path.split(':')
    if module not in ('isaaclab.envs.mdp.rewards',
                      'robot_lab.tasks.manager_based.locomotion.velocity.mdp.rewards'):
        raise ValueError(f'Unexpected reward module: {module}')
    return getattr(importlib.import_module(module),name)


def live_reward_config():
    from isaaclab.managers import RewardTermCfg, SceneEntityCfg
    return {name:RewardTermCfg(func=resolved_function(term['func']),weight=term['weight'],
        params={k:SceneEntityCfg(**v) if k.endswith('_cfg') else v for k,v in term['params'].items()})
        for name,term in reward_terms().items()}


def matching(patterns, names):
    if patterns is None:
        return list(range(len(names)))
    if isinstance(patterns,str):
        patterns = [patterns]
    return [i for i,n in enumerate(names) if any(re.fullmatch(p,n) for p in patterns)]


def offline_ledger(arrays, soft_limits):
    """All 17 active terms; contact history is the last three physics samples.

    At fixed command .3, the first-contact/no-command reward is identically zero.
    This proxy is verified against the live Isaac RewardManager for every sample.
    """
    shape = arrays['q'].shape[:2]
    n = int(np.prod(shape))
    def tensor(key):
        a = arrays[key]
        return torch.as_tensor(a.reshape((n,)+a.shape[2:]),dtype=torch.float32)
    contract = load_contract()
    names = contract['joint_names']
    data = SimpleNamespace(root_lin_vel_b=tensor('root_velocity_b')[:,:3],
        root_ang_vel_b=tensor('root_velocity_b')[:,3:], projected_gravity_b=tensor('gravity'),
        joint_pos=tensor('q'),joint_vel=tensor('dq'),joint_acc=tensor('ddq'),applied_torque=tensor('tau'),
        default_joint_pos=torch.tensor(contract['default_dof_pos']).expand(n,-1),
        soft_joint_pos_limits=torch.as_tensor(soft_limits,dtype=torch.float32).expand(n,-1,-1))
    def find_joints(patterns):
        ids = matching(patterns,names)
        return ids,[names[i] for i in ids]
    robot = SimpleNamespace(data=data,find_joints=find_joints)
    sensor = SimpleNamespace(data=SimpleNamespace(net_forces_w_history=tensor('contact_history')),
        compute_first_contact=lambda dt:torch.zeros((n,17),dtype=torch.bool))
    class Scene(dict):
        @property
        def sensors(self):
            return self
    env = SimpleNamespace(scene=Scene(robot=robot,contact_forces=sensor),num_envs=n,device='cpu',step_dt=DT,
        command_manager=SimpleNamespace(get_command=lambda _:torch.tensor([.3,0,0]).expand(n,-1)),
        action_manager=SimpleNamespace(action=tensor('action'),prev_action=tensor('previous_action')))
    values = {}
    for name,term in reward_terms().items():
        params = {}
        for k,v in term['params'].items():
            if k.endswith('_cfg'):
                params[k] = SimpleNamespace(name=v['name'],joint_ids=matching(v['joint_names'],names),
                    body_ids=matching(v['body_names'],BODY_NAMES))
            else:
                params[k] = v
        values[name] = (resolved_function(term['func'])(env,**params)*term['weight']).numpy().reshape(shape)
    return values
