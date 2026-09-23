"""Run flat B2W physics and gamepad inference in Isaac Sim without RTX rendering."""

import argparse
import ctypes
import json
import socket
import sys
import time
from pathlib import Path

if any("B2W_RL_IsaacSim" in path for path in sys.path):
    raise RuntimeError("A previous B2W project is on sys.path")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = (
    ROOT / ".cache/h/logs/qualification/flat_reference_qualification_20260919_resume1"
    "/seed54/export/policy-contract-export/policy.pt"
)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
parser.add_argument("--steps", type=int, default=0, help="Stop after this many policy steps (0: keep running)")
parser.add_argument("--telemetry-port", type=int, default=29781)
args = parser.parse_args()
if not args.policy.is_file():
    parser.error(f"Policy not found: {args.policy}")

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
        if self.dll.XInputGetState(0, ctypes.byref(self.state)) != 0:
            raise RuntimeError("XInput controller 0 is not connected")

    def advance(self):
        if self.dll.XInputGetState(0, ctypes.byref(self.state)) != 0:
            return torch.zeros(3, device=self.device)

        def axis(value):
            normalized = max(-1.0, min(1.0, value / 32767.0))
            return normalized if abs(normalized) >= 0.10 else 0.0

        pad = self.state.pad
        # XInput right is +X, while Isaac robot +Y and +yaw point left.
        return torch.tensor([axis(pad.left_y), -axis(pad.left_x), -axis(pad.right_x)],
                            dtype=torch.float32, device=self.device)


def main():
    task = "RobotLab-Isaac-Velocity-Flat-Unitree-B2W-v0"
    cfg = parse_env_cfg(task, device="cuda:0", num_envs=1, use_fabric=True)
    cfg.seed = 54
    cfg.observations.policy.enable_corruption = False
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
    configure_ground_plane()
    configure_b2w_env(cfg)

    env = gym.make(task, cfg=cfg)
    telemetry = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        observations, _ = env.reset()
        terms = list(env.unwrapped.observation_manager.active_terms["policy"])
        expected = ["base_ang_vel", "projected_gravity", "velocity_commands",
                    "joint_pos", "joint_vel", "actions"]
        if terms != expected or observations["policy"].shape != (1, 57):
            raise RuntimeError(f"Unexpected policy observation contract: {terms}, {observations['policy'].shape}")
        if env.action_space.shape != (1, 16):
            raise RuntimeError(f"Unexpected action contract: {env.action_space.shape}")
        policy = torch.jit.load(str(args.policy), map_location=env.unwrapped.device).eval()
        with torch.inference_mode():
            probe = policy(torch.zeros((1, 57), device=env.unwrapped.device))
        if probe.shape != (1, 16) or not torch.isfinite(probe).all():
            raise RuntimeError("Policy output contract failed")
        print(f"READY: flat B2W, policy={args.policy}", flush=True)
        print("GAMEPAD: XInput controller 0 connected", flush=True)
        print("Left stick: forward/back and lateral. Right stick: yaw.", flush=True)
        print(f"TELEMETRY_PORT={args.telemetry_port}", flush=True)
        dt = env.unwrapped.step_dt
        robot = env.unwrapped.scene["robot"]
        step = 0
        while simulation_app.is_running():
            start = time.perf_counter()
            with torch.inference_mode():
                action = policy(observations["policy"])
                if not torch.isfinite(action).all():
                    raise RuntimeError("Non-finite policy action")
                observations, _, _, _, _ = env.step(action)
            step += 1
            if step % 5 == 0:
                body_pos = robot.data.body_pos_w[0].cpu().tolist()
                body_quat = robot.data.body_quat_w[0].cpu().tolist()
                snapshot = {
                    "step": step,
                    "root_pos": robot.data.root_pos_w[0].cpu().tolist(),
                    "root_quat": robot.data.root_quat_w[0].cpu().tolist(),
                    "bodies": dict(zip(robot.body_names, body_pos)),
                    "body_quats": dict(zip(robot.body_names, body_quat)),
                    "command": gamepad.advance().cpu().tolist(),
                }
                telemetry.sendto(json.dumps(snapshot).encode("utf-8"), ("127.0.0.1", args.telemetry_port))
            if step % 100 == 0:
                pos = env.unwrapped.scene["robot"].data.root_pos_w[0].cpu().tolist()
                command = gamepad.advance().cpu().tolist()
                print(f"STEP={step} POS={pos} COMMAND={command}", flush=True)
            if args.steps and step >= args.steps:
                break
            elapsed = time.perf_counter() - start
            if elapsed < dt:
                time.sleep(dt - elapsed)
    finally:
        telemetry.close()
        env.close()


try:
    main()
finally:
    simulation_app.close()
