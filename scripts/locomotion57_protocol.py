"""Flat measurement primitives for the operating57 screen (50 Hz policy)."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DT = 0.02
CHECKPOINT_SHA = {19999: "e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc"}
REASONS = ("non_finite", "tilt", "base_hip_contact", "hard_joint_position")


def export_path(iteration=19999):
    if iteration != 19999:
        raise ValueError("The current screen is scoped to upstream19999")
    return ROOT / "policies/server/upstream_19999/export/policy.pt"


def terrain_boxes(name):
    if name != "flat":
        raise ValueError("The current screen covers Flat only")
    return {"name": name, "boxes": [{"size": [80, 80.0, 2.0],
            "pos": [0.0, 0.0, -1.0], "pitch": 0.0}], "start_height": 0.0,
            "physical_edge_x": None, "rough_patch_y": [-40, 40]}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

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

    @property
    def steps(self):
        return int(round(sum(s.seconds for s in self.segments) / DT))

    def schedule(self):
        commands, indices = [], []
        for i, segment in enumerate(self.segments):
            count = int(round(segment.seconds / DT))
            target = np.asarray(segment.command)
            values = np.tile(target, (count, 1))
            commands.append(values)
            indices.extend([i] * count)
        return np.concatenate(commands).astype(np.float32), np.asarray(indices)

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
    commands, _ = case.schedule()
    available = min(len(velocity), len(commands))
    velocity, position = velocity[:available], position[:available]
    finite = np.isfinite(velocity).all(axis=1)
    limit = np.array([.20, .20, .25])
    settle = 2.0
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
        zero = np.max(np.abs(cmd)) == 0
        # All complete one-second moving windows ending at/after the deadline.
        err_all = velocity[start:hi]-commands[start:hi]
        if len(err_all) >= 50:
            cumulative = np.vstack([np.zeros(3), np.cumsum(err_all**2, axis=0)])
            rolling = np.sqrt((cumulative[50:]-cumulative[:-50])/50)
            first = max(0, round(settle/DT)-50)
            mask = np.arange(len(rolling)) >= first
            if not zero and (not mask.any() or np.any(rolling[mask] > limit)):
                flags.add('command_transition_failure')
            record['moving_rmse_max_after_deadline'] = rolling[mask].max(axis=0).tolist() if mask.any() else None
        if zero:
            values = velocity[lo:hi]
            good = (len(values) >= 500 and np.all(np.linalg.norm(values[:, :2], axis=1) <= .10)
                    and np.all(np.abs(values[:, 2]) <= .10) and hi == end)
            record['continuous_zero_pass'] = bool(good)
            record['zero_speed_peak'] = float(np.linalg.norm(values[:, :2], axis=1).max()) if len(values) else None
            if not good:
                flags.add('standstill_failure')
        else:
            magnitude = np.linalg.norm(cmd[:2])
            fraction = .8
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
        records.append(record)
        start = end
    traversal = None
    if not completed:
        flags.add('tracking_failure')
    if safety['unsafe_flags']:
        flags.add('unsafe')
    order = ['unsafe', 'tracking_failure', 'command_transition_failure', 'standstill_failure']
    return {"outcome": next((reason for reason in order if reason in flags), 'success'),
            "failure_flags": sorted(flags), "completed": bool(completed), "segments": records,
            "physical_traversal": traversal, "safety": safety}
