"""CPU batch sim2sim for the shared time-commanded locomotion57_v1 protocol."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import time

import mujoco
import numpy as np
import torch

from b2w_runtime import configure_process
from check_policy_contract import load_contract
from locomotion57_protocol import (
    DT, POLICIES, TERRAINS, Telemetry, assess, cases_for, export_path,
    protocol_manifest, reset_sample, sha256, terrain_boxes,
)
from sim2sim_mujoco_b2w import (
    DEFAULT_XML, dc_motor_clip, quaternion_inverse_rotate_wxyz, validate_model_contract,
)


def model_for(terrain):
    spec = mujoco.MjSpec.from_file(str(DEFAULT_XML))
    spec.geom('floor').contype = 0
    spec.geom('floor').conaffinity = 0
    definition = terrain_boxes(terrain)
    for i, box in enumerate(definition['boxes']):
        pitch = box['pitch']
        spec.worldbody.add_geom(name=f'terrain_locomotion_{i}', type=mujoco.mjtGeom.mjGEOM_BOX,
            size=np.asarray(box['size'])/2, pos=box['pos'],
            quat=[math.cos(pitch/2), 0, math.sin(pitch/2), 0],
            friction=[1.0, 0.005, 0.0001], condim=3)
    return spec.compile(), definition


def contacts(model, data, protected):
    forces = np.zeros((5, 3))
    local_force = np.zeros(6)
    for k in range(data.ncon):
        contact = data.contact[k]
        body1, body2 = int(model.geom_bodyid[contact.geom1]), int(model.geom_bodyid[contact.geom2])
        if body1 != 0 and body2 != 0:
            continue
        body = body2 if body1 == 0 else body1
        if body not in protected:
            continue
        mujoco.mj_contactForce(model, data, k, local_force)
        world_force = contact.frame.reshape(3, 3).T @ local_force[:3]
        forces[protected.index(body)] += world_force*(1 if body1 == 0 else -1)
    return float(np.linalg.norm(forces, axis=1).max())


def run_group(terrain, policy_number, output_dir, seed_count, smoke_steps):
    configure_process()
    torch.set_num_threads(1)
    output_dir = Path(output_dir)
    output = output_dir / f'mujoco_{terrain}_{policy_number}.json'
    if output.exists():
        raise FileExistsError(output)
    cfg = load_contract()
    model, definition = model_for(terrain)
    validate_model_contract(model, cfg)
    policy = torch.jit.load(str(export_path(policy_number)), map_location='cpu').eval()
    joint_names = [name.replace('_foot_joint', '_wheel_joint') for name in cfg['joint_names']]
    joints = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in joint_names]
    qids, vids = model.jnt_qposadr[joints], model.jnt_dofadr[joints]
    protected = [i for i in range(model.nbody) if model.body(i).name == 'base_link' or '_hip' in model.body(i).name]
    assert len(protected) == 5
    dt, substeps = float(model.opt.timestep), round(DT/model.opt.timestep)
    default = np.asarray(cfg['default_dof_pos'], dtype=np.float32)
    scales = np.asarray(cfg['action_scale'], dtype=np.float32)
    kp, kd = np.asarray(cfg['rl_kp']), np.asarray(cfg['rl_kd'])
    limits, no_load = np.asarray(cfg['torque_limits']), np.asarray(cfg['isaac_velocity_limits'])
    records, traces = [], {}
    start = time.monotonic()
    cases = cases_for(terrain)[:1] if smoke_steps else cases_for(terrain)
    for case in cases:
        data = [mujoco.MjData(model) for _ in range(seed_count)]
        for i, state in enumerate(data):
            sample = reset_sample(7201+i)
            yaw = sample['yaw']
            state.qpos[:7] = [sample['xy'][0], sample['xy'][1], .65+definition['start_height'],
                               math.cos(yaw/2), 0, 0, math.sin(yaw/2)]
            state.qpos[qids] = default
            state.qpos[qids[:12]] += sample['qdelta']
            state.qvel[vids] = sample['dq']
            mujoco.mj_forward(model, state)
        telemetry = Telemetry(seed_count, limits, model.jnt_range[joints[:12]], dt)
        schedule, _ = case.schedule()
        steps = min(case.steps, smoke_steps) if smoke_steps else case.steps
        trace = np.full((steps, seed_count, 6), np.nan, np.float32)
        alive = np.ones(seed_count, bool)
        previous = np.zeros((seed_count, 16), np.float32)
        previous_targets = np.tile(default, (seed_count, 1))
        with torch.inference_mode():
            for step in range(steps):
                if not alive.any():
                    break
                active = np.flatnonzero(alive)
                obs = np.zeros((len(active), 57), np.float32)
                for k, i in enumerate(active):
                    state = data[i]
                    if case.push_time is not None and step == round(case.push_time/DT):
                        state.qvel[1] += case.push_delta_v
                        mujoco.mj_forward(model, state)
                    quat = state.sensor('imu_quat').data
                    gravity = quaternion_inverse_rotate_wxyz(quat, np.array([0., 0., -1.]))
                    obs[k, :3] = np.clip(state.sensor('imu_gyro').data, -100, 100)*.25
                    obs[k, 3:6] = gravity
                    obs[k, 6:9] = schedule[step]
                    obs[k, 9:25] = np.clip(state.qpos[qids]-default, -100, 100)
                    obs[k, 21:25] = 0
                    obs[k, 25:41] = np.clip(state.qvel[vids], -100, 100)*.05
                    obs[k, 41:57] = np.clip(previous[i], -100, 100)
                actions = policy(torch.from_numpy(obs)).numpy()
                bad = ~np.isfinite(actions).all(axis=1)
                telemetry.flags[active[bad], 0] = True
                telemetry.first_failure_s[active[bad]] = step*DT
                alive[active[bad]] = False
                targets = previous_targets.copy()
                targets[active] = np.clip(actions*scales+default, -100, 100)
                telemetry.slew_peak[active] = np.maximum(telemetry.slew_peak[active],
                    np.abs(targets[active]-previous_targets[active])/DT)
                previous[active] = actions
                previous_targets = targets
                for substep in range(substeps):
                    active = np.flatnonzero(alive)
                    if not len(active):
                        break
                    q = np.zeros((seed_count, 16))
                    dq, tau = q.copy(), q.copy()
                    gz = np.full(seed_count, -1.)
                    force = np.zeros(seed_count)
                    finite = np.ones(seed_count, bool)
                    for i in active:
                        state = data[i]
                        vel = state.qvel[vids]
                        desired_velocity = np.zeros(16)
                        desired_velocity[12:] = targets[i, 12:]
                        effort = kp*(targets[i]-state.qpos[qids])+kd*(desired_velocity-vel)
                        effort[:12] = dc_motor_clip(effort[:12], vel[:12], limits[:12], no_load[:12], limits[:12])
                        effort[12:] = np.clip(effort[12:], -limits[12:], limits[12:])
                        state.ctrl[:] = effort
                        mujoco.mj_step(model, state)
                        # Read actual actuator force after ctrlrange clipping (calves differ in vendor MJCF).
                        q[i], dq[i], tau[i] = state.qpos[qids], state.qvel[vids], state.actuator_force
                        quat = state.sensor('imu_quat').data
                        gz[i] = quaternion_inverse_rotate_wxyz(quat, np.array([0., 0., -1.]))[2]
                        force[i] = contacts(model, state, protected)
                        finite[i] = np.isfinite(state.qpos).all() and np.isfinite(state.qvel).all()
                    newly_failed = telemetry.update(q, dq, tau, gz, force, finite, alive,
                                                    step*DT+(substep+1)*dt)
                    alive &= ~newly_failed
                for i in np.flatnonzero(alive):
                    state = data[i]
                    velocity = quaternion_inverse_rotate_wxyz(state.sensor('imu_quat').data,
                                                               state.sensor('frame_vel').data)
                    trace[step, i] = [*velocity[:2], state.sensor('imu_gyro').data[2], *state.qpos[:3]]
                    telemetry.slip_peak[i] = max(telemetry.slip_peak[i],
                        float(np.max(np.abs(state.qvel[vids[12:]]*.0875-velocity[0]))))
        for i in range(seed_count):
            count = int(np.isfinite(trace[:, i, 0]).sum())
            result = assess(case, trace[:count, i, :3], trace[:count, i, 3:],
                            telemetry.result(i), count == case.steps, definition)
            records.append({'policy': policy_number, 'terrain': terrain, 'case': case.name, 'seed': 7201+i, **result})
        traces[case.name] = trace
        print(f'CASE MuJoCo {terrain} {policy_number} {case.name}: '
              f'{sum(r["outcome"]=="success" for r in records[-seed_count:])}/{seed_count}', flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output.with_suffix('.npz')
    np.savez_compressed(trace_path, **traces)
    result = {'engine': 'MuJoCo', 'protocol': protocol_manifest(), 'smoke': bool(smoke_steps),
              'physics_dt_s': dt, 'policy_dt_s': DT, 'wall_seconds': time.monotonic()-start,
              'policy_export_sha256': sha256(export_path(policy_number)),
              'source_sha256': {name: sha256(Path(__file__).parent/name) for name in
                                ('locomotion57_protocol.py', 'eval_locomotion57_mujoco.py')},
              'compiled_model': {'body_names': [model.body(i).name for i in range(model.nbody)],
                                 'mass_kg': model.body_mass.tolist(), 'joint_names': joint_names,
                                 'hard_joint_ranges': model.jnt_range[joints[:12]].tolist(),
                                 'actuator_ctrlrange': model.actuator_ctrlrange.tolist(),
                                 'xml_sha256': sha256(DEFAULT_XML),
                                 'torque_semantics': 'actuator_force after simulator ctrlrange clipping'},
              'trace_path': str(trace_path), 'trace_sha256': sha256(trace_path), 'records': records}
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return str(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--terrains', nargs='+', choices=TERRAINS, default=list(TERRAINS))
    parser.add_argument('--seeds', type=int, default=16)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--smoke-steps', type=int, default=0)
    args = parser.parse_args()
    assert 1 <= args.seeds <= 16 and 1 <= args.workers <= 4
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_group, terrain, policy, args.output_dir, args.seeds, args.smoke_steps)
                   for terrain in args.terrains for policy in POLICIES]
        for future in as_completed(futures):
            print('DONE', future.result(), flush=True)


if __name__ == '__main__':
    main()
