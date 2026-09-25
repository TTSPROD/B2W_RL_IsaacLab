"""Preregistered 19999-only cooked-collision screen with passive diagnostic traces."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
import time
import mujoco
import numpy as np
import torch
from b2w_runtime import configure_process
from check_policy_contract import load_contract
from locomotion57_protocol import DT, Telemetry, assess, cases_for, export_path, reset_sample, protocol_manifest
from eval_locomotion57_mujoco import model_for, contacts
from sim2sim_mujoco_b2w import quaternion_inverse_rotate_wxyz
from physics57_protocol import ROOT, sha256, save_json
from contact57b_model import BASE, CONFIG, COOKED as GEOMETRY, make_model, controller
from physics57_mujoco_model import reference, adapt_model, Physics57Controller, compiled_inventory


def run(terrain,policy_number,variant):
    assert policy_number == 19999, 'Only upstream19999 is authorized for this stage'
    configure_process()
    torch.set_num_threads(1)
    output=BASE/f'micro_{terrain}_{policy_number}_{variant}.json'
    if output.exists():
        raise FileExistsError(output)
    started=time.monotonic()
    plan=json.loads(CONFIG.read_text())['micro_screen']
    cfg=load_contract()
    model,definition=make_model(variant,plan['dt_s'],terrain=terrain)
    ctl=controller(model)
    policy=torch.jit.load(str(export_path(policy_number))).eval()
    protected=[model.body(n).id for n in ('base_link','FL_hip','FR_hip','RL_hip','RR_hip')]
    default=np.asarray(cfg['default_dof_pos'],dtype=np.float32)
    scales=np.asarray(cfg['action_scale'],dtype=np.float32)
    records,traces=[],{}
    seeds=plan['seeds']
    for case in cases_for(terrain):
        if case.name not in plan['cases'][terrain]:
            continue
        states=[mujoco.MjData(model) for _ in seeds]
        for seed,state in zip(seeds,states):
            sample=reset_sample(seed)
            yaw=sample['yaw']
            state.qpos[:7]=[*sample['xy'],.65+definition['start_height'],math.cos(yaw/2),0,0,math.sin(yaw/2)]
            state.qpos[ctl.qids]=default
            state.qpos[ctl.qids[:12]]+=sample['qdelta']
            state.qvel[ctl.vids]=sample['dq']
            mujoco.mj_forward(model,state)
        telemetry=Telemetry(len(seeds),cfg['torque_limits'],model.jnt_range[ctl.joints[:12]],plan['dt_s'])
        schedule=case.schedule()[0]
        trace=np.full((case.steps,len(seeds),6),np.nan,np.float32)
        detail=np.full((case.steps,len(seeds),71),np.nan,np.float32)
        alive=np.ones(len(seeds),bool)
        previous=np.zeros((len(seeds),16),np.float32)
        previous_targets=np.tile(default,(len(seeds),1))
        with torch.inference_mode():
            for step in range(case.steps):
                active=np.flatnonzero(alive)
                if not len(active):
                    break
                obs=np.zeros((len(active),57),np.float32)
                for k,i in enumerate(active):
                    state=states[i]
                    quat=state.sensor('imu_quat').data
                    obs[k,:3]=np.clip(state.sensor('imu_gyro').data,-100,100)*.25
                    obs[k,3:6]=quaternion_inverse_rotate_wxyz(quat,np.array([0.,0.,-1.]))
                    obs[k,6:9]=schedule[step]
                    obs[k,9:25]=np.clip(state.qpos[ctl.qids]-default,-100,100)
                    obs[k,21:25]=0
                    obs[k,25:41]=np.clip(state.qvel[ctl.vids],-100,100)*.05
                    obs[k,41:57]=np.clip(previous[i],-100,100)
                actions=policy(torch.from_numpy(obs)).numpy()
                assert np.isfinite(actions).all()
                targets=previous_targets.copy()
                targets[active]=np.clip(actions*scales+default,-100,100)
                telemetry.slew_peak[active]=np.maximum(telemetry.slew_peak[active],np.abs(targets[active]-previous_targets[active])/DT)
                previous[active]=actions
                previous_targets=targets
                for sub in range(round(DT/plan['dt_s'])):
                    active=np.flatnonzero(alive)
                    if not len(active):
                        break
                    q=np.zeros((len(seeds),16))
                    dq,tau=q.copy(),q.copy()
                    gz=np.full(len(seeds),-1.)
                    forces=np.zeros(len(seeds))
                    finite=np.ones(len(seeds),bool)
                    for i in active:
                        state=states[i]
                        ctl.apply(state,targets[i])
                        mujoco.mj_step(model,state)
                        q[i],dq[i],tau[i]=state.qpos[ctl.qids],state.qvel[ctl.vids],state.actuator_force
                        gz[i]=quaternion_inverse_rotate_wxyz(state.sensor('imu_quat').data,np.array([0.,0.,-1.]))[2]
                        forces[i]=contacts(model,state,protected)
                        finite[i]=np.isfinite(state.qpos).all() and np.isfinite(state.qvel).all()
                    alive &= ~telemetry.update(q,dq,tau,gz,forces,finite,alive,step*DT+(sub+1)*plan['dt_s'])
                for i in np.flatnonzero(alive):
                    state=states[i]
                    velocity=quaternion_inverse_rotate_wxyz(state.sensor('imu_quat').data,state.sensor('frame_vel').data)
                    trace[step,i]=[*velocity[:2],state.sensor('imu_gyro').data[2],*state.qpos[:3]]
                    detail[step,i]=np.r_[state.qpos[:7],state.qpos[ctl.qids],state.qvel[ctl.vids],state.actuator_force,targets[i]]
                    telemetry.slip_peak[i]=max(telemetry.slip_peak[i],float(np.max(np.abs(state.qvel[ctl.vids[12:]]*.0875-velocity[0]))))
        for i,seed in enumerate(seeds):
            count=int(np.isfinite(trace[:,i,0]).sum())
            records.append({'policy':policy_number,'terrain':terrain,'case':case.name,'seed':seed,
                **assess(case,trace[:count,i,:3],trace[:count,i,3:],telemetry.result(i),count==case.steps,definition)})
        traces[case.name]=trace
        traces[case.name+"__detail"]=detail
        print(variant,policy_number,terrain,case.name,sum(r['outcome']=='success' for r in records[-len(seeds):]),flush=True)
    trace_file=output.with_suffix('.npz')
    np.savez_compressed(trace_file,**traces)
    save_json(output,{'schema':'contact57b_micro_diagnostic','variant':variant,'engine':'MuJoCo',
        'detail_columns':'root_pose_wxyz(7), q(16), dq(16), applied_tau(16), targets(16); policy-step samples',
        'records':records,'compiled':compiled_inventory(model),'config_sha256':sha256(CONFIG),
        'policy_export_sha256':sha256(export_path(policy_number)),
        'protocol':protocol_manifest(),'source_sha256':sha256(__file__),
        'adapter_sha256':sha256(ROOT/'scripts/contact57b_model.py'),
        'geometry_sha256':sha256(GEOMETRY),
        'mechanics_adapter_sha256':sha256(ROOT/'scripts/physics57_mujoco_model.py'),
        'trace_file':str(trace_file.relative_to(ROOT)),'trace_sha256':sha256(trace_file),
        'wall_seconds':time.monotonic()-started})
    return str(output)


if __name__=='__main__':
    plan=json.loads(CONFIG.read_text())['micro_screen']
    with ProcessPoolExecutor(max_workers=4) as pool:
        pending=[pool.submit(run,t,p,v) for v in plan['variants'] for t in plan['terrains'] for p in plan['policies']]
        for f in as_completed(pending):
            print('DONE',f.result(),flush=True)
