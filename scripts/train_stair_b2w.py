"""Fine-tune the pinned B2W rough policy on complete stair flights.

All task changes live here, outside immutable vendor snapshots. The first
experiment keeps the rough actor/critic ABI and PPO hyperparameters intact.
"""

import argparse
import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import torch  # load native modules before Kit
import tensordict  # noqa: F401

from local_b2w_assets import (
    configure_b2w_env,
    configure_ground_plane,
    enable_policy_base_lin_vel,
    expand_actor_for_base_lin_vel,
)
from stair_command_profile import braking_speed
from stair_cycle_protocol import stop_outcome
from wheel_head_training import configure_wheel_head_only
from moving_teacher_anchor import install_moving_teacher_anchor
from hold_tail_reward import late_hold_speed_excess_squared

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--parent-checkpoint", type=Path, required=True)
parser.add_argument("--landing-stability-weight", type=float, default=0.0)
parser.add_argument("--stop-on-landing", action="store_true")
parser.add_argument("--restart-after-stop", action="store_true")
parser.add_argument("--strict-stop-deadline", action="store_true")
parser.add_argument("--cycle-protocol-v3", action="store_true",
                    help="Match the evaluator's 100-step stop boundary and unsafe terminations")
parser.add_argument("--rough-replay-fraction", type=float, default=0.15)
parser.add_argument("--up-fraction", type=float, help="Fraction of uphill terrain tiles; downhill gets the remaining stair tiles")
parser.add_argument("--stop-speed-reward-weight", type=float, default=0.0)
parser.add_argument("--late-hold-speed-penalty-weight", type=float, default=0.0,
                    help="Positive magnitude for a late-hold planar-speed hinge penalty")
parser.add_argument("--late-hold-start-step", type=int, default=40)
parser.add_argument("--late-hold-speed-threshold", type=float, default=0.10)
parser.add_argument("--landing-approach-speed", type=float)
parser.add_argument("--slowdown-distance", type=float, default=1.0)
parser.add_argument("--brake-profile", action="store_true")
parser.add_argument("--brake-distance", type=float, default=1.2)
parser.add_argument("--brake-min-speed", type=float, default=0.25)
parser.add_argument("--landing-tiles-fraction", type=float, default=0.0)
parser.add_argument("--landing-start-probability", type=float, default=0.0)
parser.add_argument("--rollin-start-offset", type=float,
                    help="Start selected stair tiles this many metres ahead on the flat approach")
parser.add_argument("--max-stair-rise", type=float, default=0.16)
parser.add_argument("--min-stair-run", type=float, default=0.30)
parser.add_argument("--inverse-rough-fraction", type=float, default=0.0)
parser.add_argument("--passage-reward-weight", type=float, default=0.0)
parser.add_argument("--hold-reward-weight", type=float, default=0.0,
                    help="One-shot reward for completing the 100-step safe hold")
parser.add_argument("--failure-replay-up", type=Path)
parser.add_argument("--failure-replay-down", type=Path)
parser.add_argument("--failure-replay-probe", action="store_true")
parser.add_argument("--rough-reset-probe", action="store_true")
parser.add_argument("--diverse-replay-commands", action="store_true")
parser.add_argument("--replay-command-probe", action="store_true")
parser.add_argument("--actor-base-lin-vel", action="store_true")
parser.add_argument("--wheel-head-only", action="store_true",
                    help="Train only the final four wheel rows of the actor output layer")
parser.add_argument("--teacher-anchor-weight", type=float, default=0.0,
                    help="Behavior-cloning weight to the parent actor on nonzero-command rollout states")
parser.add_argument("--fresh-optimizer", action="store_true")
parser.add_argument("--learning-rate", type=float, default=1e-4,
                    help="Fixed PPO learning rate; recorded in stair_parent.json")
parser.add_argument("--save-interval", type=int, default=25,
                    help="Checkpoint interval in PPO updates")
parser.add_argument("--observation-noise-scale", type=float, default=1.0,
                    help="Scale existing policy sensor-noise ranges without changing the 57-D ABI")
parser.add_argument("--reset-probe", action="store_true")
extra, passthrough = parser.parse_known_args(sys.argv[1:])
if extra.landing_stability_weight < 0:
    parser.error("--landing-stability-weight must be nonnegative")
if not 1e-6 <= extra.learning_rate <= 1e-3:
    parser.error("--learning-rate must be in [1e-6, 1e-3]")
if not 1 <= extra.save_interval <= 100:
    parser.error("--save-interval must be in [1, 100]")
if not 0.5 <= extra.observation_noise_scale <= 2.0:
    parser.error("--observation-noise-scale must be in [0.5, 2.0]")
if extra.restart_after_stop and not extra.stop_on_landing:
    parser.error("--restart-after-stop requires --stop-on-landing")
if extra.strict_stop_deadline and not extra.restart_after_stop:
    parser.error("--strict-stop-deadline requires --restart-after-stop")
if extra.cycle_protocol_v3 and not extra.restart_after_stop:
    parser.error("--cycle-protocol-v3 requires --restart-after-stop")
strict_deadline = extra.strict_stop_deadline or extra.cycle_protocol_v3
if not (0.05 <= extra.rough_replay_fraction <= 0.50):
    parser.error("--rough-replay-fraction must be in [0.05, 0.50]")
stair_total_fraction = 0.85 - extra.rough_replay_fraction
up_fraction = stair_total_fraction / 2 if extra.up_fraction is None else extra.up_fraction
down_fraction = stair_total_fraction - up_fraction
if not (0.1 <= up_fraction <= stair_total_fraction - 0.1):
    parser.error("--up-fraction must leave at least 0.1 for uphill and downhill stair tiles")
if extra.stop_speed_reward_weight < 0 or (extra.stop_speed_reward_weight and not extra.restart_after_stop):
    parser.error("--stop-speed-reward-weight requires --restart-after-stop and must be nonnegative")
if extra.late_hold_speed_penalty_weight < 0 or (
    extra.late_hold_speed_penalty_weight and not extra.restart_after_stop
):
    parser.error("--late-hold-speed-penalty-weight requires --restart-after-stop and must be nonnegative")
if not 1 <= extra.late_hold_start_step < 100:
    parser.error("--late-hold-start-step must be in [1, 99]")
if not 0 < extra.late_hold_speed_threshold <= 0.15:
    parser.error("--late-hold-speed-threshold must be in (0, 0.15]")
if extra.landing_approach_speed is not None and (
    not extra.stop_on_landing or not 0 < extra.landing_approach_speed < 0.7 or extra.slowdown_distance <= 0
):
    parser.error("--landing-approach-speed requires --stop-on-landing, a speed in (0, 0.7), and positive slowdown distance")
if extra.brake_profile and (not extra.restart_after_stop or extra.landing_approach_speed is not None
                            or extra.brake_distance <= 0 or not 0 < extra.brake_min_speed < 0.7):
    parser.error("--brake-profile requires restart, no fixed approach speed, positive distance and minimum in (0, 0.7)")
if extra.landing_tiles_fraction not in (0.0, 0.1, 0.2):
    parser.error("--landing-tiles-fraction must be 0, 0.1 or 0.2 for the 20-column terrain")
if extra.landing_tiles_fraction and (
    up_fraction < extra.landing_tiles_fraction / 2
    or down_fraction < extra.landing_tiles_fraction / 2
):
    parser.error("Each stair direction must cover its fixed landing-tile fraction")
if not 0.0 <= extra.landing_start_probability <= 1.0:
    parser.error("--landing-start-probability must be in [0, 1]")
if extra.landing_start_probability and (not extra.restart_after_stop or extra.landing_tiles_fraction == 0):
    parser.error("Landing starts require --restart-after-stop and positive --landing-tiles-fraction")
if extra.rollin_start_offset is not None and (
    not 0.2 <= extra.rollin_start_offset <= 1.2
    or extra.landing_start_probability != 1.0
    or extra.landing_tiles_fraction == 0
    or not extra.restart_after_stop
):
    parser.error("Roll-in starts require offset in [0.2, 1.2], fixed landing tiles, probability 1 and restart")
if extra.reset_probe and (extra.landing_tiles_fraction == 0 or extra.landing_start_probability == 0):
    parser.error("--reset-probe requires landing tiles and a positive start probability")
if not (0.05 <= extra.max_stair_rise <= 0.20 and 0.25 <= extra.min_stair_run <= 0.42):
    parser.error("Invalid stair training geometry range")
if (extra.inverse_rough_fraction < 0.0
        or extra.inverse_rough_fraction > extra.rough_replay_fraction
        or abs(extra.inverse_rough_fraction * 20 - round(extra.inverse_rough_fraction * 20)) > 1e-9):
    parser.error("--inverse-rough-fraction must be a 0.05 multiple within rough replay")
if extra.inverse_rough_fraction and not extra.landing_tiles_fraction:
    parser.error("Inverse rough replay requires fixed landing tiles")
if extra.rough_reset_probe and not extra.inverse_rough_fraction:
    parser.error("--rough-reset-probe requires inverse rough replay")
if extra.diverse_replay_commands and not extra.cycle_protocol_v3:
    parser.error("--diverse-replay-commands requires --cycle-protocol-v3")
if extra.replay_command_probe and not extra.diverse_replay_commands:
    parser.error("--replay-command-probe requires --diverse-replay-commands")
if extra.actor_base_lin_vel and not extra.fresh_optimizer:
    parser.error("--actor-base-lin-vel requires --fresh-optimizer")
if extra.wheel_head_only and (not extra.fresh_optimizer or extra.actor_base_lin_vel
                              or not extra.stop_speed_reward_weight):
    parser.error("--wheel-head-only requires fresh 57-D optimizer, no base velocity, and stop-speed reward")
if extra.teacher_anchor_weight < 0:
    parser.error("--teacher-anchor-weight must be nonnegative")
if extra.teacher_anchor_weight and (not extra.fresh_optimizer or extra.actor_base_lin_vel
                                    or not extra.stop_speed_reward_weight
                                    or not extra.diverse_replay_commands):
    parser.error("Teacher anchor requires fresh 57-D PPO, stop-speed reward, and diverse replay commands")
if extra.actor_base_lin_vel and (extra.failure_replay_up is not None or extra.failure_replay_probe):
    parser.error("--actor-base-lin-vel is not implemented with failure-state replay")
if extra.passage_reward_weight < 0 or (extra.passage_reward_weight and not extra.restart_after_stop):
    parser.error("--passage-reward-weight requires --restart-after-stop and must be nonnegative")
if extra.hold_reward_weight < 0 or (extra.hold_reward_weight and not extra.restart_after_stop):
    parser.error("--hold-reward-weight requires --restart-after-stop and must be nonnegative")
if (extra.failure_replay_up is None) != (extra.failure_replay_down is None):
    parser.error("Failure-state replay requires both up and down snapshot files")
if extra.failure_replay_up is not None and (
    extra.landing_tiles_fraction != 0.1 or extra.landing_start_probability != 1.0 or not extra.restart_after_stop
):
    parser.error("Failure-state replay requires fixed landing tiles, probability 1, and restart")
if extra.rollin_start_offset is not None and extra.failure_replay_up is not None:
    parser.error("Physical roll-in and failure-state replay are mutually exclusive")
if extra.failure_replay_probe and extra.failure_replay_up is None:
    parser.error("--failure-replay-probe requires snapshot files")
sys.argv = [sys.argv[0], *passthrough]
if "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" not in passthrough:
    raise ValueError("Stair training requires the B2W rough task")
parent_sha = hashlib.sha256(extra.parent_checkpoint.read_bytes()).hexdigest()
accepted_parent_hashes = {
    "916bf5c5b4e5ca43ecfacd4bde6c5a92b164b9c0a6d5c9257a6c7ed68662febf",  # rough seed 54
    "765fe2a4cd1438ca3e81c387be570473c5dd3f9db656c4f064ec7a903dd802ed",  # rough seed 55
    "64a9646efc52285934170efc623753550f497c34f4e1ab8536a9403c144f1465",  # rough seed 56
    "49c50eabfc3d9ce640dc3cc46fb15f45fb8f071351e53a768afc2a406b474801",  # control57 seed 54
    "f5d7403f98853374b3cdaf6dc329461b29f0f0658e308c0d6a47b890c2371ff2",  # control57 seed 55
    "73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa",  # inverse57 update3000
    "4fac5e083e334790933e2cec755f97f833f52b995bb53b8097120d42bd000c7c",  # payload57 variant B model3098
    "20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17",  # cycle57 A model3000
}
if parent_sha not in accepted_parent_hashes:
    raise ValueError(f"Unexpected parent checkpoint SHA-256: {parent_sha}")
replay_files = {"up": extra.failure_replay_up, "down": extra.failure_replay_down}
replay_data = {}
replay_hashes = {}
for direction, file_path in replay_files.items():
    if file_path is None:
        continue
    raw = file_path.read_bytes()
    data = json.loads(raw)
    geometry = data.get("geometry", {})
    if (data.get("schema") != "b2w_stair_stop_failure_states_v1"
            or data.get("policy_sha256") != parent_sha
            or geometry.get("direction") != direction
            or geometry.get("rise_m") != 0.14 or geometry.get("run_m") != 0.32
            or geometry.get("num_steps") != 6 or not data.get("states")):
        raise ValueError(f"Invalid failure replay snapshots: {file_path}")
    if any(state["base_force_max_n"] > 5 or state["hip_force_max_n"] > 5
           or state["projected_gravity_z"] > -0.5 for state in data["states"]):
        raise ValueError(f"Unsafe capture in failure replay: {file_path}")
    replay_data[direction] = data
    replay_hashes[direction] = hashlib.sha256(raw).hexdigest()
if any("B2W_RL_IsaacSim" in path for path in sys.path):
    raise RuntimeError("A previous B2W project is on sys.path")

from isaaclab.app import AppLauncher

root = Path(__file__).resolve().parents[1]
portable_root = root / ".cache" / "kit"
portable_root.mkdir(parents=True, exist_ok=True)
extensions = root / ".runtime" / "extensions"
trainer = root / "vendor" / "robot_lab" / "scripts" / "reinforcement_learning" / "rsl_rl" / "train.py"
original_app_init = AppLauncher.__init__


def init_with_local_paths(self, *args, **kwargs):
    original_argv = sys.argv[:]
    sys.argv.extend(["--portable-root", str(portable_root), "--ext-folder", str(extensions)])
    try:
        original_app_init(self, *args, **kwargs)
    finally:
        sys.argv = original_argv
    install_task_hooks()


AppLauncher.__init__ = init_with_local_paths
task_hooks_installed = False
applied_policy_noise = {}


def install_task_hooks():
    """Patch task creation only after Isaac Sim has initialized."""
    global task_hooks_installed, applied_policy_noise
    if task_hooks_installed:
        return
    import gymnasium as gym

    from isaaclab.managers import RewardTermCfg as RewTerm
    from isaaclab.managers import TerminationTermCfg as DoneTerm
    from isaaclab.managers import SceneEntityCfg
    from isaaclab.terrains import TerrainGeneratorCfg

    import robot_lab.tasks.manager_based.locomotion.velocity.mdp as mdp
    from stair_terrain import GOAL_X, START_X, TILE_X, TILE_Y, InvertedStairsReplayCfg, RoughReplayCfg, StairFlightCfg

    landing_per_direction = extra.landing_tiles_fraction / 2
    regular_up = up_fraction - landing_per_direction
    regular_down = down_fraction - landing_per_direction
    regular_up_columns = round(20 * regular_up)
    regular_down_columns = round(20 * regular_down)
    landing_columns_per_direction = round(20 * landing_per_direction)
    landing_up_start = regular_up_columns + regular_down_columns
    landing_columns = {
        "up": tuple(range(landing_up_start, landing_up_start + landing_columns_per_direction)),
        "down": tuple(range(landing_up_start + landing_columns_per_direction,
                            landing_up_start + 2 * landing_columns_per_direction)),
    }
    landing_rise = 0.14
    landing_height = 6 * landing_rise
    replay_start_column = int(round(20 * stair_total_fraction))

    def replay_mask(env):
        return env.scene.terrain.terrain_types >= replay_start_column

    def cycle_exclusion_mask(env):
        if extra.diverse_replay_commands:
            return replay_mask(env)
        return torch.zeros(env.num_envs, device=env.device, dtype=torch.bool)

    def reset_base_with_landing_starts(env, env_ids, pose_range, velocity_range):
        """Start selected fixed-geometry tiles on their exit landing, at rest."""
        terrain_type = env.scene.terrain.terrain_types[env_ids]
        up_mask = torch.isin(terrain_type, torch.tensor(landing_columns["up"], device=env.device))
        down_mask = torch.isin(terrain_type, torch.tensor(landing_columns["down"], device=env.device))
        up_ids = env_ids[up_mask]
        down_ids = env_ids[down_mask]
        landing_ids = torch.cat((up_ids, down_ids))
        if extra.landing_start_probability < 1.0 and len(landing_ids):
            choose = torch.rand(len(landing_ids), device=env.device) < extra.landing_start_probability
            landing_ids = landing_ids[choose]
            selected_types = env.scene.terrain.terrain_types[landing_ids]
            up_ids = landing_ids[torch.isin(selected_types, torch.tensor(landing_columns["up"], device=env.device))]
            down_ids = landing_ids[torch.isin(selected_types, torch.tensor(landing_columns["down"], device=env.device))]
        env._b2w_landing_selected = landing_ids.clone()
        regular = env_ids[~torch.isin(env_ids, landing_ids)]
        if len(regular):
            mdp.reset_root_state_uniform(env, regular, pose_range, velocity_range)
        if replay_data:
            robot = env.scene["robot"]
            env._b2w_replay_ids = landing_ids.clone()
            env._b2w_replay_actions = torch.zeros((len(landing_ids), 16), device=env.device)
            env._b2w_replay_root = torch.zeros((len(landing_ids), 13), device=env.device)
            env._b2w_replay_joint_pos = torch.zeros((len(landing_ids), robot.num_joints), device=env.device)
            env._b2w_replay_joint_vel = torch.zeros_like(env._b2w_replay_joint_pos)
            for direction, selected in (("up", up_ids), ("down", down_ids)):
                if len(selected) == 0:
                    continue
                data = replay_data[direction]
                if robot.joint_names != data["joint_names"]:
                    raise RuntimeError(f"Joint order mismatch in {direction} failure replay")
                states = data["states"]
                pick = torch.randint(len(states), (len(selected),), device=env.device)
                samples = [states[index] for index in pick.tolist()]
                root_state = torch.tensor([s["root_state_relative"] for s in samples], device=env.device)
                root_state[:, :3] += env.scene.terrain.env_origins[selected]
                joint_pos = torch.tensor([s["joint_pos"] for s in samples], device=env.device)
                joint_vel = torch.tensor([s["joint_vel"] for s in samples], device=env.device)
                prev_action = torch.tensor([s["previous_action"] for s in samples], device=env.device)
                robot.write_root_state_to_sim(root_state, env_ids=selected)
                robot.write_joint_state_to_sim(joint_pos, joint_vel, env_ids=selected)
                slot = torch.isin(landing_ids, selected)
                env._b2w_replay_actions[slot] = prev_action
                env._b2w_replay_root[slot] = root_state
                env._b2w_replay_joint_pos[slot] = joint_pos
                env._b2w_replay_joint_vel[slot] = joint_vel
            return
        if extra.rollin_start_offset is not None:
            rollin_pose = dict(pose_range)
            rollin_pose.update(x=(extra.rollin_start_offset - 0.1, extra.rollin_start_offset + 0.1),
                               z=(0.0, 0.0))
            mdp.reset_root_state_uniform(env, landing_ids, rollin_pose, velocity_range)
        else:
            for selected, height_offset in ((up_ids, landing_height), (down_ids, -landing_height)):
                if len(selected):
                    landing_pose = dict(pose_range)
                    landing_pose.update(x=(GOAL_X - START_X - 0.95, GOAL_X - START_X - 0.65),
                                        z=(height_offset, height_offset))
                    mdp.reset_root_state_uniform(env, selected, landing_pose, velocity_range)

    def probe_landing_resets(env):
        """Check that landing starts clear the floor and avoid unsafe contacts."""
        observations, _ = env.reset()
        scene = env.unwrapped.scene
        robot = scene["robot"]
        terrain = scene.terrain
        contact = scene["contact_forces"]
        landing_type_ids = torch.tensor(landing_columns["up"] + landing_columns["down"], device=env.unwrapped.device)
        ids = torch.where(torch.isin(terrain.terrain_types, landing_type_ids))[0]
        if len(ids) == 0:
            raise RuntimeError("Reset probe has no landing-tile environments")
        selected = torch.isin(ids, env.unwrapped._b2w_landing_selected)
        relative_z = robot.data.root_pos_w[ids, 2] - terrain.env_origins[ids, 2]
        up_type_ids = torch.tensor(landing_columns["up"], device=env.unwrapped.device)
        height_offset = torch.where(torch.isin(terrain.terrain_types[ids], up_type_ids),
                                    landing_height, -landing_height)
        if extra.rollin_start_offset is not None:
            height_offset.zero_()
        expected = robot.data.default_root_state[ids, 2] + torch.where(selected, height_offset, 0.0)
        height_error = (relative_z - expected).abs().max().item()
        relative_x = robot.data.root_pos_w[ids, 0] - terrain.env_origins[ids, 0]
        rollin_offset_error = None
        if extra.rollin_start_offset is not None:
            rollin_offset_error = float((relative_x[selected] - extra.rollin_start_offset).abs().max().item())
        base_ids = contact.find_bodies("base_link")[0]
        hip_ids = contact.find_bodies(".*_hip")[0]
        unsafe_count = 0
        for _ in range(10):
            actions = torch.zeros((env.unwrapped.num_envs, 16), device=env.unwrapped.device)
            observations, _, terminated, _, _ = env.step(actions)
            forces = contact.data.net_forces_w[ids]
            bad_force = (torch.linalg.vector_norm(forces[:, base_ids], dim=-1) > 5).any(dim=-1)
            bad_force |= (torch.linalg.vector_norm(forces[:, hip_ids], dim=-1) > 5).any(dim=-1)
            bad_tilt = robot.data.projected_gravity_b[ids, 2] > -0.5
            unsafe_count += int((bad_force | bad_tilt | terminated[ids]).sum().item())
        print("B2W_LANDING_RESET_PROBE=" + json.dumps({
            "landing_envs": len(ids), "selected_landing_starts": int(selected.sum().item()),
            "height_error_max_m": height_error,
            "rollin_offset_error_max_m": rollin_offset_error,
            "guaranteed_flat_approach_min_m": round(
                (-6 * 0.42 / 2 - START_X) - (extra.rollin_start_offset + 0.1), 6
            ) if extra.rollin_start_offset is not None else None,
            "unsafe_env_steps_first_10": unsafe_count,
            "observation_finite": bool(torch.isfinite(observations["policy"]).all().item()),
        }), flush=True)
        if (height_error > 1e-3 or (rollin_offset_error is not None and rollin_offset_error > 0.11)
                or unsafe_count or not torch.isfinite(observations["policy"]).all()):
            raise RuntimeError("Landing reset probe failed")

    def probe_inverse_resets(env):
        observations, _ = env.reset()
        scene = env.unwrapped.scene
        ids = torch.where(scene.terrain.terrain_types == 19)[0]
        if len(ids) == 0:
            raise RuntimeError("Reset probe has no inverted-stair environments")
        robot = scene["robot"]
        contact = scene["contact_forces"]
        base_ids = contact.find_bodies("base_link")[0]
        hip_ids = contact.find_bodies(".*_hip")[0]
        unsafe_count = 0
        for _ in range(10):
            actions = torch.zeros((env.unwrapped.num_envs, 16), device=env.unwrapped.device)
            observations, _, terminated, _, _ = env.step(actions)
            forces = contact.data.net_forces_w[ids]
            bad = (torch.linalg.vector_norm(forces[:, base_ids], dim=-1) > 5).any(dim=-1)
            bad |= (torch.linalg.vector_norm(forces[:, hip_ids], dim=-1) > 5).any(dim=-1)
            bad |= robot.data.projected_gravity_b[ids, 2] > -0.5
            unsafe_count += int((bad | terminated[ids]).sum().item())
        print("B2W_INVERSE_RESET_PROBE=" + json.dumps({
            "inverse_envs": len(ids), "unsafe_env_steps_first_10": unsafe_count,
            "observation_finite": bool(torch.isfinite(observations["policy"]).all().item()),
        }), flush=True)
        if unsafe_count or not torch.isfinite(observations["policy"]).all():
            raise RuntimeError("Inverted-stair reset probe failed")

    def probe_failure_replay(env):
        observations, _ = env.reset()
        core = env.unwrapped
        ids = core._b2w_replay_ids
        if len(ids) == 0:
            raise RuntimeError("Failure replay probe has no selected environments")
        robot = core.scene["robot"]
        term = core.command_manager.get_term("base_velocity")
        root_error = (robot.data.root_state_w[ids] - core._b2w_replay_root).abs().max().item()
        joint_error = max((robot.data.joint_pos[ids] - core._b2w_replay_joint_pos).abs().max().item(),
                          (robot.data.joint_vel[ids] - core._b2w_replay_joint_vel).abs().max().item())
        action_error = (observations["policy"][ids, -16:] - core._b2w_replay_actions).abs().max().item()
        holding = bool(((term.phase[ids] == 1) & (term.vel_command_b[ids, 0] == 0)).all().item())
        state = torch.load(extra.parent_checkpoint, map_location="cpu", weights_only=True)["model_state_dict"]
        policy = torch.nn.Sequential(torch.nn.Linear(57, 512), torch.nn.ELU(),
                                     torch.nn.Linear(512, 256), torch.nn.ELU(),
                                     torch.nn.Linear(256, 128), torch.nn.ELU(),
                                     torch.nn.Linear(128, 16)).to(core.device).eval()
        policy.load_state_dict({key.removeprefix("actor."): value for key, value in state.items()
                                if key.startswith("actor.")}, strict=True)
        contact = core.scene["contact_forces"]
        base_ids = contact.find_bodies("base_link")[0]
        hip_ids = contact.find_bodies(".*_hip")[0]
        unsafe_count = 0
        with torch.no_grad():
            for _ in range(10):
                observations, _, terminated, truncated, _ = env.step(policy(observations["policy"]))
                forces = contact.data.net_forces_w[ids]
                bad = (torch.linalg.vector_norm(forces[:, base_ids], dim=-1) > 5).any(dim=-1)
                bad |= (torch.linalg.vector_norm(forces[:, hip_ids], dim=-1) > 5).any(dim=-1)
                bad |= robot.data.projected_gravity_b[ids, 2] > -0.5
                unsafe_count += int((bad | terminated[ids] | truncated[ids]).sum().item())
        result = {"replay_envs": len(ids), "root_error_max": root_error,
                  "joint_error_max": joint_error, "action_observation_error_max": action_error,
                  "all_in_hold_phase": holding, "unsafe_env_steps_first_10": unsafe_count,
                  "observation_finite": bool(torch.isfinite(observations["policy"]).all().item())}
        print("B2W_FAILURE_REPLAY_PROBE=" + json.dumps(result), flush=True)
        if (root_error > 1e-3 or joint_error > 1e-3 or action_error > 1e-4 or not holding
                or unsafe_count or not result["observation_finite"]):
            raise RuntimeError("Failure replay probe failed")

    class LandingStopCommand(mdp.UniformThresholdVelocityCommand):
        """Keep a zero command after first reaching the exit landing."""

        def __init__(self, cfg, env):
            super().__init__(cfg, env)
            self.stop_start_step = torch.full((self.num_envs,), -1, device=self.device, dtype=torch.long)
            self.stop_origin = torch.zeros(self.num_envs, device=self.device)

        def _update_command(self):
            super()._update_command()
            self.stop_start_step[self._env.episode_length_buf == 0] = -1
            progress = self.robot.data.root_pos_w[:, 0] - self._env.scene.terrain.env_origins[:, 0]
            first_arrival = (self.stop_start_step < 0) & (progress >= GOAL_X - START_X)
            self.stop_start_step[first_arrival] = self._env.episode_length_buf[first_arrival]
            self.stop_origin[first_arrival] = progress[first_arrival]
            if extra.brake_profile:
                moving = self.stop_start_step < 0
                self.vel_command_b[moving, 0] = braking_speed(
                    progress[moving], GOAL_X - START_X, 0.7,
                    extra.brake_min_speed, extra.brake_distance)
            elif extra.landing_approach_speed is not None:
                self.vel_command_b[self.stop_start_step < 0, 0] = 0.7
                approaching = (self.stop_start_step < 0) & (progress >= GOAL_X - START_X - extra.slowdown_distance)
                self.vel_command_b[approaching, 0] = extra.landing_approach_speed
            self.vel_command_b[self.stop_start_step >= 0] = 0.0

    class LandingCycleCommand(LandingStopCommand):
        """Restart after a held, safe stop on the exit landing."""

        def __init__(self, cfg, env):
            super().__init__(cfg, env)
            self.phase = torch.zeros(self.num_envs, device=self.device, dtype=torch.int8)
            self.restart_origin = torch.zeros(self.num_envs, device=self.device)

        def _update_command(self):
            super()._update_command()
            self.phase[self._env.episode_length_buf == 0] = 0
            self.phase[(self.stop_start_step >= 0) & (self.phase == 0)] = 1
            progress = self.robot.data.root_pos_w[:, 0] - self._env.scene.terrain.env_origins[:, 0]
            speed = torch.linalg.vector_norm(self.robot.data.root_lin_vel_b[:, :2], dim=-1)
            _, restart, _ = stop_outcome(
                self.phase == 1, self._env.episode_length_buf - self.stop_start_step,
                (progress - self.stop_origin).abs(), speed,
                hold_steps=100, max_drift_m=0.35, max_speed_m_s=0.15)
            self.phase[restart] = 2
            self.restart_origin[restart] = progress[restart]
            self.vel_command_b[self.phase == 2, 0] = 0.7

    class DiverseReplayCycleCommand(LandingCycleCommand):
        """Use the original rough velocity-command distribution on replay tiles."""

        def __init__(self, cfg, env):
            self.replay_command = torch.zeros((env.num_envs, 3), device=env.device)
            super().__init__(cfg, env)

        def _sample_replay(self, env_ids):
            if len(env_ids) == 0:
                return
            command = torch.empty((len(env_ids), 3), device=self.device).uniform_(-1.0, 1.0)
            command[:, :2] *= (torch.linalg.vector_norm(command[:, :2], dim=1) > 0.2).unsqueeze(1)
            standing = torch.rand(len(env_ids), device=self.device) < 0.02
            command[standing] = 0.0
            self.replay_command[env_ids] = command

        def _resample_command(self, env_ids):
            super()._resample_command(env_ids)
            ids = torch.as_tensor(env_ids, device=self.device, dtype=torch.long)
            selected = ids[replay_mask(self._env)[ids]]
            self._sample_replay(selected)
            self.vel_command_b[selected] = self.replay_command[selected]

        def _update_command(self):
            super()._update_command()
            replay = replay_mask(self._env)
            # The baseline rough task samples every 10 seconds at 50 Hz.
            sample = replay & (self._env.episode_length_buf > 0) & (
                self._env.episode_length_buf.remainder(500) == 0)
            self._sample_replay(torch.where(sample)[0])
            self.stop_start_step[replay] = -1
            self.phase[replay] = 0
            self.vel_command_b[replay] = self.replay_command[replay]

    def unsafe_state(env):
        sensor = env.scene["contact_forces"]
        if not hasattr(env, "_b2w_stair_contact_ids"):
            base_ids = sensor.find_bodies("base_link")[0]
            hip_ids = sensor.find_bodies(".*_hip")[0]
            if len(base_ids) != 1 or len(hip_ids) != 4:
                raise RuntimeError("Unexpected B2W contact sensor body order")
            env._b2w_stair_contact_ids = (base_ids, hip_ids)
        base_ids, hip_ids = env._b2w_stair_contact_ids
        forces = sensor.data.net_forces_w
        base_bad = (torch.linalg.vector_norm(forces[:, base_ids], dim=-1) > 5.0).any(dim=-1)
        hip_bad = (torch.linalg.vector_norm(forces[:, hip_ids], dim=-1) > 5.0).any(dim=-1)
        tilt_bad = env.scene["robot"].data.projected_gravity_b[:, 2] > -0.5
        return base_bad | hip_bad | tilt_bad

    def reached_landing(env):
        robot = env.scene["robot"]
        progress = robot.data.root_pos_w[:, 0] - env.scene.terrain.env_origins[:, 0]
        if not extra.stop_on_landing:
            return (progress >= GOAL_X - START_X) & ~unsafe_state(env) & ~cycle_exclusion_mask(env)
        term = env.command_manager.get_term("base_velocity")
        if extra.restart_after_stop:
            return ((term.phase == 2) & (progress >= term.restart_origin + 0.35)
                    & ~unsafe_state(env) & ~cycle_exclusion_mask(env))
        held = (term.stop_start_step >= 0) & (env.episode_length_buf - term.stop_start_step >= 100)
        stopped = (progress - term.stop_origin).abs() <= 0.35
        speed = torch.linalg.vector_norm(robot.data.root_lin_vel_b[:, :2], dim=-1) <= 0.15
        return held & stopped & speed & ~unsafe_state(env) & ~cycle_exclusion_mask(env)

    def safe_first_passage(env):
        """One reward on first safe exit arrival; full-cycle success remains separate."""
        term = env.command_manager.get_term("base_velocity")
        progress = env.scene["robot"].data.root_pos_w[:, 0] - env.scene.terrain.env_origins[:, 0]
        # Reward is computed before command_manager.compute() records first arrival.
        return ((term.stop_start_step < 0) & (progress >= GOAL_X - START_X)
                & ~unsafe_state(env) & ~cycle_exclusion_mask(env))

    def safe_hold_completion(env):
        """One reward at the evaluator-aligned boundary of a successful hold."""
        term = env.command_manager.get_term("base_velocity")
        robot = env.scene["robot"]
        progress = robot.data.root_pos_w[:, 0] - env.scene.terrain.env_origins[:, 0]
        _, completed, _ = stop_outcome(
            (term.phase == 1) & (term.stop_start_step >= 0),
            env.episode_length_buf - term.stop_start_step,
            (progress - term.stop_origin).abs(),
            torch.linalg.vector_norm(robot.data.root_lin_vel_b[:, :2], dim=-1),
            hold_steps=100, max_drift_m=0.35, max_speed_m_s=0.15)
        # Reward is computed before command_manager.compute() advances phase 1 -> 2.
        return completed & ~unsafe_state(env) & ~cycle_exclusion_mask(env)

    def overshot_landing(env):
        term = env.command_manager.get_term("base_velocity")
        progress = env.scene["robot"].data.root_pos_w[:, 0] - env.scene.terrain.env_origins[:, 0]
        holding = term.phase == 1 if extra.restart_after_stop else term.stop_start_step >= 0
        return holding & ((progress - term.stop_origin).abs() > 0.35) & ~cycle_exclusion_mask(env)

    def missed_stop_deadline(env):
        """Fail the stop at the same 100-step boundary used by cycle evaluation."""
        term = env.command_manager.get_term("base_velocity")
        robot = env.scene["robot"]
        progress = robot.data.root_pos_w[:, 0] - env.scene.terrain.env_origins[:, 0]
        _, _, failed = stop_outcome(
            (term.phase == 1) & (term.stop_start_step >= 0),
            env.episode_length_buf - term.stop_start_step,
            (progress - term.stop_origin).abs(),
            torch.linalg.vector_norm(robot.data.root_lin_vel_b[:, :2], dim=-1),
            hold_steps=100, max_drift_m=0.35, max_speed_m_s=0.15)
        return failed & ~cycle_exclusion_mask(env)

    def landing_stability(env):
        robot = env.scene["robot"]
        progress = robot.data.root_pos_w[:, 0] - env.scene.terrain.env_origins[:, 0]
        on_exit = (progress >= GOAL_X - START_X - 1.3) & (progress < GOAL_X - START_X)
        gravity_xy = robot.data.projected_gravity_b[:, :2]
        angular_xy = robot.data.root_ang_vel_b[:, :2]
        stability = torch.exp(-4.0 * torch.sum(gravity_xy.square(), dim=-1)
                              - 0.5 * torch.sum(angular_xy.square(), dim=-1))
        return on_exit.float() * (~unsafe_state(env)).float() * (~cycle_exclusion_mask(env)).float() * stability

    def stop_speed_reward(env):
        term = env.command_manager.get_term("base_velocity")
        holding = (term.phase == 1) & (env.episode_length_buf - term.stop_start_step < 100)
        velocity = env.scene["robot"].data.root_lin_vel_b[:, :2]
        speed_sq = torch.sum(velocity.square(), dim=-1)
        return (holding.float() * (~unsafe_state(env)).float() *
                (~cycle_exclusion_mask(env)).float() * torch.exp(-20.0 * speed_sq))

    def late_hold_speed_penalty(env):
        """Penalize only late-hold speed above the pre-registered safe margin."""
        term = env.command_manager.get_term("base_velocity")
        elapsed = env.episode_length_buf - term.stop_start_step
        return late_hold_speed_excess_squared(
            env.scene["robot"].data.root_lin_vel_b[:, :2],
            term.phase,
            elapsed,
            unsafe_state(env),
            cycle_exclusion_mask(env),
            start_step=extra.late_hold_start_step,
            end_step=100,
            speed_threshold_m_s=extra.late_hold_speed_threshold,
        )

    def stair_levels(env, env_ids):
        """Advance only after a clean landing; lower failed episodes."""
        terrain = env.scene.terrain
        progress = env.scene["robot"].data.root_pos_w[:, 0] - terrain.env_origins[:, 0]
        is_replay = replay_mask(env)[env_ids]
        move_up = reached_landing(env)[env_ids]
        failed_stop = missed_stop_deadline(env)[env_ids] if strict_deadline else False
        move_down = ~move_up & ((progress[env_ids] < GOAL_X - START_X) | unsafe_state(env)[env_ids] | failed_stop)
        if extra.diverse_replay_commands and bool(is_replay.any()):
            distance = torch.linalg.vector_norm(
                env.scene["robot"].data.root_pos_w[env_ids, :2] - terrain.env_origins[env_ids, :2], dim=1)
            command = env.command_manager.get_command("base_velocity")[env_ids, :2]
            replay_up = distance > terrain.cfg.terrain_generator.size[0] / 2
            replay_down = distance < torch.linalg.vector_norm(command, dim=1) * env.max_episode_length_s * 0.5
            replay_down &= ~replay_up
            move_up = torch.where(is_replay, replay_up, move_up)
            move_down = torch.where(is_replay, replay_down, move_down)
        terrain.update_env_origins(env_ids, move_up, move_down)
        return torch.mean(terrain.terrain_levels.float())

    original_make = gym.make

    def make_stair_task(task, *args, **kwargs):
        global applied_policy_noise
        if task == "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0":
            configure_ground_plane()
            cfg = configure_b2w_env(kwargs["cfg"])
            if extra.actor_base_lin_vel:
                enable_policy_base_lin_vel(cfg)
            applied_policy_noise = {}
            for term_name in ("base_lin_vel", "base_ang_vel", "projected_gravity", "joint_pos", "joint_vel"):
                term = getattr(cfg.observations.policy, term_name, None)
                noise = getattr(term, "noise", None) if term is not None else None
                if noise is None:
                    continue
                noise.n_min *= extra.observation_noise_scale
                noise.n_max *= extra.observation_noise_scale
                applied_policy_noise[term_name] = [noise.n_min, noise.n_max]
            sub_terrains = {
                "stairs_up": StairFlightCfg(proportion=regular_up, direction="up", min_rise=0.05,
                                             max_rise=extra.max_stair_rise, min_run=extra.min_stair_run, max_run=0.42),
                "stairs_down": StairFlightCfg(proportion=regular_down, direction="down", min_rise=0.05,
                                               max_rise=extra.max_stair_rise, min_run=extra.min_stair_run, max_run=0.42),
            }
            if extra.landing_tiles_fraction:
                if extra.rollin_start_offset is not None:
                    sub_terrains.update({
                        "landing_up": StairFlightCfg(
                            proportion=landing_per_direction, direction="up", min_rise=0.05,
                            max_rise=extra.max_stair_rise, min_run=extra.min_stair_run, max_run=0.42),
                        "landing_down": StairFlightCfg(
                            proportion=landing_per_direction, direction="down", min_rise=0.05,
                            max_rise=extra.max_stair_rise, min_run=extra.min_stair_run, max_run=0.42),
                    })
                else:
                    sub_terrains.update({
                        "landing_up": StairFlightCfg(proportion=landing_per_direction, direction="up", min_rise=landing_rise,
                                                      max_rise=landing_rise, min_run=0.32, max_run=0.32),
                        "landing_down": StairFlightCfg(proportion=landing_per_direction, direction="down", min_rise=landing_rise,
                                                        max_rise=landing_rise, min_run=0.32, max_run=0.32),
                    })
            sub_terrains.update({
                "flat_replay": StairFlightCfg(proportion=0.15, direction="up", min_rise=0.0,
                                              max_rise=0.0, min_run=0.32, max_run=0.32),
                "rough_replay": RoughReplayCfg(proportion=extra.rough_replay_fraction - extra.inverse_rough_fraction,
                                               noise_range=(0.02, 0.10),
                                               noise_step=0.02, border_width=0.25),
            })
            if extra.inverse_rough_fraction:
                sub_terrains["inverse_rough_replay"] = InvertedStairsReplayCfg(
                    proportion=extra.inverse_rough_fraction, step_height_range=(0.05, 0.23),
                    step_width=0.3, platform_width=3.0, border_width=1.0, holes=False)
            cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
                seed=cfg.seed,
                size=(TILE_X, TILE_Y),
                border_width=2.0,
                num_rows=10,
                num_cols=20,
                curriculum=True,
                use_cache=False,
                sub_terrains=sub_terrains,
            )
            cfg.scene.terrain.max_init_terrain_level = 2
            cfg.curriculum.terrain_levels.func = stair_levels
            cfg.terminations.terrain_out_of_bounds = None
            cfg.terminations.illegal_contact = DoneTerm(
                func=mdp.illegal_contact,
                params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=["base_link", ".*_hip"]),
                        "threshold": 5.0},
            )
            if extra.cycle_protocol_v3:
                cfg.terminations.stair_unsafe = DoneTerm(func=unsafe_state)
            cfg.terminations.stair_goal = DoneTerm(func=reached_landing)
            cfg.rewards.stair_goal = RewTerm(func=reached_landing, weight=250.0)
            if extra.passage_reward_weight:
                cfg.rewards.safe_passage = RewTerm(func=safe_first_passage, weight=extra.passage_reward_weight)
            if extra.hold_reward_weight:
                cfg.rewards.safe_hold = RewTerm(func=safe_hold_completion, weight=extra.hold_reward_weight)
            if extra.stop_on_landing:
                if extra.diverse_replay_commands:
                    cfg.commands.base_velocity.class_type = DiverseReplayCycleCommand
                else:
                    cfg.commands.base_velocity.class_type = LandingCycleCommand if extra.restart_after_stop else LandingStopCommand
                cfg.commands.base_velocity.resampling_time_range = (1000.0, 1000.0)
                if not extra.cycle_protocol_v3:
                    cfg.terminations.stop_overshoot = DoneTerm(func=overshot_landing)
            if strict_deadline:
                cfg.terminations.stop_deadline = DoneTerm(func=missed_stop_deadline)
            if extra.landing_stability_weight:
                cfg.rewards.landing_stability = RewTerm(
                    func=landing_stability, weight=extra.landing_stability_weight)
            if extra.stop_speed_reward_weight:
                cfg.rewards.stop_speed = RewTerm(func=stop_speed_reward, weight=extra.stop_speed_reward_weight)
            if extra.late_hold_speed_penalty_weight:
                cfg.rewards.late_hold_speed = RewTerm(
                    func=late_hold_speed_penalty,
                    weight=-extra.late_hold_speed_penalty_weight,
                )
            cfg.commands.base_velocity.heading_command = False
            cfg.commands.base_velocity.rel_standing_envs = 0.0
            cfg.commands.base_velocity.rel_heading_envs = 0.0
            cfg.commands.base_velocity.ranges.lin_vel_x = (0.7, 0.7)
            cfg.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
            cfg.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)
            pose = cfg.events.randomize_reset_base.params["pose_range"]
            pose.update(x=(-0.05, 0.05), y=(-0.15, 0.15), z=(0.0, 0.0),
                        roll=(-0.1, 0.1), pitch=(-0.1, 0.1), yaw=(-0.15, 0.15))
            velocity = cfg.events.randomize_reset_base.params["velocity_range"]
            velocity.update({axis: (0.0, 0.0) for axis in velocity})
            if extra.landing_tiles_fraction:
                cfg.events.randomize_reset_base.func = reset_base_with_landing_starts
            print("B2W_STAIR_TASK=" + json.dumps({
                "rows": 10, "columns": 20, "up_fraction": up_fraction, "down_fraction": down_fraction,
                "flat_fraction": 0.15, "rough_fraction": extra.rough_replay_fraction,
                "rise_range_m": [0.05, extra.max_stair_rise],
                "run_range_m": [extra.min_stair_run, 0.42], "steps_per_flight": 6,
                "goal_bonus_weight": 250.0, "command_vx_m_s": 0.7,
                "safe_goal_and_curriculum": True,
                "landing_stability_weight": extra.landing_stability_weight,
                "stop_on_landing": extra.stop_on_landing,
                "restart_after_stop": extra.restart_after_stop,
                "strict_stop_deadline": strict_deadline,
                "cycle_protocol": "v3" if extra.cycle_protocol_v3 else "legacy",
                "actor_observation_dim": 60 if extra.actor_base_lin_vel else 57,
                "actor_base_lin_vel": extra.actor_base_lin_vel,
                "observation_noise_scale": extra.observation_noise_scale,
                "policy_observation_noise_ranges": applied_policy_noise,
                "stop_hold_steps": 100 if extra.stop_on_landing else None,
                "stop_speed_reward_weight": extra.stop_speed_reward_weight,
                "late_hold_speed_penalty": {
                    "weight": -extra.late_hold_speed_penalty_weight,
                    "start_step": extra.late_hold_start_step,
                    "end_step": 100,
                    "speed_threshold_m_s": extra.late_hold_speed_threshold,
                } if extra.late_hold_speed_penalty_weight else None,
                "landing_approach_speed_m_s": extra.landing_approach_speed,
                "slowdown_distance_m": extra.slowdown_distance if extra.landing_approach_speed is not None else None,
                "brake_profile": extra.brake_profile,
                "brake_distance_m": extra.brake_distance if extra.brake_profile else None,
                "brake_min_speed_m_s": extra.brake_min_speed if extra.brake_profile else None,
                "landing_tiles_fraction": extra.landing_tiles_fraction,
                "landing_start_probability": extra.landing_start_probability,
                "rollin_start_offset_m": extra.rollin_start_offset,
                "inverse_rough_fraction": extra.inverse_rough_fraction,
                "diverse_replay_commands": extra.diverse_replay_commands,
                "replay_command_ranges": {"vx": [-1.0, 1.0], "vy": [-1.0, 1.0],
                                           "yaw": [-1.0, 1.0], "standing_fraction": 0.02}
                    if extra.diverse_replay_commands else None,
                "passage_reward_weight": extra.passage_reward_weight,
                "hold_reward_weight": extra.hold_reward_weight,
                "failure_replay_sha256": replay_hashes,
                "parent_sha256": parent_sha,
            }), flush=True)
        env = original_make(task, *args, **kwargs)
        if task == "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" and replay_data:
            manager = env.unwrapped.action_manager
            original_action_reset = manager.reset

            def reset_actions_with_replay(env_ids=None):
                result = original_action_reset(env_ids)
                ids = getattr(env.unwrapped, "_b2w_replay_ids", torch.empty(0, device=env.unwrapped.device, dtype=torch.long))
                if len(ids):
                    manager._action[ids] = env.unwrapped._b2w_replay_actions
                    manager._prev_action[ids] = env.unwrapped._b2w_replay_actions
                return result

            manager.reset = reset_actions_with_replay
            commands = env.unwrapped.command_manager
            original_command_reset = commands.reset

            def reset_commands_with_replay(env_ids=None):
                result = original_command_reset(env_ids)
                ids = getattr(env.unwrapped, "_b2w_replay_ids", torch.empty(0, device=env.unwrapped.device, dtype=torch.long))
                if len(ids):
                    term = commands.get_term("base_velocity")
                    progress = env.unwrapped.scene["robot"].data.root_pos_w[ids, 0] - env.unwrapped.scene.terrain.env_origins[ids, 0]
                    term.stop_start_step[ids] = 0
                    term.stop_origin[ids] = progress
                    term.phase[ids] = 1
                    term.vel_command_b[ids] = 0.0
                return result

            commands.reset = reset_commands_with_replay
        if task == "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" and extra.reset_probe:
            probe_landing_resets(env)
        if task == "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" and extra.rough_reset_probe:
            probe_inverse_resets(env)
        if task == "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" and extra.failure_replay_probe:
            probe_failure_replay(env)
        if task == "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" and extra.replay_command_probe:
            observations, _ = env.reset()
            core = env.unwrapped
            mask = replay_mask(core)
            command = core.command_manager.get_command("base_velocity")
            result = {
                "replay_envs": int(mask.sum().item()),
                "stair_envs": int((~mask).sum().item()),
                "replay_abs_vy_max": float(command[mask, 1].abs().max().item()),
                "replay_abs_yaw_max": float(command[mask, 2].abs().max().item()),
                "replay_vx_min": float(command[mask, 0].min().item()),
                "replay_vx_max": float(command[mask, 0].max().item()),
                "stair_abs_vy_yaw_max": float(command[~mask, 1:].abs().max().item()),
                "observation_finite": bool(torch.isfinite(observations["policy"]).all().item()),
            }
            print("B2W_REPLAY_COMMAND_PROBE=" + json.dumps(result), flush=True)
            if (not result["replay_envs"] or result["replay_abs_vy_max"] < 0.5
                    or result["replay_abs_yaw_max"] < 0.5 or result["replay_vx_min"] > -0.5
                    or result["replay_vx_max"] < 0.5 or result["stair_abs_vy_yaw_max"] > 1e-6
                    or not result["observation_finite"]):
                raise RuntimeError("Replay command probe failed")
        return env

    gym.make = make_stair_task
    task_hooks_installed = True

sys.path.insert(0, str(trainer.parent))
import cli_args

original_update_cfg = cli_args.update_rsl_rl_cfg


def update_agent_cfg(agent_cfg, args_cli):
    agent_cfg = original_update_cfg(agent_cfg, args_cli)
    agent_cfg.experiment_name = "unitree_b2w_stair"
    agent_cfg.save_interval = extra.save_interval
    agent_cfg.policy.init_noise_std = 0.1
    agent_cfg.algorithm.learning_rate = extra.learning_rate
    agent_cfg.algorithm.schedule = "fixed"
    agent_cfg.algorithm.entropy_coef = 0.0
    agent_cfg.algorithm.clip_param = 0.1
    return agent_cfg


cli_args.update_rsl_rl_cfg = update_agent_cfg

from rsl_rl.runners import OnPolicyRunner

original_runner_init = OnPolicyRunner.__init__


def init_from_rough(self, env, train_cfg, log_dir=None, device="cpu"):
    original_runner_init(self, env, copy.deepcopy(train_cfg), log_dir=log_dir, device=device)
    source = torch.load(extra.parent_checkpoint, map_location="cpu", weights_only=True)
    if extra.fresh_optimizer:
        source_state = source["model_state_dict"]
        target_state = self.alg.policy.state_dict()
        if extra.actor_base_lin_vel:
            target_state = expand_actor_for_base_lin_vel(source_state, target_state)
        else:
            if set(source_state) != set(target_state):
                raise RuntimeError("Parent and control policy state keys differ")
            target_state = source_state
        self.alg.policy.load_state_dict(target_state, strict=True)
        self.current_learning_iteration = source["iter"]
        print(f"B2W_STAIR_PARENT_WEIGHTS_LOADED fresh_optimizer=true iteration={source['iter']}", flush=True)
    else:
        self.load(str(extra.parent_checkpoint.resolve()), load_optimizer=True)
    self.alg.learning_rate = extra.learning_rate
    for group in self.alg.optimizer.param_groups:
        group["lr"] = extra.learning_rate
    self.alg.policy.std.requires_grad_(False)
    wheel_head_manifest = None
    if extra.wheel_head_only:
        wheel_head_manifest = configure_wheel_head_only(self.alg.policy)
        print("B2W_WHEEL_HEAD_ONLY=" + json.dumps(wheel_head_manifest), flush=True)
    teacher_anchor_manifest = None
    if extra.teacher_anchor_weight:
        teacher_anchor_manifest = install_moving_teacher_anchor(
            self.alg, weight=extra.teacher_anchor_weight, max_samples=8192)
        print("B2W_TEACHER_ANCHOR=" + json.dumps(teacher_anchor_manifest), flush=True)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    (Path(log_dir) / "stair_parent.json").write_text(json.dumps({
        "source_checkpoint": str(extra.parent_checkpoint.resolve()),
        "source_sha256": parent_sha,
        "code_sha256": {name: hashlib.sha256((root / "scripts" / name).read_bytes()).hexdigest()
                        for name in ("train_stair_b2w.py", "stair_cycle_protocol.py",
                                     "stair_command_profile.py", "stair_terrain.py",
                                     "wheel_head_training.py", "moving_teacher_anchor.py",
                                     "hold_tail_reward.py")},
        "actor_critic_optimizer": "weights_resumed_optimizer_fresh" if extra.fresh_optimizer else "resumed",
        "actor_observation_dim": 60 if extra.actor_base_lin_vel else 57,
        "actor_base_lin_vel": extra.actor_base_lin_vel,
        "wheel_head_only": extra.wheel_head_only,
        "wheel_head_training": wheel_head_manifest,
        "teacher_anchor_weight": extra.teacher_anchor_weight,
        "teacher_anchor": teacher_anchor_manifest,
        "optimizer_learning_rates": [group["lr"] for group in self.alg.optimizer.param_groups],
        "fixed_learning_rate": extra.learning_rate,
        "save_interval_updates": extra.save_interval,
        "observation_noise_scale": extra.observation_noise_scale,
        "policy_observation_noise_ranges": applied_policy_noise,
        "exploration_std_values": self.alg.policy.std.detach().cpu().tolist(),
        "exploration_std": "restored_from_parent_then_frozen",
        "safe_goal_and_curriculum": True,
        "landing_stability_weight": extra.landing_stability_weight,
        "stop_on_landing": extra.stop_on_landing,
        "restart_after_stop": extra.restart_after_stop,
        "strict_stop_deadline": strict_deadline,
        "cycle_protocol": "v3" if extra.cycle_protocol_v3 else "legacy",
        "rough_replay_fraction": extra.rough_replay_fraction,
        "up_fraction": up_fraction,
        "down_fraction": down_fraction,
        "stop_speed_reward_weight": extra.stop_speed_reward_weight,
        "late_hold_speed_penalty": {
            "weight": -extra.late_hold_speed_penalty_weight,
            "start_step": extra.late_hold_start_step,
            "end_step": 100,
            "speed_threshold_m_s": extra.late_hold_speed_threshold,
        } if extra.late_hold_speed_penalty_weight else None,
        "landing_approach_speed_m_s": extra.landing_approach_speed,
        "slowdown_distance_m": extra.slowdown_distance if extra.landing_approach_speed is not None else None,
        "brake_profile": extra.brake_profile,
        "brake_distance_m": extra.brake_distance if extra.brake_profile else None,
        "brake_min_speed_m_s": extra.brake_min_speed if extra.brake_profile else None,
        "landing_tiles_fraction": extra.landing_tiles_fraction,
        "landing_start_probability": extra.landing_start_probability,
        "rollin_start_offset_m": extra.rollin_start_offset,
        "max_stair_rise_m": extra.max_stair_rise,
        "min_stair_run_m": extra.min_stair_run,
        "inverse_rough_fraction": extra.inverse_rough_fraction,
        "diverse_replay_commands": extra.diverse_replay_commands,
        "passage_reward_weight": extra.passage_reward_weight,
        "hold_reward_weight": extra.hold_reward_weight,
        "failure_replay_sha256": replay_hashes,
        "failure_replay_state_count": {direction: len(data["states"]) for direction, data in replay_data.items()},
    }, indent=2), encoding="utf-8")
    print(f"B2W_STAIR_PARENT_LOADED sha256={parent_sha}", flush=True)


OnPolicyRunner.__init__ = init_from_rough
sys.argv = [str(trainer), *sys.argv[1:]]
runpy.run_path(str(trainer), run_name="__main__")
