"""Run a selected B2W policy with matching flat or rough Isaac Sim physics."""

import argparse
import ctypes
import json
import os
import socket
import sys
import time
from pathlib import Path

if any("B2W_RL_IsaacSim" in path for path in sys.path):
    raise RuntimeError("A previous B2W project is on sys.path")

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
model = parser.add_mutually_exclusive_group(required=True)
model.add_argument("--policy", type=Path, help="Exported 57-to-16 TorchScript actor")
model.add_argument("--checkpoint", type=Path, help="RSL-RL checkpoint with a 57-to-16 actor")
parser.add_argument("--terrain", choices=("flat", "rough", "stair", "map"), required=True)
parser.add_argument("--terrain-family", default="random_rough")
parser.add_argument("--terrain-level", type=int, default=9)
parser.add_argument("--seed", type=int, default=2002)
parser.add_argument("--device", choices=("cpu", "cuda:0"), default="cuda:0")
parser.add_argument("--stair-direction", choices=("up", "down"), default="up")
parser.add_argument("--stair-rise", type=float, default=0.14)
parser.add_argument("--stair-run", type=float, default=0.32)
parser.add_argument("--stair-steps", type=int, default=6)
parser.add_argument("--terrain-mesh-file", type=Path)
parser.add_argument("--steps", type=int, default=0, help="Stop after this many policy steps (0: keep running)")
parser.add_argument("--telemetry-port", type=int, default=29781)
args = parser.parse_args()
model_path = args.policy or args.checkpoint
if not model_path.is_file():
    parser.error(f"Model not found: {model_path}")
if not 0 <= args.terrain_level <= 9:
    parser.error("--terrain-level must be from 0 to 9")
if args.terrain_mesh_file and args.terrain == "flat":
    parser.error("--terrain-mesh-file requires --terrain rough, stair or map")
if args.terrain == "stair" and not (0.03 <= args.stair_rise <= 0.25 and 0.20 <= args.stair_run <= 0.6
                                    and 1 <= args.stair_steps <= 8 and args.stair_steps * args.stair_run <= 3.0):
    parser.error("Stair geometry is outside the tested scene bounds")

from isaaclab.app import AppLauncher

portable_root = ROOT / ".cache/kit-gamepad"
portable_root.mkdir(parents=True, exist_ok=True)
extensions = ROOT / ".runtime/extensions"
sys.argv = [sys.argv[0], "--portable-root", str(portable_root), "--ext-folder", str(extensions)]
launcher = AppLauncher({
    "headless": True,
})
simulation_app = launcher.app

import gymnasium as gym
import numpy as np
import torch

import robot_lab.tasks  # noqa: F401
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab_tasks.utils import parse_env_cfg

from local_b2w_assets import configure_b2w_env, configure_ground_plane


class XInputPad(ctypes.Structure):
    _fields_ = [("buttons", ctypes.c_ushort), ("left_trigger", ctypes.c_ubyte),
                ("right_trigger", ctypes.c_ubyte), ("left_x", ctypes.c_short),
                ("left_y", ctypes.c_short), ("right_x", ctypes.c_short),
                ("right_y", ctypes.c_short)]


class XInputState(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_ulong), ("pad", XInputPad)]


class XInputGamepad:
    """Read controller 0 directly, including in headless Isaac Sim."""

    def __init__(self, device):
        self.device = device
        self.dll = ctypes.WinDLL("xinput1_4")
        self.dll.XInputGetState.argtypes = [ctypes.c_ulong, ctypes.POINTER(XInputState)]
        self.dll.XInputGetState.restype = ctypes.c_ulong
        self.state = XInputState()
        self.command = [0.0, 0.0, 0.0]
        self.reset_requested = False
        self.previous_buttons = 0
        if self.dll.XInputGetState(0, ctypes.byref(self.state)) != 0:
            raise RuntimeError("XInput controller 0 is not connected")

    def advance(self):
        if self.dll.XInputGetState(0, ctypes.byref(self.state)) != 0:
            self.command = [0.0, 0.0, 0.0]
            return torch.zeros(3, device=self.device)

        def axis(value):
            normalized = max(-1.0, min(1.0, value / 32767.0))
            return normalized if abs(normalized) >= 0.10 else 0.0

        pad = self.state.pad
        if pad.buttons & 0x1000 and not self.previous_buttons & 0x1000:
            self.reset_requested = True
        self.previous_buttons = pad.buttons
        # XInput right is +X, while Isaac robot +Y and +yaw point left.
        self.command = [axis(pad.left_y), -axis(pad.left_x), -axis(pad.right_x)]
        return torch.tensor(self.command,
                            dtype=torch.float32, device=self.device)


def main():
    # Small single-robot tensors do not benefit from CPU thread-pool overhead.
    torch.set_num_threads(1)
    task_terrain = "rough" if args.terrain in ("stair", "map") else args.terrain
    task = f"RobotLab-Isaac-Velocity-{task_terrain.capitalize()}-Unitree-B2W-v0"
    cfg = parse_env_cfg(task, device=args.device, num_envs=1, use_fabric=True)
    cfg.seed = args.seed
    if args.terrain == "map":
        terrain = cfg.scene.terrain.terrain_generator
        terrain.seed = args.seed
        terrain.num_rows, terrain.num_cols = 10, 20
        # Retain upstream families/proportions; rows span increasing difficulty.
        terrain.curriculum = True
        terrain.difficulty_range = (0.0, 1.0)
        terrain.border_width = 20.0
        cfg.scene.terrain.max_init_terrain_level = 0
        cfg.curriculum.terrain_levels = None
    elif args.terrain == "stair":
        from isaaclab.terrains import TerrainGeneratorCfg
        from stair_terrain import TILE_X, TILE_Y, StairFlightCfg

        cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
            seed=args.seed, size=(TILE_X, TILE_Y), border_width=2.0,
            num_rows=1, num_cols=1, curriculum=False, use_cache=False,
            sub_terrains={"stair_flight": StairFlightCfg(
                direction=args.stair_direction, min_rise=args.stair_rise,
                max_rise=args.stair_rise, min_run=args.stair_run,
                max_run=args.stair_run, num_steps=args.stair_steps)},
        )
        cfg.scene.terrain.max_init_terrain_level = 0
        cfg.curriculum.terrain_levels = None
        cfg.terminations.terrain_out_of_bounds = None
    elif args.terrain == "rough":
        terrain = cfg.scene.terrain.terrain_generator
        if args.terrain_family not in terrain.sub_terrains:
            raise ValueError(f"Unknown rough terrain family {args.terrain_family!r}; choose from {list(terrain.sub_terrains)}")
        terrain.sub_terrains = {args.terrain_family: terrain.sub_terrains[args.terrain_family]}
        terrain.seed = args.seed
        terrain.num_rows = terrain.num_cols = 1
        terrain.curriculum = False
        difficulty = (args.terrain_level + 0.5) / 10.0
        terrain.difficulty_range = (difficulty, difficulty)
        terrain.border_width = 1.0
        cfg.scene.terrain.max_init_terrain_level = 0
        cfg.curriculum.terrain_levels = None
    cfg.observations.policy.enable_corruption = False
    # Playback needs only the blind actor observation. Critic scans and reward
    # terms do not affect the physics or actions, but cost time every step.
    cfg.observations.critic = None
    cfg.rewards = None
    cfg.scene.height_scanner = None
    cfg.scene.height_scanner_base = None
    if cfg.terminations.illegal_contact is None:
        cfg.scene.contact_forces = None
    cfg.events.randomize_apply_external_force_torque = None
    cfg.events.push_robot = None
    cfg.terminations.time_out = None
    cfg.commands.base_velocity.debug_vis = False
    pose = cfg.events.randomize_reset_base.params["pose_range"]
    pose.update(x=(0.0, 0.0), y=(0.0, 0.0), z=(0.0, 0.0),
                roll=(0.0, 0.0), pitch=(0.0, 0.0), yaw=(0.0, 0.0))
    velocity = cfg.events.randomize_reset_base.params["velocity_range"]
    velocity.update({axis: (0.0, 0.0) for axis in velocity})
    gamepad = XInputGamepad(cfg.sim.device)
    cfg.observations.policy.velocity_commands = ObsTerm(
        func=lambda env: gamepad.advance().unsqueeze(0),
    )
    if args.terrain != "flat" and args.terrain_mesh_file:
        # Capture the exact mesh passed to PhysX for the external OpenGL viewer.
        from isaaclab.terrains import TerrainImporter

        original_import_mesh = TerrainImporter.import_mesh

        def import_mesh_and_record(importer, name, mesh):
            if name == "terrain":
                target = args.terrain_mesh_file.resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(target.suffix + ".tmp")
                with temporary.open("wb") as stream:
                    np.savez_compressed(stream, vertices=mesh.vertices, faces=mesh.faces)
                os.replace(temporary, target)
                print(f"TERRAIN_MESH={target} TRIANGLES={len(mesh.faces)}", flush=True)
            return original_import_mesh(importer, name, mesh)

        TerrainImporter.import_mesh = import_mesh_and_record
    configure_ground_plane()
    configure_b2w_env(cfg)

    env = gym.make(task, cfg=cfg)
    telemetry = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if args.terrain == "map":
            # Flat apron next to the easiest row, facing into the full map.
            terrain = env.unwrapped.scene.terrain
            terrain.env_origins[:] = torch.tensor(
                [-0.5 * cfg.scene.terrain.terrain_generator.size[0] * 10 - 3.0, 0.0, 0.0],
                device=env.unwrapped.device,
            )
            print("MAP: 10x20 upstream tiles, 80x160 m + 20 m flat border; spawn on apron", flush=True)
        observations, _ = env.reset()
        terms = list(env.unwrapped.observation_manager.active_terms["policy"])
        expected = ["base_ang_vel", "projected_gravity", "velocity_commands",
                    "joint_pos", "joint_vel", "actions"]
        if terms != expected or observations["policy"].shape != (1, 57):
            raise RuntimeError(f"Unexpected policy observation contract: {terms}, {observations['policy'].shape}")
        if env.action_space.shape != (1, 16):
            raise RuntimeError(f"Unexpected action contract: {env.action_space.shape}")
        if args.policy:
            policy = torch.jit.load(str(args.policy), map_location=env.unwrapped.device).eval()
        else:
            state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)["model_state_dict"]
            policy = torch.nn.Sequential(
                torch.nn.Linear(57, 512), torch.nn.ELU(),
                torch.nn.Linear(512, 256), torch.nn.ELU(),
                torch.nn.Linear(256, 128), torch.nn.ELU(),
                torch.nn.Linear(128, 16),
            )
            policy.load_state_dict(
                {key.removeprefix("actor."): value for key, value in state.items() if key.startswith("actor.")},
                strict=True,
            )
            policy = policy.to(env.unwrapped.device).eval()
        with torch.inference_mode():
            probe = policy(torch.zeros((1, 57), device=env.unwrapped.device))
        if probe.shape != (1, 16) or not torch.isfinite(probe).all():
            raise RuntimeError("Policy output contract failed")
        print(f"READY: {args.terrain} B2W, model={model_path}, seed={args.seed}, "
              f"family={args.terrain_family if args.terrain == 'rough' else ('all_upstream' if args.terrain == 'map' else ('stair_flight' if args.terrain == 'stair' else 'plane'))}, "
              f"level={args.terrain_level if args.terrain == 'rough' else 0}", flush=True)
        print("GAMEPAD: XInput controller 0 connected", flush=True)
        print("Left stick: forward/back and lateral. Right stick: yaw. A: reset to start.", flush=True)
        print(f"TELEMETRY_PORT={args.telemetry_port}", flush=True)
        dt = env.unwrapped.step_dt
        print(f"PLAYBACK_DEVICE={args.device} POLICY_DT={dt} PHYSICS_DT={cfg.sim.dt}", flush=True)
        robot = env.unwrapped.scene["robot"]
        step = 0
        report_time = time.perf_counter()
        compute_seconds = 0.0
        next_step = report_time
        while simulation_app.is_running():
            start = time.perf_counter()
            with torch.inference_mode():
                if gamepad.reset_requested:
                    gamepad.reset_requested = False
                    observations, _ = env.reset()
                    print(f"GAMEPAD_RESET STEP={step}", flush=True)
                action = policy(observations["policy"])
                if not torch.isfinite(action).all():
                    raise RuntimeError("Non-finite policy action")
                observations, _, _, _, _ = env.step(action)
            step += 1
            packed = torch.cat((robot.data.root_pos_w[0], robot.data.root_quat_w[0],
                                robot.data.body_pos_w[0].reshape(-1),
                                robot.data.body_quat_w[0].reshape(-1))).cpu().tolist()
            count = len(robot.body_names)
            body_pos = [packed[7 + 3 * i:10 + 3 * i] for i in range(count)]
            body_quat = [packed[7 + 3 * count + 4 * i:11 + 3 * count + 4 * i] for i in range(count)]
            snapshot = {
                "step": step,
                "wall_time": time.perf_counter(),
                "policy_dt": dt,
                "root_pos": packed[:3],
                "root_quat": packed[3:7],
                "bodies": dict(zip(robot.body_names, body_pos)),
                "body_quats": dict(zip(robot.body_names, body_quat)),
                "command": gamepad.command,
            }
            telemetry.sendto(json.dumps(snapshot).encode("utf-8"), ("127.0.0.1", args.telemetry_port))
            compute_seconds += time.perf_counter() - start
            if step % 100 == 0:
                print(f"STEP={step} POS={packed[:3]} COMMAND={gamepad.command}", flush=True)
                wall_seconds = time.perf_counter() - report_time
                print(f"PERF: policy_hz={100 / wall_seconds:.1f} realtime={100 * dt / wall_seconds:.3f} "
                      f"compute_ms={compute_seconds * 10:.2f}", flush=True)
                report_time = time.perf_counter()
                compute_seconds = 0.0
            if args.steps and step >= args.steps:
                break
            next_step += dt
            delay = next_step - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            elif delay < -dt:
                next_step = time.perf_counter()
    finally:
        telemetry.close()
        env.close()


try:
    main()
finally:
    simulation_app.close()
