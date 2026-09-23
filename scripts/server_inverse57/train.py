"""Isolated 57->16 upstream fine-tune; no vendor modifications."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument('--parent', required=True)
parser.add_argument('--parent-sha256', required=True)
parser.add_argument('--initial', action='store_true')
parser.add_argument('--updates', type=int, required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--previous-terrain')
parser.add_argument('--distributed', action='store_true')
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
launcher = AppLauncher(args)
from isaac_compat import apply_pinned_urdf_importer_compatibility
apply_pinned_urdf_importer_compatibility()

import gymnasium as gym
import torch
import robot_lab.tasks
from isaaclab_tasks.utils import parse_env_cfg, load_cfg_from_registry
from isaaclab_tasks.manager_based.locomotion.velocity.mdp.curriculums import terrain_levels_vel
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
from isaaclab.utils.io import dump_yaml
from rsl_rl.runners import OnPolicyRunner

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.backends.cudnn.deterministic = False
torch.backends.cudnn.benchmark = False

def focused_levels(env, env_ids):
    terrain_levels_vel(env, env_ids)
    ids = torch.as_tensor(env_ids, device=env.device)
    ids = ids[ids % 2 == 0]
    terrain = env.scene.terrain
    terrain.terrain_levels[ids] = torch.randint(7, 10, (len(ids),), device=env.device)
    terrain.env_origins[ids] = terrain.terrain_origins[terrain.terrain_levels[ids], terrain.terrain_types[ids]]
    return terrain.terrain_levels.float().mean()

rank = int(os.environ.get('LOCAL_RANK', '0'))
assert int(os.environ.get('WORLD_SIZE', '1')) == 4
device = f'cuda:{rank}'
out = Path(args.output)
out.mkdir(parents=True, exist_ok=True)
task = 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0'
cfg = parse_env_cfg(task, device=device, num_envs=1024, use_fabric=True)
agent = load_cfg_from_registry(task, 'rsl_rl_cfg_entry_point')
# Preserve the complete contract, not merely tensor dimensions.
contract_before = repr((cfg.observations.to_dict(), cfg.actions.to_dict(), cfg.rewards.to_dict(), cfg.commands.to_dict()))
cfg.seed = 54 + rank
cfg.scene.terrain.terrain_generator.seed = 54 + rank
proportions = dict(pyramid_stairs=.20, pyramid_stairs_inv=.35, boxes=.15,
                  random_rough=.10, hf_pyramid_slope=.10, hf_pyramid_slope_inv=.10)
assert set(proportions) == set(cfg.scene.terrain.terrain_generator.sub_terrains)
for name, value in proportions.items():
    cfg.scene.terrain.terrain_generator.sub_terrains[name].proportion = value
cfg.curriculum.terrain_levels.func = focused_levels
assert contract_before == repr((cfg.observations.to_dict(), cfg.actions.to_dict(), cfg.rewards.to_dict(), cfg.commands.to_dict()))
cfg.commands.base_velocity.debug_vis = False
cfg.scene.robot.spawn.usd_dir = f'/run-output/train-usd/rank{rank}'
cfg.log_dir = str(out)
agent.seed = cfg.seed
agent.device = device
agent.save_interval = 100
agent.algorithm.learning_rate = 1e-4
agent.algorithm.schedule = 'fixed'
agent.logger = 'tensorboard'
env = gym.make(task, cfg=cfg)
terrain = env.unwrapped.scene.terrain
if args.previous_terrain:
    levels = torch.load(Path(args.previous_terrain)/f'terrain_rank{rank}.pt', weights_only=True, map_location=device)
    terrain.terrain_levels[:] = levels
else:
    terrain.terrain_levels[::2] = torch.randint(7, 10, (512,), device=device)
terrain.env_origins[:] = terrain.terrain_origins[terrain.terrain_levels, terrain.terrain_types]
env = RslRlVecEnvWrapper(env, clip_actions=agent.clip_actions)
obs = env.get_observations()
assert obs['policy'].shape == (1024, 57) and env.num_actions == 16
terms = list(env.unwrapped.observation_manager.active_terms['policy'])
assert terms == ['base_ang_vel', 'projected_gravity', 'velocity_commands', 'joint_pos', 'joint_vel', 'actions'], terms
runner = OnPolicyRunner(env, agent.to_dict(), log_dir=str(out), device=device)
parent = Path(args.parent)
digest = hashlib.sha256(parent.read_bytes()).hexdigest()
assert digest == args.parent_sha256
saved = torch.load(parent, map_location='cpu', weights_only=False)
runner.load(str(parent), load_optimizer=True, map_location=device)
for name, value in runner.alg.policy.state_dict().items():
    assert torch.equal(value.cpu(), saved['model_state_dict'][name]), name
assert runner.alg.policy.actor[0].in_features == 57
assert runner.alg.policy.actor[-1].out_features == 16
assert len(runner.alg.optimizer.state_dict()['state']) == len(saved['optimizer_state_dict']['state'])
runner.alg.learning_rate = 1e-4
for group in runner.alg.optimizer.param_groups:
    group['lr'] = 1e-4
runner.current_learning_iteration = 0 if args.initial else saved['iter'] + 1
audit = dict(rank=rank, parent_sha256=digest, actor_inputs=57, actions=16,
             model_equal=True, optimizer_restored=True, fixed_lr=1e-4,
             next_iteration=runner.current_learning_iteration, updates=args.updates,
             policy_terms=terms, proportions=proportions,
             initial_level_histogram=torch.bincount(terrain.terrain_levels, minlength=10).cpu().tolist(),
             environment_reset_between_blocks=True)
(out/f'audit_rank{rank}.json').write_text(json.dumps(audit, indent=2))
if rank == 0:
    dump_yaml(str(out/'env.yaml'), cfg)
    dump_yaml(str(out/'agent.yaml'), agent)
    print('TRANSFER_AUDIT', json.dumps(audit), flush=True)
start = time.time()
runner.learn(num_learning_iterations=args.updates, init_at_random_ep_len=True)
torch.save(terrain.terrain_levels.cpu(), out/f'terrain_rank{rank}.pt')
(out/f'completed_rank{rank}.json').write_text(json.dumps(dict(iteration=runner.current_learning_iteration,
    seconds=time.time()-start, allocated_mib=torch.cuda.max_memory_allocated()/2**20)))
env.close()
launcher.app.close()
