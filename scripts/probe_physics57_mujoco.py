"""Pair recorded Isaac target traces with source-backed MuJoCo variants."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import time
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from b2w_runtime import configure_process
from physics57_protocol import ROOT, BASE, CONFIG, DT, VARIANTS, save_json, sha256
from physics57_mujoco_model import reference, make_probe_model, indices, Physics57Controller, compiled_inventory
from eval_locomotion57_mujoco import contacts


def kinematic_comparison(model, isaac):
    _,qids,_=indices(model)
    state=mujoco.MjData(model)
    results=[]
    for pose in isaac['kinematics']:
        state.qpos[:7]=[0,0,3,1,0,0,0]
        state.qpos[qids]=pose['joint_pos']
        mujoco.mj_forward(model,state)
        rows=[]
        for i,name in enumerate(isaac['compiled']['body_names']):
            body=model.body(name.replace('_foot','_wheel_link')).id
            expected=np.asarray(pose['body_pose_root_wxyz'][i])
            measured=np.r_[state.xpos[body]-[0,0,3],state.xquat[body]]
            ra=Rotation.from_quat(expected[3:][[1,2,3,0]])
            rb=Rotation.from_quat(measured[3:][[1,2,3,0]])
            rows.append({'body':name,'position_error_m':float(np.max(np.abs(expected[:3]-measured[:3]))),
                         'rotation_error_rad':float((ra.inv()*rb).magnitude())})
        results.append(rows)
    return results


def run(suite,variant,dt):
    configure_process()
    start=time.monotonic()
    output=BASE/f'mujoco_{suite}_{variant}_{dt:g}.json'
    if output.exists():
        raise FileExistsError(output)
    isaac=json.loads((BASE/f'isaac_{suite}_0.005.json').read_text())
    trace=np.load(ROOT/isaac['trace_file'])
    source=reference()['compiled']
    records={k:[] for k in ('q','dq','tau','root','base_hip_force')}
    first_inventory=None
    for j,case in enumerate(isaac['cases']):
        model=make_probe_model(case,variant,dt,source,suite=='airborne')
        if first_inventory is None:
            first_inventory=compiled_inventory(model)
            kinematics=kinematic_comparison(model,isaac)
        state=mujoco.MjData(model)
        ctl=Physics57Controller(model,variant)
        state.qpos[:7]=isaac['initial_root'][j][:7]
        state.qpos[ctl.qids]=isaac['initial_joint_pos'][j]
        mujoco.mj_forward(model,state)
        protected=[model.body(n).id for n in ('base_link','FL_hip','FR_hip','RL_hip','RR_hip')]
        case_records={key:[] for key in records}
        for target in trace['targets'][:,j]:
            peak_force=0.
            for _ in range(round(DT/dt)):
                ctl.apply(state,target)
                mujoco.mj_step(model,state)
                peak_force=max(peak_force,contacts(model,state,protected))
            # qpos root orientation is wxyz; free angular velocity is body frame.
            world_angular=Rotation.from_quat(state.qpos[3:7][[1,2,3,0]]).apply(state.qvel[3:6])
            case_records['q'].append(state.qpos[ctl.qids].copy())
            case_records['dq'].append(state.qvel[ctl.vids].copy())
            case_records['tau'].append(state.actuator_force.copy())
            case_records['root'].append(np.r_[state.qpos[:7],state.qvel[:3],world_angular])
            case_records['base_hip_force'].append(peak_force)
        for key in records:
            records[key].append(np.asarray(case_records[key]))
    arrays={key:np.stack(values,axis=1) for key,values in records.items()}
    assert all(np.isfinite(v).all() for v in arrays.values())
    trace_path=output.with_suffix('.npz')
    np.savez_compressed(trace_path,**arrays)
    save_json(output,{'engine':'MuJoCo','suite':suite,'variant':variant,'dt_s':dt,
        'cases':isaac['cases'],'compiled':first_inventory,'kinematic_comparison':kinematics,
        'isaac_reference_sha256':sha256(BASE/f'isaac_{suite}_0.005.json'),
        'targets_trace_sha256':isaac['trace_sha256'],
        'config_sha256':sha256(CONFIG),'source_sha256':sha256(__file__),
        'model_adapter_sha256':sha256(ROOT/'scripts/physics57_mujoco_model.py'),
        'trace_file':str(trace_path.relative_to(ROOT)),'trace_sha256':sha256(trace_path),
        'wall_seconds':time.monotonic()-start})
    return str(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=('airborne','contact'),required=True)
    args=parser.parse_args()
    with ProcessPoolExecutor(max_workers=4) as pool:
        pending=[pool.submit(run,args.suite,v,dt) for v in VARIANTS for dt in (.005,.002,.001)]
        for future in as_completed(pending):
            print('DONE',future.result(),flush=True)


if __name__=='__main__':
    main()
