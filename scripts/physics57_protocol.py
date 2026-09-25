"""Bounded source-model diagnosis, separate from frozen locomotion acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np

from check_policy_contract import load_contract
from locomotion57_protocol import ROOT, DT, sha256, terrain_boxes

BASE = ROOT/'logs/physics57_20260925'
CONFIG = ROOT/'configs/physics57_diagnostics_20260925.json'
AIRBORNE = ('hold', 'hip_step', 'thigh_chirp', 'calf_step', 'wheel_step')
CONTACT = ('stand', 'roll_brake', 'slope_roll', 'step_roll')
VARIANTS = ('vendor', 'damping_only', 'armature_only', 'inertials_only', 'effort_only',
            'mechanics', 'mechanics_implicit')


def command(case, time_s):
    return np.array([.5 if case != 'stand' and 1 <= time_s < 8 else 0., 0., 0.])


def targets(case, time_s):
    target = np.asarray(load_contract()['default_dof_pos']).copy()
    if .5 <= time_s < 2.5:
        if case in ('hip_step', 'calf_step'):
            target[0 if case == 'hip_step' else 2] += .05
        elif case == 'thigh_chirp':
            t = time_s-.5
            target[1] += .05*np.sin(2*np.pi*(.5*t+.375*t*t))
        elif case == 'wheel_step':
            target[12:] = 10.
    return target


def case_boxes(case):
    if case == 'step_roll':
        return [{'size': [41.2, 2., 2.], 'pos': [-19.4, 0., -1.], 'pitch': 0.},
                {'size': [38.8, 2., 2.12], 'pos': [20.6, 0., -.94], 'pitch': 0.}]
    result = terrain_boxes('slope_up' if case == 'slope_roll' else 'flat')['boxes']
    for box in result:
        box['size'][1] = 2.
    return result


def save_json(path, data):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def manifest():
    return {'schema': 'physics57_diagnostics_v1',
            'purpose': 'source-backed mechanical/adapter diagnosis, not policy acceptance or hardware identification',
            'policy_dt_s': DT, 'airborne_cases': AIRBORNE, 'contact_cases': CONTACT,
            'airborne_seconds': 4., 'contact_seconds': 10.,
            'isaac_dt_s': [.005, .002], 'mujoco_dt_s': [.005, .002, .001],
            'mujoco_variants': VARIANTS,
            'variant_semantics': {
                'vendor': 'immutable vendor mechanics, explicit wheel PD, original integrator',
                'damping_only': 'zero passive viscous damping; retain actuator damping',
                'armature_only': 'copy compiled Isaac armature',
                'inertials_only': 'copy compiled Isaac body-frame mass, COM and full inertia',
                'effort_only': 'copy source contract calf actuator effort bound 320 Nm',
                'mechanics': 'combine damping/armature/inertials/effort; explicit wheel PD unchanged',
                'mechanics_implicit': 'mechanics plus force-limited wheel velocity servos and implicitfast'},
            'reference': 'current nominal Isaac training asset; not measured real B2W',
            'kinematic_poses': ['default', 'offset_leg_pose_1', 'offset_leg_pose_2'],
            'static_tolerances': {'position_m': 1e-5, 'rotation_rad': 1e-4,
                                  'mass_kg': 1e-4, 'com_m': 1e-5, 'inertia_kg_m2': 1e-5},
            'airborne_diagnostic_tolerances': {'leg_q_max_abs_rad': .03,
                'wheel_steady_velocity_max_abs_rad_s': .2, 'wheel_final_speed_max_rad_s': .05},
            'contact_probe': 'same initial state and full recorded targets from Isaac upstream10000, no actor feedback in MuJoCo replay',
            'contact_interpretation': 'finite-horizon descriptive divergence; no long-trajectory equivalence/pass claim',
            'micro_screen': {'policies': [10000, 19999], 'variants': ['vendor', 'damping_only', 'mechanics_implicit'],
                'terrains': ['flat', 'up_14x32'], 'cases': {'flat': ['vx_+0.50', 'vx_+1.00'],
                'up_14x32': ['forward_0.30', 'forward_0.70', 'interrupted']},
                'seeds': list(range(7201,7205)), 'dt_s': .002,
                'criteria': 'unchanged locomotion57_v1, diagnostic subset only; 120 episodes'},
            'budget': 'local only, short probes and 120 diagnostic policy episodes; no PPO or server jobs',
            'not_covered': ['measured hardware parameters', 'full collision/contact equivalence',
                            'closed validation', 'policy release acceptance', 'training repeatability']}
