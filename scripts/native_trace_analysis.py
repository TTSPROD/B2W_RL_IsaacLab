"""Offline evidence helpers; no simulator, optimizer or policy selection."""
from __future__ import annotations
import numpy as np


def settled_segments(commands, velocity, dt=.02, settle=2.):
    """Return settled contiguous command phases, keeping signs separate."""
    commands = np.asarray(commands)
    starts = np.r_[0, np.flatnonzero(np.any(commands[1:] != commands[:-1], axis=1))+1]
    ends = np.r_[starts[1:], len(commands)]
    rows = []
    for lo, hi in zip(starts, ends):
        c = commands[lo]
        values = velocity[lo+round(settle/dt):hi]
        values = values[np.isfinite(values).all(axis=1)]
        if not len(values):
            continue
        mean = values.mean(axis=0)
        axis = np.flatnonzero(c)
        rows.append({'start_s': float(lo*dt), 'end_s': float(hi*dt), 'command': c.tolist(),
                     'mean': mean.tolist(), 'rmse': np.sqrt(((values-c)**2).mean(axis=0)).tolist(),
                     'axis': int(axis[0]) if len(axis)==1 else None,
                     'response_ratio': float(mean[axis[0]]/c[axis[0]]) if len(axis)==1 else None,
                     'samples': len(values)})
    return rows


def physical_targets(raw, default, scales):
    # Isaac semantics: physical clipping, raw previous action preserved.
    return np.clip(raw*np.asarray(scales)+np.asarray(default), -100., 100.)


def margins(q, limits):
    return np.minimum(q[..., :12]-limits[:, 0], limits[:, 1]-q[..., :12])


def near_event(x, entry, limits, default, scales, time_s, joint):
    step = np.arange(len(x['joints_10hz']))
    times = step*.1+.02  # stored after the 20ms policy step
    valid = np.isfinite(x['joints_10hz'][:, entry]).all(axis=1)
    ids = np.flatnonzero(valid & (times <= time_s) & (times >= max(0, time_s-2.)))
    if not len(ids):
        return None
    q = x['joints_10hz'][ids, entry, :16]
    dq = x['joints_10hz'][ids, entry, 16:32]
    tau = x['joints_10hz'][ids, entry, 32:48]
    target = physical_targets(x['raw_actions_10hz'][ids, entry], default, scales)
    velocity = x['trace'][ids*5, entry, :3]
    quat = x['quaternion_wxyz_10hz'][ids, entry]
    tilt = np.degrees(np.arccos(np.clip(1-2*(quat[:, 1]**2+quat[:, 2]**2), -1, 1)))
    result = {'time_after_step_s': times[ids].tolist(), 'action_start_s': (ids*.1).tolist(),
              'joint': joint, 'q': q[:, joint].tolist(), 'dq': dq[:, joint].tolist(),
              'tau': tau[:, joint].tolist(), 'q_des': target[:, joint].tolist(),
              'actual_margin': margins(q, limits)[:, joint].tolist(),
              'desired_margin_diagnostic_only': margins(target, limits)[:, joint].tolist(),
              'velocity_body': velocity.tolist(), 'tilt_deg': tilt.tolist(),
              'wheel_dq_des': target[:, 12:].tolist(), 'wheel_dq': dq[:, 12:].tolist(),
              'wheel_tau_estimate': tau[:, 12:].tolist(),
              'minimum_observed_actual_margin_rad': float(margins(q, limits)[:, joint].min())}
    if 'wheels_xyz_upforce_50hz' in x:
        result['wheel_upforce_n'] = x['wheels_xyz_upforce_50hz'][ids*5, entry, :, 3].tolist()
    return result
