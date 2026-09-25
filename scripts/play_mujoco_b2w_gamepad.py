"""Visible MuJoCo B2W playback controlled by a Windows XInput gamepad.

This process is simulator-only: it opens no DDS or Unitree SDK transport.
Hold LB to drive; releasing LB, pressing B, or disconnecting the controller
immediately commands zero velocity.  A resets the simulation, X toggles the
tracking camera, and Esc/closing the window exits.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

import mujoco
import numpy as np
import torch

from b2w_gamepad import CommandMapper, XInputController
from check_policy_contract import action_targets, load_contract, make_observation
from mujoco_safety_recorder import (
    CommandTraceWriter,
    MuJoCoSafetyRecorder,
    ReplayCommand,
    SafetyThresholds,
    load_command_trace,
    validate_trace_context,
)
from sim2sim_mujoco_b2w import (
    DEFAULT_POLICY,
    DEFAULT_XML,
    build_model,
    dc_motor_clip,
    forbidden_terrain_contacts,
    initialize,
    quaternion_inverse_rotate_wxyz,
    sha256,
    validate_model_contract,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "logs/mujoco_gamepad/session.jsonl"
DEFAULT_TRACE_DIR = ROOT / "logs/mujoco_gamepad/command_traces"


@dataclass
class RuntimeState:
    previous_action: np.ndarray
    current_targets: np.ndarray
    policy_steps: int = 0
    physics_steps: int = 0
    resets: int = 0
    peak_leg_torque_utilization: float = 0.0
    peak_wheel_torque_utilization: float = 0.0
    peak_wheel_speed_rad_s: float = 0.0


class B2WMujocoRuntime:
    """One-robot 57→16 policy and mixed-actuator MuJoCo runtime."""

    def __init__(
        self,
        model: mujoco.MjModel,
        policy: torch.jit.ScriptModule,
        cfg: dict,
        terrain: dict,
        *,
        safety_thresholds: SafetyThresholds | None = None,
        pre_failure_window_s: float = 2.0,
    ):
        self.model = model
        self.data = mujoco.MjData(model)
        self.policy = policy
        self.cfg = cfg
        self.terrain = terrain
        self.kp = np.asarray(cfg["rl_kp"], dtype=np.float64)
        self.kd = np.asarray(cfg["rl_kd"], dtype=np.float64)
        self.torque_limits = np.asarray(cfg["torque_limits"], dtype=np.float64)
        self.velocity_limits = np.asarray(cfg["isaac_velocity_limits"], dtype=np.float64)
        self.substeps = int(round(cfg["policy_dt"] / model.opt.timestep))
        self.base_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "base_link")
        if self.base_id < 0:
            raise ValueError("MuJoCo model has no base_link body")
        self.state = RuntimeState(np.zeros(16, dtype=np.float32), np.zeros(16, dtype=np.float64))
        self.safety = MuJoCoSafetyRecorder(
            model, cfg, terrain, safety_thresholds, pre_failure_window_s
        )
        self.pending_unsafe: dict[str, object] | None = None
        self.reset()

    def reset(
        self,
        outcome: str = "manual_reset",
        failure_reason: str | None = None,
    ) -> dict[str, object] | None:
        completed = self.safety.finalize(self.data, outcome, failure_reason)
        initialize(self.model, self.data, self.cfg, self.terrain)
        self.state.previous_action = np.zeros(16, dtype=np.float32)
        self.state.current_targets = np.asarray(self.cfg["default_dof_pos"], dtype=np.float64).copy()
        self.state.resets += 1
        self.pending_unsafe = None
        self.safety.begin_episode(self.data)
        return completed

    def policy_step(self, command: tuple[float, float, float]) -> np.ndarray:
        command_array = np.asarray(command, dtype=np.float32)
        if command_array.shape != (3,) or not np.isfinite(command_array).all():
            raise ValueError("Gamepad command must be a finite 3-vector")
        quaternion = np.asarray(self.data.sensor("imu_quat").data, dtype=np.float32).copy()
        observation = make_observation({
            "omega_body": np.asarray(self.data.sensor("imu_gyro").data, dtype=np.float32).copy(),
            "quat_wxyz": quaternion,
            "commands": command_array,
            "joint_pos": np.asarray(self.data.sensordata[:16], dtype=np.float32).copy(),
            "joint_vel": np.asarray(self.data.sensordata[16:32], dtype=np.float32).copy(),
            "previous_action": self.state.previous_action,
            "age_s": 0.0,
        }, self.cfg)
        with torch.inference_mode():
            action = self.policy(observation[None]).squeeze(0).cpu()
        if action.shape != (16,) or not torch.isfinite(action).all():
            raise RuntimeError("Policy returned an invalid action")
        action_array = action.numpy().astype(np.float32, copy=False)
        previous_action = self.state.previous_action.copy()
        self.state.previous_action = np.clip(
            action_array, self.cfg["clip_actions_lower"], self.cfg["clip_actions_upper"]
        )
        self.state.current_targets = action_targets(action, self.cfg).numpy().astype(np.float64, copy=False)
        self.safety.record_policy_step(
            command_array, observation.numpy(), self.state.previous_action, previous_action
        )
        self.state.policy_steps += 1
        return action_array

    def physics_step(self) -> np.ndarray:
        q = np.asarray(self.data.sensordata[:16], dtype=np.float64)
        dq = np.asarray(self.data.sensordata[16:32], dtype=np.float64)
        desired_velocity = np.zeros(16, dtype=np.float64)
        desired_velocity[12:] = self.state.current_targets[12:]
        effort = self.kp * (self.state.current_targets - q) + self.kd * (desired_velocity - dq)
        effort[:12] = dc_motor_clip(
            effort[:12], dq[:12], self.torque_limits[:12], self.velocity_limits[:12],
            self.torque_limits[:12],
        )
        effort[12:] = np.clip(effort[12:], -self.torque_limits[12:], self.torque_limits[12:])
        self.data.ctrl[:] = effort
        mujoco.mj_step(self.model, self.data)
        if not (np.isfinite(self.data.qpos).all() and np.isfinite(self.data.qvel).all()):
            raise RuntimeError("MuJoCo produced a non-finite state")
        utilization = np.abs(effort) / self.torque_limits
        self.state.peak_leg_torque_utilization = max(
            self.state.peak_leg_torque_utilization, float(np.max(utilization[:12]))
        )
        self.state.peak_wheel_torque_utilization = max(
            self.state.peak_wheel_torque_utilization, float(np.max(utilization[12:]))
        )
        self.state.peak_wheel_speed_rad_s = max(
            self.state.peak_wheel_speed_rad_s,
            float(np.max(np.abs(self.data.sensordata[28:32]))),
        )
        self.state.physics_steps += 1
        event = self.safety.record_physics_step(self.data, effort)
        if event is not None and self.pending_unsafe is None:
            self.pending_unsafe = event
        return effort

    def telemetry(self, command: tuple[float, float, float], connected: bool) -> dict[str, object]:
        quaternion = np.asarray(self.data.sensor("imu_quat").data, dtype=np.float64)
        world_velocity = np.asarray(self.data.sensor("frame_vel").data, dtype=np.float64)
        body_velocity = quaternion_inverse_rotate_wxyz(quaternion, world_velocity)
        gravity_body = quaternion_inverse_rotate_wxyz(quaternion, np.array([0.0, 0.0, -1.0]))
        tilt = math.degrees(math.acos(float(np.clip(-gravity_body[2], -1.0, 1.0))))
        contacts, peak_force, bodies = forbidden_terrain_contacts(self.model, self.data)
        return {
            "sim_time_s": float(self.data.time),
            "position_xyz_m": np.asarray(self.data.qpos[:3], dtype=float).tolist(),
            "body_velocity_xy_m_s": np.asarray(body_velocity[:2], dtype=float).tolist(),
            "yaw_rate_rad_s": float(self.data.sensor("imu_gyro").data[2]),
            "tilt_deg": tilt,
            "command": list(command),
            "gamepad_connected": connected,
            "forbidden_contact_count": contacts,
            "forbidden_contact_peak_n": peak_force,
            "forbidden_contact_bodies": bodies,
            "peak_leg_torque_utilization": self.state.peak_leg_torque_utilization,
            "peak_wheel_torque_utilization": self.state.peak_wheel_torque_utilization,
            "peak_wheel_speed_rad_s": self.state.peak_wheel_speed_rad_s,
            "policy_steps": self.state.policy_steps,
            "physics_steps": self.state.physics_steps,
            "resets": self.state.resets,
            "safety": self.safety.snapshot(),
        }


def configure_tracking_camera(viewer, runtime: B2WMujocoRuntime, enabled: bool) -> None:
    if enabled:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
        viewer.cam.trackbodyid = runtime.base_id
        viewer.cam.distance = 3.2
        viewer.cam.azimuth = 135.0
        viewer.cam.elevation = -18.0
    else:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.lookat[:] = runtime.data.qpos[:3]


def run_headless_smoke(runtime: B2WMujocoRuntime, policy_steps: int) -> dict[str, object]:
    for _ in range(policy_steps):
        runtime.policy_step((0.0, 0.0, 0.0))
        for _ in range(runtime.substeps):
            runtime.physics_step()
            if runtime.pending_unsafe is not None:
                break
        if runtime.pending_unsafe is not None:
            break
    return runtime.telemetry((0.0, 0.0, 0.0), connected=False)


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")


def append_episode(path: Path, summary: dict[str, object] | None) -> None:
    """Write compact episode summary and a separate raw failure-window event."""
    if summary is None:
        return
    payload = dict(summary)
    failure_window = payload.pop("failure_window", None)
    append_jsonl(path, {"event": "episode_summary", **payload})
    if failure_window is not None:
        append_jsonl(path, failure_window)


def command_trace_context(session: dict[str, object], cfg: dict) -> dict[str, object]:
    return {
        "policy_sha256": session["policy_sha256"],
        "xml_sha256": session["xml_sha256"],
        "terrain": session["terrain"],
        "policy_dt_s": float(cfg["policy_dt"]),
        "policy_abi": session["policy_abi"],
    }


def default_trace_path() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return DEFAULT_TRACE_DIR / f"commands_{stamp}_{os.getpid()}.jsonl"


def update_hud(viewer, runtime: B2WMujocoRuntime, status: str) -> None:
    safety = runtime.safety.snapshot()
    left = "B2W MuJoCo safety\nstatus\nepisode\ntilt peak\nforbidden peak\nleg/wheel util\nphysics samples"
    right = (
        f"\n{status}\n{safety['episode_index']}\n{safety['tilt_peak_deg']:.1f} deg\n"
        f"{safety['forbidden_contact_peak_force_n']:.1f} N\n"
        f"{safety['leg_torque_utilization_peak']:.2f} / {safety['wheel_torque_utilization_peak']:.2f}\n"
        f"{safety['physics_steps']}"
    )
    viewer.set_texts((
        mujoco.mjtFontScale.mjFONTSCALE_150,
        mujoco.mjtGridPos.mjGRID_TOPRIGHT,
        left,
        right,
    ))


def finalize_unsafe(
    runtime: B2WMujocoRuntime,
    log_path: Path,
    *,
    reset: bool,
) -> dict[str, object]:
    event = runtime.pending_unsafe
    if event is None:
        raise RuntimeError("No pending unsafe event")
    if reset:
        summary = runtime.reset("unsafe", str(event["reason"]))
    else:
        summary = runtime.safety.finalize(runtime.data, "unsafe", str(event["reason"]))
    append_episode(log_path, summary)
    append_jsonl(log_path, {"event": "unsafe_termination", **event, "automatic_reset": reset})
    return event


def run_headless_replay(
    runtime: B2WMujocoRuntime,
    commands: list[ReplayCommand],
    log_path: Path,
) -> dict[str, object]:
    """Replay post-mapping commands without XInput, rendering, or wall-clock pacing."""
    for replay in commands:
        if replay.reset_before_step:
            append_episode(log_path, runtime.reset("manual_reset", "recorded_reset"))
        runtime.policy_step(replay.command)
        for _ in range(runtime.substeps):
            runtime.physics_step()
            if runtime.pending_unsafe is not None:
                event = finalize_unsafe(runtime, log_path, reset=False)
                return {"status": "unsafe", "step": replay.step, "unsafe_event": event,
                        "telemetry": runtime.telemetry(replay.command, connected=False)}
    telemetry = runtime.telemetry((0.0, 0.0, 0.0), connected=False)
    append_episode(log_path, runtime.safety.finalize(runtime.data, "replay_completed"))
    return {"status": "completed", "steps": len(commands), "telemetry": telemetry}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--terrain", choices=("flat", "stair_up", "stair_down", "scene"), default="flat",
                        help="scene loads the supplied XML without adding generated stairs")
    parser.add_argument("--gamepad-index", type=int, choices=range(4), default=0)
    parser.add_argument("--max-forward", type=float, default=0.7)
    parser.add_argument("--max-lateral", type=float, default=0.4)
    parser.add_argument("--max-yaw", type=float, default=0.5)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--smoke-steps", type=int, default=0,
                        help="Headless zero-command policy steps; does not open XInput or a window")
    parser.add_argument("--record-commands", type=Path,
                        help="New JSONL path for the post-mapping 50 Hz command trace")
    parser.add_argument("--replay-commands", type=Path,
                        help="Replay a recorded command trace instead of opening XInput")
    parser.add_argument("--headless-replay", action="store_true",
                        help="Run --replay-commands without a window or real-time pacing")
    parser.add_argument("--unsafe-action", choices=("auto", "reset", "stop"), default="auto",
                        help="auto resets a manual session and stops deterministic replay")
    parser.add_argument("--pre-failure-window-s", type=float, default=2.0,
                        help="Raw 500 Hz state history retained when unsafe termination fires")
    args = parser.parse_args()
    if any(not 0.0 < value <= 1.0 for value in (args.max_forward, args.max_lateral, args.max_yaw)):
        parser.error("Command limits must be in (0, 1]")
    if args.smoke_steps < 0:
        parser.error("--smoke-steps must be non-negative")
    if not math.isfinite(args.pre_failure_window_s) or args.pre_failure_window_s <= 0.0:
        parser.error("--pre-failure-window-s must be positive and finite")
    if args.headless_replay and args.replay_commands is None:
        parser.error("--headless-replay requires --replay-commands")
    if args.smoke_steps and (args.replay_commands is not None or args.headless_replay):
        parser.error("--smoke-steps cannot be combined with command replay")
    if args.record_commands is not None and args.replay_commands is not None:
        parser.error("Cannot record and replay command traces simultaneously")
    policy_path, xml_path = args.policy.resolve(), args.xml.resolve()
    if not policy_path.is_file() or not xml_path.is_file():
        parser.error("Policy and XML must exist")

    torch.set_num_threads(1)
    cfg = load_contract()
    model, terrain = build_model(xml_path, args.terrain)
    contract = validate_model_contract(model, cfg)
    policy = torch.jit.load(str(policy_path), map_location="cpu").eval()
    probe = policy(torch.zeros(1, 57))
    if probe.shape != (1, 16) or not torch.isfinite(probe).all():
        raise ValueError("Export is not a finite 57 -> 16 policy")
    runtime = B2WMujocoRuntime(
        model, policy, cfg, terrain, pre_failure_window_s=args.pre_failure_window_s
    )
    log_path = args.log.resolve()
    session = {
        "event": "session_start",
        "created_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": "MuJoCo simulator only; no DDS or robot transport",
        "policy": str(policy_path),
        "policy_sha256": sha256(policy_path),
        "policy_abi": "57 observations -> 16 actions",
        "xml": str(xml_path),
        "xml_sha256": sha256(xml_path),
        "terrain": terrain,
        "contract": contract,
        "safety": {
            "full_rate_hz": 1.0 / model.opt.timestep,
            "thresholds": asdict(runtime.safety.thresholds),
            "pre_failure_window_s": args.pre_failure_window_s,
            "automatic_unsafe_termination": True,
        },
        "runtime": {"python": platform.python_version(), "torch": torch.__version__,
                    "mujoco": mujoco.__version__, "platform": platform.platform()},
    }
    replay_commands: list[ReplayCommand] | None = None
    if args.replay_commands is not None:
        trace_header, replay_commands = load_command_trace(args.replay_commands)
        validate_trace_context(
            trace_header,
            policy_sha256=str(session["policy_sha256"]),
            xml_sha256=str(session["xml_sha256"]),
            terrain=terrain,
            policy_dt_s=float(cfg["policy_dt"]),
        )
        session["replay_commands"] = str(args.replay_commands.resolve())
        session["replay_steps"] = len(replay_commands)
    append_jsonl(log_path, session)

    if args.smoke_steps:
        telemetry = run_headless_smoke(runtime, args.smoke_steps)
        if runtime.pending_unsafe is not None:
            finalize_unsafe(runtime, log_path, reset=False)
        else:
            append_episode(log_path, runtime.safety.finalize(runtime.data, "smoke_completed"))
        append_jsonl(log_path, {"event": "headless_smoke_complete", **telemetry})
        print("MUJOCO_GAMEPAD_SMOKE=" + json.dumps(telemetry, sort_keys=True))
        return 2 if telemetry["safety"]["unsafe_pending"] else 0

    if replay_commands is not None and args.headless_replay:
        result = run_headless_replay(runtime, replay_commands, log_path)
        append_jsonl(log_path, {"event": "session_end", "replay": result})
        print("MUJOCO_GAMEPAD_REPLAY=" + json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "completed" else 2

    if replay_commands is None and platform.system() != "Windows":
        parser.error("Interactive gamepad mode currently requires Windows XInput")
    gamepad = XInputController(args.gamepad_index) if replay_commands is None else None
    mapper = CommandMapper(args.max_forward, args.max_lateral, args.max_yaw) if gamepad else None
    from mujoco import viewer as mujoco_viewer

    if replay_commands is None:
        print("MUJOCO GAMEPAD: hold LB to drive; release LB/B/disconnect stops; A reset; X camera; Esc exit")
    else:
        print(f"MUJOCO REPLAY: {len(replay_commands)} deterministic command steps; Esc exits")
    print(f"POLICY={policy_path} SHA256={session['policy_sha256']} TERRAIN={args.terrain}")
    unsafe_action = args.unsafe_action
    if unsafe_action == "auto":
        unsafe_action = "reset" if replay_commands is None else "stop"
    trace_writer: CommandTraceWriter | None = None
    if replay_commands is None:
        trace_path = args.record_commands.resolve() if args.record_commands else default_trace_path().resolve()
        trace_writer = CommandTraceWriter(trace_path, command_trace_context(session, cfg))
        append_jsonl(log_path, {"event": "command_trace", "path": str(trace_path)})
        print(f"COMMAND_TRACE={trace_path}")
    target_wall_time = time.perf_counter()
    last_report = target_wall_time
    connected_previous: bool | None = None
    tracking_camera = True
    replay_index = 0
    trace_reset_pending = False
    hud_status = "ARMED" if replay_commands is None else "REPLAY"
    trace_outcome = "viewer_closed"
    exit_code = 0
    try:
        with mujoco_viewer.launch_passive(model, runtime.data, show_left_ui=False, show_right_ui=True) as viewer:
            configure_tracking_camera(viewer, runtime, tracking_camera)
            update_hud(viewer, runtime, hud_status)
            while viewer.is_running():
                if replay_commands is None:
                    pad = gamepad.read()
                    command, reset, toggle_camera = mapper.advance(pad, cfg["policy_dt"])
                    connected = pad.connected
                    if pad.connected != connected_previous:
                        print(f"GAMEPAD connected={pad.connected} index={args.gamepad_index}", flush=True)
                        append_jsonl(log_path, {"event": "gamepad_connection", "connected": pad.connected})
                        connected_previous = pad.connected
                    reset_before_step = reset or trace_reset_pending
                    if reset:
                        append_episode(log_path, runtime.reset("manual_reset", "gamepad_reset"))
                        target_wall_time = time.perf_counter()
                        print("RESET", flush=True)
                    if toggle_camera:
                        tracking_camera = not tracking_camera
                        configure_tracking_camera(viewer, runtime, tracking_camera)
                    trace_writer.record(command, reset_before_step=reset_before_step)
                    trace_reset_pending = False
                else:
                    if replay_index >= len(replay_commands):
                        append_episode(log_path, runtime.safety.finalize(runtime.data, "replay_completed"))
                        trace_outcome = "replay_completed"
                        break
                    replay = replay_commands[replay_index]
                    replay_index += 1
                    command = replay.command
                    connected = False
                    if replay.reset_before_step:
                        append_episode(log_path, runtime.reset("manual_reset", "recorded_reset"))
                        target_wall_time = time.perf_counter()

                runtime.policy_step(command)
                unsafe = False
                for _ in range(runtime.substeps):
                    runtime.physics_step()
                    target_wall_time += model.opt.timestep
                    delay = target_wall_time - time.perf_counter()
                    if delay > 0.0:
                        time.sleep(delay)
                    elif delay < -0.25:
                        target_wall_time = time.perf_counter()
                    if runtime.pending_unsafe is not None:
                        unsafe = True
                        break
                if unsafe:
                    event = finalize_unsafe(runtime, log_path, reset=unsafe_action == "reset")
                    hud_status = "UNSAFE: " + str(event["reason"])
                    print(f"UNSAFE episode={event['episode_index']} reason={event['reason']}", flush=True)
                    if mapper is not None:
                        mapper.block()
                    if unsafe_action == "reset":
                        trace_reset_pending = True
                        target_wall_time = time.perf_counter()
                    else:
                        trace_outcome = "unsafe"
                        exit_code = 2
                update_hud(viewer, runtime, hud_status)
                viewer.sync()
                if unsafe and unsafe_action == "stop":
                    break
                now = time.perf_counter()
                if now - last_report >= 1.0:
                    telemetry = runtime.telemetry(command, connected)
                    telemetry["event"] = "telemetry"
                    append_jsonl(log_path, telemetry)
                    print(
                        "STEP={policy_steps} POS={position_xyz_m} CMD={command} CONNECTED={gamepad_connected} "
                        "TILT={tilt_deg:.1f} WHEEL_UTIL={peak_wheel_torque_utilization:.2f} "
                        "SAFETY={safety[unsafe_reason]}".format(**telemetry),
                        flush=True,
                    )
                    if not unsafe:
                        hud_status = "ARMED" if replay_commands is None else "REPLAY"
                    last_report = now
    finally:
        if runtime.safety.active:
            outcome = "viewer_closed" if replay_commands is None else "stopped"
            append_episode(log_path, runtime.safety.finalize(runtime.data, outcome))
        if trace_writer is not None:
            trace_writer.close(trace_outcome)
    append_jsonl(log_path, {"event": "session_end", "outcome": trace_outcome,
                            **runtime.telemetry((0.0, 0.0, 0.0), False)})
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
