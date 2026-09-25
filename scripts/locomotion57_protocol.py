"""Time-commanded B2W development evaluation; no route/landing feedback.

Geometry, command schedules and outcome logic are shared by both simulators.
This protocol does not measure hardware limits or qualify a training recipe.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DT = 0.02
POLICIES = (10000, 15000, 19999)
CHECKPOINT_SHA = {
    10000: "611dba2dfbb53f828c2a6e005a44c612970a5ca42e8f9261bb22b5f9c4659caa",
    15000: "9d97dfa997f5d759d8bbf1e63a558321fa0dbf455df27a77dd10b6d8732c654c",
    19999: "e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc",
}
REASONS = ("non_finite", "tilt", "base_hip_contact", "hard_joint_position")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export_path(iteration):
    return ROOT / f"logs/locomotion57_upstream_20260925/export{iteration}/policy-contract-export/policy.pt"


@dataclass(frozen=True)
class Segment:
    seconds: float
    command: tuple[float, float, float]
    kind: str = "constant"


@dataclass(frozen=True)
class Case:
    name: str
    terrain: str
    segments: tuple[Segment, ...]
    precision_axis: int | None = None
    push_time: float | None = None
    # Instantaneous, world-frame lateral velocity perturbation; not a force claim.
    push_delta_v: float = 0.35

    @property
    def steps(self):
        return int(round(sum(s.seconds for s in self.segments) / DT))

    def schedule(self):
        commands, indices = [], []
        previous = np.zeros(3)
        for i, segment in enumerate(self.segments):
            count = int(round(segment.seconds / DT))
            target = np.asarray(segment.command)
            values = (np.linspace(previous, target, count + 1)[1:]
                      if segment.kind == "ramp" else np.tile(target, (count, 1)))
            commands.append(values)
            indices.extend([i] * count)
            previous = target
        return np.concatenate(commands).astype(np.float32), np.asarray(indices)


def cases_for(terrain):
    zero = (0.0, 0.0, 0.0)
    start = Segment(2, zero, "initialization")
    stop = Segment(12 if terrain == "flat" else 13, zero)

    def steady(name, command, precision=None, push=None):
        return Case(name, terrain, (start, Segment(30, command), stop), precision, push)

    if terrain == "flat":
        cases = [Case("stand", terrain, (Segment(12, zero),))]
        for axis, label, values in ((0, "vx", (-0.5, 0.5, 1.0)),
                                    (1, "vy", (-0.2, 0.2)), (2, "wz", (-0.5, 0.5))):
            for value in values:
                cmd = [0.0] * 3
                cmd[axis] = value
                cases.append(steady(f"{label}_{value:+.2f}", tuple(cmd)))
        for axis, label in enumerate(("vx", "vy", "wz")):
            for value in (-0.1, 0.1):
                cmd = [0.0] * 3
                cmd[axis] = value
                cases.append(steady(f"precision_{label}_{value:+.2f}", tuple(cmd), axis))
        cases += [steady("diagonal", (0.5, 0.2, 0.0)),
                  steady("turning", (0.5, 0.0, 0.5)),
                  Case("reverse", terrain, (start, Segment(30, (0.5, 0, 0)),
                                              Segment(30, (-0.5, 0, 0)), stop)),
                  Case("ramp", terrain, (start, Segment(4, (1.0, 0, 0), "ramp"),
                                           Segment(30, (1.0, 0, 0)), stop)),
                  steady("push_moving", (0.5, 0, 0), push=10.0),
                  Case("push_standing", terrain, (Segment(25, zero),), push_time=10.0)]
        return cases
    cases = [steady("forward_0.30", (0.3, 0, 0)), steady("forward_0.70", (0.7, 0, 0)),
             Case("interrupted", terrain,
                  (start, Segment(4, (0.5, 0, 0)), stop, Segment(30, (0.5, 0, 0)), stop))]
    if terrain == "random_rough":
        cases.append(steady("push_moving", (0.3, 0, 0), push=10.0))
    return cases


TERRAINS = ("flat", "random_rough", "obstacles", "inverse", "slope_up", "slope_down",
            "up_12x38", "down_12x38", "up_14x32", "down_14x32", "up_16x29", "down_16x29")


def terrain_boxes(name):
    """Exact same solid boxes in both engines. x=0 is the starting point.

    Return full dimensions, center and rotation about Y, plus start elevation and
    far physical edge. The 80 m surface prevents truncating 30 s command segments.
    """
    boxes = []

    def slab(left, right, top, y=0.0, width=80.0):
        bottom = -2.0
        boxes.append({"size": [right-left, width, top-bottom],
                      "pos": [(left+right)/2, y, (top+bottom)/2], "pitch": 0.0})

    start_height, edge = 0.0, None
    if name == "flat":
        slab(-40, 40, 0)
    elif name.startswith(("up_", "down_")) or name == "inverse":
        if name == "inverse":
            rise, run = 0.10, 0.32
            heights = [-rise*i for i in range(1, 7)] + [-rise*i for i in range(5, -1, -1)]
        else:
            dims = name.split('_')[1].split('x')
            rise, run = int(dims[0])/100, int(dims[1])/100
            start_height = 6*rise if name.startswith('down') else 0.0
            heights = ([start_height-rise*i for i in range(1, 7)]
                       if name.startswith('down') else [rise*i for i in range(1, 7)])
        slab(-40, 2, start_height)
        for i, height in enumerate(heights):
            slab(2+i*run, 2+(i+1)*run, height)
        edge = 2+len(heights)*run
        slab(edge, 40, heights[-1])
    elif name.startswith('slope'):
        rise = 5 * math.tan(math.radians(8))
        sign = 1 if name.endswith('up') else -1
        start_height = 0.0 if sign == 1 else rise
        end = rise if sign == 1 else 0.0
        slab(-40, 2, start_height)
        angle = -sign * math.radians(8)
        thick = 0.4
        # Top face endpoints are exactly (2,start_height) and (7,end).
        boxes.append({"size": [5/math.cos(angle), 80, thick],
                      "pos": [4.5-math.sin(angle)*thick/2, 0,
                              (start_height+end)/2-math.cos(angle)*thick/2], "pitch": angle})
        slab(7, 40, end)
        edge = 7.0
    else:
        slab(-40, 40, 0)
        if name == 'random_rough':
            rng = np.random.default_rng(20260925)
            for x in np.arange(2, 7, 0.5):
                for y in np.arange(-10, 10, 0.5):
                    height = float(rng.uniform(0.015, 0.08))
                    boxes.append({"size": [0.5, 0.5, height],
                                  "pos": [x+0.25, y+0.25, height/2], "pitch": 0.0})
        elif name == 'obstacles':
            for x in (2.0, 3.5, 5.0, 6.5):
                boxes.append({"size": [0.25, 80, 0.08], "pos": [x, 0, 0.04], "pitch": 0.0})
        else:
            raise ValueError(name)
        edge = 7.0
    return {"name": name, "boxes": boxes, "start_height": start_height, "physical_edge_x": edge,
            "rough_patch_y": [-10, 10] if name == 'random_rough' else [-40, 40]}


def reset_sample(seed):
    rng = np.random.default_rng(seed)
    return {"xy": rng.uniform(-0.04, 0.04, 2), "yaw": float(rng.uniform(-0.04, 0.04)),
            "qdelta": rng.uniform(-0.015, 0.015, 12), "dq": rng.uniform(-0.03, 0.03, 16)}


class Telemetry:
    """Physics-step statistics, with explicit hard/soft/speed distinctions."""
    def __init__(self, count, torque_limits, hard_ranges, dt):
        self.count, self.dt = count, dt
        self.limits = np.asarray(torque_limits)
        self.ranges = np.asarray(hard_ranges)
        self.flags = np.zeros((count, len(REASONS)), bool)
        self.first_failure_s = np.full(count, np.nan)
        self.samples = np.zeros(count, np.int64)
        self.tau_sq = np.zeros((count, 16))
        self.tau_peak = np.zeros((count, 16))
        self.speed_peak = np.zeros((count, 16))
        self.saturated = np.zeros((count, 16), np.int64)
        self.streak = np.zeros((count, 16), np.int64)
        self.longest = np.zeros((count, 16), np.int64)
        self.hist = np.zeros((count, 16, 101), np.int32)
        self.margin = np.full((count, 12), np.inf)
        self.contact_peak = np.zeros(count)
        self.tilt_peak = np.zeros(count)
        self.slew_peak = np.zeros((count, 16))
        self.slip_peak = np.zeros(count)

    def update(self, q, dq, tau, gravity_z, forbidden_force, finite, alive, time_s):
        margin = np.minimum(q[:, :12]-self.ranges[..., 0], self.ranges[..., 1]-q[:, :12])
        flags = np.stack((~finite, gravity_z > -0.5, forbidden_force > 5.0,
                          margin.min(axis=1) < -0.001), axis=1)
        new = alive & flags.any(axis=1)
        self.first_failure_s[new & ~np.isfinite(self.first_failure_s)] = time_s
        self.flags |= flags & alive[:, None]
        ids = np.flatnonzero(alive)
        self.samples[ids] += 1
        absolute = np.nan_to_num(np.abs(tau[ids]), nan=0.0, posinf=0.0)
        self.tau_sq[ids] += absolute**2
        self.tau_peak[ids] = np.maximum(self.tau_peak[ids], absolute)
        self.speed_peak[ids] = np.maximum(self.speed_peak[ids], np.abs(dq[ids]))
        saturated = absolute >= .95*self.limits
        self.saturated[ids] += saturated
        self.streak[ids] = (self.streak[ids]+1)*saturated
        self.longest[ids] = np.maximum(self.longest[ids], self.streak[ids])
        bins = np.minimum(100, np.floor(absolute/self.limits*100)).astype(int)
        self.hist[ids[:, None], np.arange(16)[None, :], bins] += 1
        self.margin[ids] = np.minimum(self.margin[ids], margin[ids])
        self.contact_peak[ids] = np.maximum(self.contact_peak[ids], forbidden_force[ids])
        self.tilt_peak[ids] = np.maximum(self.tilt_peak[ids], np.degrees(np.arccos(np.clip(-gravity_z[ids], -1, 1))))
        return new

    def result(self, index):
        n = max(1, self.samples[index])
        percentile_bin = (np.cumsum(self.hist[index], axis=-1) >= .99*n).argmax(axis=-1)
        return {"physics_samples": int(self.samples[index]),
                "unsafe_flags": [name for flag, name in zip(self.flags[index], REASONS) if flag],
                "unsafe_time_s": float(self.first_failure_s[index]) if np.isfinite(self.first_failure_s[index]) else None,
                "torque_rms_nm": np.sqrt(self.tau_sq[index]/n).tolist(),
                "torque_p99_bin_upper_nm": ((percentile_bin+1)/100*self.limits).tolist(),
                "torque_peak_nm": self.tau_peak[index].tolist(),
                "torque_saturation_fraction": (self.saturated[index]/n).tolist(),
                "longest_saturation_s": (self.longest[index]*self.dt).tolist(),
                "speed_peak_rad_s": self.speed_peak[index].tolist(),
                "hard_joint_margin_min_rad": self.margin[index].tolist(),
                "base_hip_force_peak_n": float(self.contact_peak[index]),
                "tilt_peak_deg": float(self.tilt_peak[index]),
                "physical_target_slew_peak": self.slew_peak[index].tolist(),
                "wheel_rolling_residual_peak_m_s": float(self.slip_peak[index])}


def assess(case, velocity, position, safety, completed, terrain):
    """Evaluate all segments; safety has outcome precedence. No trajectory feedback."""
    commands, segment_ids = case.schedule()
    available = min(len(velocity), len(commands))
    velocity, position = velocity[:available], position[:available]
    finite = np.isfinite(velocity).all(axis=1)
    limit = np.array([.20, .20, .25] if case.terrain == 'flat' else [.30, .30, .35])
    settle = 2.0 if case.terrain == 'flat' else 3.0
    flags, records = set(), []
    start = 0
    for i, segment in enumerate(case.segments):
        length = int(round(segment.seconds/DT))
        end = start+length
        if segment.kind == 'initialization':
            start = end
            continue
        lo, hi = start+round(settle/DT), min(end, available)
        if hi <= lo or not finite[lo:hi].all():
            flags.add('tracking_failure')
            records.append({"segment": i, "complete": False})
            start = end
            continue
        errors = velocity[lo:hi]-commands[lo:hi]
        rmse = np.sqrt(np.mean(errors**2, axis=0))
        mean = velocity[lo:hi].mean(axis=0)
        record = {"segment": i, "kind": segment.kind, "command": list(segment.command),
                  "complete": hi == end, "rmse": rmse.tolist(), "bias": errors.mean(axis=0).tolist(),
                  "absolute_error_p95": np.quantile(np.abs(errors), .95, axis=0).tolist(),
                  "absolute_error_peak": np.abs(errors).max(axis=0).tolist(), "mean_velocity": mean.tolist()}
        if hi != end or np.any(rmse > limit):
            flags.add('tracking_failure')
        cmd = np.asarray(segment.command)
        zero = np.max(np.abs(cmd)) == 0 and segment.kind != 'ramp'
        # All complete one-second moving windows ending at/after the deadline.
        err_all = velocity[start:hi]-commands[start:hi]
        if len(err_all) >= 50:
            cumulative = np.vstack([np.zeros(3), np.cumsum(err_all**2, axis=0)])
            rolling = np.sqrt((cumulative[50:]-cumulative[:-50])/50)
            first = max(0, round(settle/DT)-50)
            endpoints = (np.arange(len(rolling))+50+start)*DT
            mask = np.arange(len(rolling)) >= first
            if case.push_time is not None:
                mask &= ~((endpoints >= case.push_time) & (endpoints < case.push_time+3))
            if not zero and (not mask.any() or np.any(rolling[mask] > limit)):
                flags.add('command_transition_failure')
            record['moving_rmse_max_after_deadline'] = rolling[mask].max(axis=0).tolist() if mask.any() else None
        if zero:
            times = (np.arange(lo, hi)+1)*DT
            zero_mask = np.ones(len(times), bool)
            if case.push_time is not None:
                zero_mask &= ~((times >= case.push_time) & (times < case.push_time+3))
            values = velocity[lo:hi][zero_mask]
            good = (len(values) >= 500 and np.all(np.linalg.norm(values[:, :2], axis=1) <= .10)
                    and np.all(np.abs(values[:, 2]) <= .10) and hi == end)
            record['continuous_zero_pass'] = bool(good)
            record['zero_speed_peak'] = float(np.linalg.norm(values[:, :2], axis=1).max()) if len(values) else None
            if not good:
                flags.add('standstill_failure')
        elif segment.kind != 'ramp':
            magnitude = np.linalg.norm(cmd[:2])
            fraction = .8 if case.terrain == 'flat' else .6
            if magnitude >= .2-1e-7:
                ratio = float(np.dot(mean[:2], cmd[:2])/(magnitude*magnitude))
                record['linear_response_ratio'] = ratio
                if ratio < fraction:
                    flags.add('tracking_failure')
            if abs(cmd[2]) >= .2-1e-7:
                ratio = float(mean[2]/cmd[2])
                record['angular_response_ratio'] = ratio
                if ratio < fraction:
                    flags.add('tracking_failure')
            if case.precision_axis is not None:
                axis = case.precision_axis
                if rmse[axis] > .05 or mean[axis]/cmd[axis] < .5:
                    flags.add('tracking_failure')
        records.append(record)
        start = end
    edge = terrain['physical_edge_x']
    traversal = None
    if edge is not None:
        # Base clears the last edge by a rear-wheel allowance; lateral coordinates
        # only establish crossing the physical surface, never a route corridor.
        ylo, yhi = terrain['rough_patch_y']
        traversal = bool(np.any((position[:, 0] >= edge+.55) &
                               (position[:, 1] >= ylo) & (position[:, 1] <= yhi)))
        if not traversal:
            flags.add('terrain_stall')
    if not completed:
        flags.add('tracking_failure')
    if safety['unsafe_flags']:
        flags.add('unsafe')
    order = ['unsafe', 'tracking_failure', 'command_transition_failure', 'standstill_failure', 'terrain_stall']
    return {"outcome": next((reason for reason in order if reason in flags), 'success'),
            "failure_flags": sorted(flags), "completed": bool(completed), "segments": records,
            "physical_traversal": traversal, "safety": safety}


def protocol_manifest():
    from dataclasses import asdict
    return {"schema": "locomotion57_v1", "stage": "development_screen", "policy_dt_s": DT,
            "reset_seeds": list(range(7201, 7217)), "policies": CHECKPOINT_SHA,
            "terrains": {name: terrain_boxes(name) for name in TERRAINS},
            "cases": [asdict(case) for name in TERRAINS for case in cases_for(name)],
            "qualification": False, "navigation_feedback": False,
            "physics": "nominal source models, no mass/gain randomization; paired bounded reset variations",
            "safety": {"tilt_deg": 60, "base_hip_net_force_n": 5, "hard_joint_tolerance_rad": .001,
                       "startup_grace_s": 0, "no_load_speed_is_hard_limit": False},
            "criteria": {"flat_rmse": [.20, .20, .25], "rough_stair_rmse": [.30, .30, .35],
                         "flat_response_fraction": .8, "rough_stair_response_fraction": .6,
                         "precision_rmse": .05, "precision_response_fraction": .5,
                         "flat_settling_s": 2, "rough_stair_settling_s": 3,
                         "moving_rmse_window_s": 1, "continuous_zero_s": 10,
                         "zero_xy_speed_m_s": .1, "zero_yaw_speed_rad_s": .1,
                         "disturbance_recovery_s": 3, "development_success_flat": .99,
                         "development_success_rough_stair": .95, "unsafe_allowed": 0},
            "limits": "compiled position ranges; simulator actuation limits, not hardware certification",
            "not_covered": ["independent training seeds", "closed validation", "full domain randomization",
                            "real current/thermal limits", "deployment latency/watchdog", "measured physics parity"],
            "comparison": "paired episodes; no acceptance from pooled average or 16/16 successes"}
