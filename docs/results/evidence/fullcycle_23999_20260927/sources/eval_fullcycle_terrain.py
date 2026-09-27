"""Paired full-cycle terrain comparison with frozen scoring and physics-step safety."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

from b2w_runtime import configure_process
configure_process()
if os.environ.get('B2W_PAYLOAD_URDF'):
    raise RuntimeError('Nominal test refuses a payload override')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--terrain', required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seeds', type=int, default=32)
parser.add_argument('--smoke-steps', type=int, default=0)
parser.add_argument('--policy-map', type=Path, help='JSON mapping two policy IDs to verified export directories')
args = parser.parse_args()
if args.output.exists():
    raise FileExistsError(args.output)

from fullcycle_eval_protocol import (SEED_START, SEEDS, POLICIES, EXPORT_DIRS, cases_for, protocol_manifest,
                                    geometry, meshes_for, stair_exposure, coverage)
if args.policy_map:
    root_path = Path(__file__).resolve().parents[1]
    selection = json.loads(args.policy_map.read_text(encoding='utf-8-sig'))
    EXPORT_DIRS = {int(policy): (root_path / folder).resolve() for policy, folder in selection.items()}
    if any(not folder.is_relative_to(root_path) for folder in EXPORT_DIRS.values()):
        raise ValueError('Policy exports must remain inside this project')
    POLICIES = tuple(EXPORT_DIRS)
frozen_plan = protocol_manifest(EXPORT_DIRS)
import torch
import tensordict  # noqa: F401
from isaaclab.app import AppLauncher
root = Path(__file__).resolve().parents[1]
sys.argv = [sys.argv[0], '--portable-root', str(root/f'.cache/kit-fullcycle-{os.getpid()}'),
            '--ext-folder', str(root/'.runtime/extensions')]
launcher = AppLauncher({'headless': True})
app = launcher.app

import gymnasium as gym
import numpy as np
import torch
import trimesh
from isaaclab.terrains import TerrainGeneratorCfg
from isaaclab.terrains.sub_terrain_cfg import SubTerrainBaseCfg
from isaaclab.utils import configclass
from isaaclab_tasks.utils import parse_env_cfg
from b2w_runtime import register_b2w_tasks
from local_b2w_assets import configure_b2w_env
from check_policy_contract import load_contract
from locomotion57_protocol import (
    DT, Telemetry, assess,
    reset_sample, sha256, terrain_boxes,
)

def export_path(iteration):
    return EXPORT_DIRS[iteration]/'policy.pt'

register_b2w_tasks()
torch.set_num_threads(4)
definition = geometry(args.terrain)


def terrain_function(difficulty, cfg):
    return meshes_for(args.terrain)


@configclass
class EvaluationTerrainCfg(SubTerrainBaseCfg):
    function = terrain_function


env = None
try:
    if args.seeds != SEEDS:
        raise ValueError("The declared suite requires 32 paired seeds")
    cases = cases_for(args.terrain)
    if args.smoke_steps:
        cases = cases[:1]
    entries = [(policy, case, seed) for policy in POLICIES for case in cases
               for seed in range(SEED_START, SEED_START+args.seeds)]
    n = len(entries)
    task = 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0'
    cfg = parse_env_cfg(task, device='cuda:0', num_envs=n, use_fabric=True)
    cfg.seed = SEED_START - 1
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
        seed=20260927, size=(80., 80.), border_width=0, num_rows=1, num_cols=1,
        curriculum=False, use_cache=False, sub_terrains={'course': EvaluationTerrainCfg()})
    cfg.scene.terrain.max_init_terrain_level = 0
    cfg.scene.height_scanner = None
    cfg.scene.height_scanner_base = None
    cfg.scene.contact_forces.update_period = cfg.sim.dt
    cfg.observations.critic.height_scan = None
    cfg.observations.policy.enable_corruption = False
    cfg.events = {}
    cfg.curriculum = {}
    cfg.terminations = {}
    cfg.rewards = {}
    cfg.commands.base_velocity.heading_command = False
    cfg.commands.base_velocity.rel_heading_envs = 0.0
    cfg.commands.base_velocity.rel_standing_envs = 0.0
    cfg.commands.base_velocity.resampling_time_range = (1e9, 1e9)
    cfg.commands.base_velocity.ranges.lin_vel_x = (0, 0)
    cfg.commands.base_velocity.ranges.lin_vel_y = (0, 0)
    cfg.commands.base_velocity.ranges.ang_vel_z = (0, 0)
    configure_b2w_env(cfg)
    env = gym.make(task, cfg=cfg).unwrapped
    env.reset()
    scene, device = env.scene, env.device
    robot, contact = scene['robot'], scene['contact_forces']
    contract = load_contract()
    joint_ids, names = robot.find_joints(contract['joint_names'], preserve_order=True)
    if names != contract['joint_names']:
        raise RuntimeError('Joint order mismatch')
    protected_ids = contact.find_bodies(['base_link', '.*_hip'])[0]
    wheel_names = ['FR_foot', 'FL_foot', 'RR_foot', 'RL_foot']
    wheel_ids = robot.find_bodies(wheel_names, preserve_order=True)[0]
    contact_wheel_ids = contact.find_bodies(wheel_names, preserve_order=True)[0]
    if len(protected_ids) != 5:
        raise RuntimeError('Safety contact mask mismatch')
    if abs(env.step_dt-DT) > 1e-10:
        raise RuntimeError('Not a 50 Hz policy')
    roots = robot.data.default_root_state.clone()
    roots[:, :3] += scene.env_origins
    positions = robot.data.default_joint_pos.clone()
    velocities = torch.zeros_like(positions)
    for i, (_, case, seed) in enumerate(entries):
        sample = reset_sample(seed)
        roots[i, :2] += torch.as_tensor(sample['xy'], device=device)
        yaw = sample['yaw'] + (np.pi if case.name == 'backward_traverse' else 0.)
        roots[i, 3:7] = torch.tensor([np.cos(yaw/2), 0, 0, np.sin(yaw/2)], device=device)
        positions[i, joint_ids[:12]] += torch.as_tensor(sample['qdelta'], device=device, dtype=torch.float32)
        velocities[i, joint_ids] = torch.as_tensor(sample['dq'], device=device, dtype=torch.float32)
    robot.write_root_state_to_sim(roots)
    robot.write_joint_state_to_sim(positions, velocities)
    scene.update(cfg.sim.dt)
    models = {p: torch.jit.load(str(export_path(p)), map_location=device).eval() for p in POLICIES}
    slices = {p: slice(j*n//len(POLICIES), (j+1)*n//len(POLICIES)) for j, p in enumerate(POLICIES)}
    default = torch.tensor(contract['default_dof_pos'], device=device)
    scales = torch.tensor(contract['action_scale'], device=device)
    previous = torch.zeros((n, 16), device=device)
    previous_targets = default.expand(n, -1).clone()
    commands = torch.zeros((n, 3), device=device)
    command_term = env.command_manager.get_term('base_velocity')

    def observation():
        q = robot.data.joint_pos[:, joint_ids]-default
        q[:, 12:] = 0
        return torch.cat((robot.data.root_ang_vel_b.clamp(-100, 100)*.25,
                          robot.data.projected_gravity_b.clamp(-100, 100), commands.clamp(-100, 100),
                          q.clamp(-100, 100), robot.data.joint_vel[:, joint_ids].clamp(-100, 100)*.05,
                          previous.clamp(-100, 100)), dim=1)

    observed = env.observation_manager.compute()['policy']
    torch.testing.assert_close(observation(), observed, rtol=0, atol=1e-5)
    ranges = robot.data.joint_pos_limits[0, joint_ids[:12]].cpu().numpy()
    telemetry = Telemetry(n, contract['torque_limits'], ranges, cfg.sim.dt)
    schedules = [case.schedule()[0] for _, case, _ in entries]
    lengths = np.array([len(schedule) for schedule in schedules])
    steps = min(int(lengths.max()), args.smoke_steps) if args.smoke_steps else int(lengths.max())
    trace = np.full((steps, n, 6), np.nan, np.float32)
    alive = np.ones(n, bool)
    is_stairs = definition['kind'] == 'stairs'
    exposure = np.zeros((steps, n), bool)
    # Full q/dq/tau samples at 10 Hz supplement 200 Hz safety/statistics.
    joint_trace = np.full(((steps+4)//5, n, 48), np.nan, np.float32)
    action_trace = np.full(((steps+4)//5, n, 16), np.nan, np.float32)
    wheels_trace = np.full((steps, n, 4, 4), np.nan, np.float32) if is_stairs else None
    attitude_trace = np.full(((steps+4)//5, n, 4), np.nan, np.float32)
    source_hashes = {name: sha256(root/'scripts'/name) for name in
                     ('locomotion57_protocol.py', 'operating57_protocol.py', 'fullcycle_eval_protocol.py', 'eval_fullcycle_terrain.py', 'local_b2w_assets.py')}
    metadata = {
        'engine': 'Isaac', 'protocol': frozen_plan, 'source_sha256': source_hashes,
        'protocol_role': 'Declared terrain extension; unchanged operating57 assess and Telemetry',
        'evaluated_export_manifests': {p: json.loads((folder/'manifest.json').read_text()) for p, folder in EXPORT_DIRS.items()},
        'geometry': definition,
        'runtime': {'torch': torch.__version__, 'gpu': torch.cuda.get_device_name()},
        'physics_dt_s': cfg.sim.dt, 'policy_dt_s': DT, 'smoke': bool(args.smoke_steps),
        'compiled_model': {'body_names': robot.body_names,
                           'mass_kg': robot.data.default_mass[0].cpu().tolist(),
                           'hard_joint_ranges': ranges.tolist(), 'joint_names': names,
                           'torque_semantics': 'Isaac applied_torque: explicit legs; estimated implicit wheel PD torque'},
        'policy_exports': {p: {'path': str(export_path(p)), 'sha256': sha256(export_path(p))} for p in POLICIES},
        'observation_parity_max_abs': float((observation()-observed).abs().max().item()),
        'reset_seeds': list(range(SEED_START, SEED_START+args.seeds)),
        'no_autoreset': True, 'actor_only': True, 'navigation_feedback': False,
        'case_order': [case.name for case in cases],
    }
    start_time = time.monotonic()
    command_observation_error = 0.0
    with torch.inference_mode():
        for step in range(steps):
            alive &= step < lengths
            if not alive.any():
                break
            command_np = np.stack([s[min(step, len(s)-1)] for s in schedules])
            commands.copy_(torch.as_tensor(command_np, device=device))
            command_term.vel_command_b.copy_(commands)
            obs = observation()
            command_observation_error = max(command_observation_error, float((obs[:, 6:9] - commands).abs().max().item()))
            if step % 500 == 0:
                torch.testing.assert_close(obs, env.observation_manager.compute()["policy"], rtol=0, atol=1e-5)
            actions = torch.empty((n, 16), device=device)
            for policy, model in models.items():
                actions[slices[policy]] = model(obs[slices[policy]])
            bad = ~torch.isfinite(actions).all(dim=1).cpu().numpy()
            telemetry.flags[alive & bad, 0] = True
            telemetry.first_failure_s[alive & bad] = step*DT
            alive &= ~bad
            actions[torch.as_tensor(~alive, device=device)] = 0
            env.action_manager.process_action(actions)
            targets = (actions*scales+default).clamp(-100, 100)
            telemetry.slew_peak = np.maximum(telemetry.slew_peak,
                ((targets-previous_targets).abs()/DT).cpu().numpy()*alive[:, None])
            previous_targets.copy_(targets)
            previous.copy_(actions)
            for substep in range(cfg.decimation):
                env.action_manager.apply_action()
                scene.write_data_to_sim()
                env.sim.step(render=False)
                scene.update(cfg.sim.dt)
                forces = contact.data.net_forces_w[:, protected_ids].norm(dim=-1).max(dim=1).values
                q = robot.data.joint_pos[:, joint_ids]
                dq = robot.data.joint_vel[:, joint_ids]
                tau = robot.data.applied_torque[:, joint_ids]
                packed = torch.cat((q, dq, tau, robot.data.projected_gravity_b[:, 2:3],
                                    forces[:, None], robot.data.root_state_w), dim=1).cpu().numpy()
                finite = np.isfinite(packed).all(axis=1)
                newly_failed = telemetry.update(packed[:, :16], packed[:, 16:32], packed[:, 32:48],
                    packed[:, 48], packed[:, 49], finite, alive, step*DT+(substep+1)*cfg.sim.dt)
                alive &= ~newly_failed
            measured = torch.cat((robot.data.root_lin_vel_b[:, :2], robot.data.root_ang_vel_b[:, 2:3],
                                  robot.data.root_pos_w-scene.env_origins), dim=1).cpu().numpy()
            trace[step, alive] = measured[alive]
            if step % 5 == 0:
                joint_trace[step//5, alive] = packed[alive, :48]
                action_trace[step//5, alive] = actions.cpu().numpy()[alive]
                attitude_trace[step//5, alive] = robot.data.root_quat_w.cpu().numpy()[alive]
            if is_stairs:
                wheel_xyz = robot.data.body_pos_w[:, wheel_ids].clone()
                wheel_xyz[..., :2] -= scene.env_origins[:, None, :2]
                wheel_xyz = wheel_xyz.cpu().numpy()
                wheel_force = contact.data.net_forces_w[:, contact_wheel_ids, 2].cpu().numpy()
                exposure[step] = stair_exposure(args.terrain, measured[:,3:], wheel_xyz, wheel_force) & alive
                wheels_trace[step, alive, :, :3] = wheel_xyz[alive]
                wheels_trace[step, alive, :, 3] = wheel_force[alive]
            telemetry.slip_peak = np.maximum(telemetry.slip_peak,
                np.max(np.abs(packed[:, 28:32]*.0875-measured[:, 0:1]), axis=1)*alive)
            if step % 500 == 0:
                print(f'PROGRESS {args.terrain} step={step}/{steps} alive={alive.sum()}/{n} elapsed={time.monotonic()-start_time:.1f}s', flush=True)
    records = []
    for i, (policy, case, seed) in enumerate(entries):
        valid_count = int(np.isfinite(trace[:, i, 0]).sum())
        result = assess(case, trace[:valid_count, i, :3], trace[:valid_count, i, 3:],
                        telemetry.result(i), valid_count == case.steps, definition)
        valid = np.isfinite(trace[:, i, 0])
        terrain_coverage = coverage(case, exposure[:, i], trace[:, i, 3:], valid)
        if terrain_coverage is not None:
            by_segment = {s['segment']: s for s in result['segments']}
            for window in terrain_coverage['zero_windows']:
                window['exposed_zero_success'] = bool(window['exposure_pass'] and
                    by_segment.get(window['segment'], {}).get('continuous_zero_pass', False))
            covered = (terrain_coverage['moving_exposure_pass'] and
                       all(w['exposed_zero_success'] for w in terrain_coverage['zero_windows']))
        else:
            covered = True
        records.append({'policy': policy, 'terrain': args.terrain, 'case': case.name, 'seed': seed,
                        'terrain_exposure': terrain_coverage,
                        'covered_scenario_success': bool(covered and result['outcome'] == 'success'), **result})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    trace_path = args.output.with_suffix('.npz')
    extra_traces = {'joints_10hz': joint_trace, 'raw_actions_10hz': action_trace, 'quaternion_wxyz_10hz': attitude_trace, 'stair_exposure': exposure}
    if wheels_trace is not None:
        extra_traces['wheels_xyz_upforce_50hz'] = wheels_trace
    np.savez_compressed(trace_path, trace=trace, lengths=lengths, **extra_traces,
                        commands=np.stack([np.pad(s, ((0, int(lengths.max())-len(s)), (0, 0)), constant_values=np.nan)
                                           for s in schedules]))
    metadata.update({'command_observation_max_abs': command_observation_error, 'wall_seconds': time.monotonic()-start_time, 'records': records,
                     'trace_path': str(trace_path), 'trace_sha256': sha256(trace_path)})
    args.output.write_text(json.dumps(metadata, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print('DONE', args.output, {p: sum(r['outcome']=='success' for r in records if r['policy']==p) for p in POLICIES}, flush=True)
except BaseException:
    import traceback
    traceback.print_exc()
    raise
finally:
    if env is not None:
        env.close()
    app.close()


