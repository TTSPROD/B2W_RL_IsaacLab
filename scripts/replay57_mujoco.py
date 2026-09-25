"""Capture full 19999 states and replay fresh contacts or serialized warm state."""
import argparse
import math
import json
import time
import mujoco
import numpy as np
import torch
from b2w_runtime import configure_process
from check_policy_contract import load_contract
from contact57b_model import make_model, controller
from locomotion57_protocol import cases_for, reset_sample, export_path, Telemetry
from sim2sim_mujoco_b2w import quaternion_inverse_rotate_wxyz as inverse
from replay57_protocol import BASE, ROOT, DT, PHYSICS_DT, STEPS, SEEDS, BODY_NAMES, saved_config, write_result

STATE_SPEC = mujoco.mjtState.mjSTATE_INTEGRATION


def actor_observation(states, ctl, previous, command, default):
    obs = np.zeros((len(states),57),np.float32)
    for i,d in enumerate(states):
        obs[i,:3] = np.clip(d.sensor('imu_gyro').data,-100,100)*.25
        obs[i,3:6] = inverse(d.sensor('imu_quat').data,np.array([0.,0.,-1.]))
        obs[i,6:9] = command
        obs[i,9:25] = np.clip(d.qpos[ctl.qids]-default,-100,100)
        obs[i,21:25] = 0
        obs[i,25:41] = np.clip(d.qvel[ctl.vids],-100,100)*.05
        obs[i,41:] = np.clip(previous[i],-100,100)
    return obs


def basic_trace(states):
    return np.asarray([[*inverse(d.sensor('imu_quat').data,d.sensor('frame_vel').data)[:2],
        d.sensor('imu_gyro').data[2],*d.qpos[:3]] for d in states],np.float32)


def snapshot(model, states, ctl, previous, targets):
    state = np.empty((4,mujoco.mj_stateSize(model,STATE_SPEC)))
    root_velocity = np.empty((4,6))
    for i,d in enumerate(states):
        mujoco.mj_getState(model,d,state[i],STATE_SPEC)
        # Recompute only a copy: observation sensor cache of the live run is untouched.
        copy = mujoco.MjData(model)
        mujoco.mj_copyData(copy,model,d)
        mujoco.mj_forward(model,copy)
        jp,jr = np.zeros((3,model.nv)),np.zeros((3,model.nv))
        mujoco.mj_jacBodyCom(model,copy,jp,jr,model.body('base_link').id)
        root_velocity[i] = np.r_[jp@copy.qvel,jr@copy.qvel]
    return {'integration':state, 'sensors':np.stack([d.sensordata.copy() for d in states]),
        'root_pose':np.stack([d.qpos[:7].copy() for d in states]), 'root_com_velocity_w':root_velocity,
        'q':np.stack([d.qpos[ctl.qids].copy() for d in states]),
        'dq':np.stack([d.qvel[ctl.vids].copy() for d in states]),
        'previous_action':previous.copy(), 'targets':targets.copy(),
        'qvel_native':np.stack([d.qvel.copy() for d in states])}


def capture():
    model,definition = make_model('cooked_shapes',PHYSICS_DT,terrain='up_14x32')
    ctl = controller(model)
    cfg = load_contract()
    default,scale = np.asarray(cfg['default_dof_pos'],np.float32),np.asarray(cfg['action_scale'],np.float32)
    actor = torch.jit.load(str(export_path(19999))).eval()
    states = [mujoco.MjData(model) for _ in SEEDS]
    for seed,d in zip(SEEDS,states):
        s = reset_sample(seed)
        d.qpos[:7] = [*s['xy'],.65+definition['start_height'],math.cos(s['yaw']/2),0,0,math.sin(s['yaw']/2)]
        d.qpos[ctl.qids] = default
        d.qpos[ctl.qids[:12]] += s['qdelta']
        d.qvel[ctl.vids] = s['dq']
        mujoco.mj_forward(model,d)
    case = next(c for c in cases_for('up_14x32') if c.name=='forward_0.30')
    trace = np.empty((case.steps,4,6),np.float32)
    previous = np.zeros((4,16),np.float32)
    targets = np.tile(default,(4,1))
    started = time.monotonic()
    with torch.inference_mode():
        for step,cmd in enumerate(case.schedule()[0]):
            if step == 1350:
                snap = snapshot(model,states,ctl,previous,targets)
            actions = actor(torch.from_numpy(actor_observation(states,ctl,previous,cmd,default))).numpy()
            targets = np.clip(actions*scale+default,-100,100)
            previous = actions.copy()
            for _ in range(10):
                for i,d in enumerate(states):
                    ctl.apply(d,targets[i])
                    mujoco.mj_step(model,d)
            trace[step] = basic_trace(states)
            if step%500 == 0:
                print('CAPTURE',step,flush=True)
    original = np.load(ROOT/'logs/contact57b_20260925/micro_up_14x32_19999_cooked_shapes.npz')['forward_0.30']
    error = float(np.max(np.abs(original-trace)))
    write_result('capture', {'trace':trace, **snap}, {'engine':'MuJoCo','max_abs_original_trace_error':error,
        'snapshot_time_s':27.,'state_spec':int(STATE_SPEC),'wall_seconds':time.monotonic()-started})
    if error != 0:
        raise RuntimeError(f'Source recapture diverged: {error}')


def contact_data(model,d,body_ids,wheels):
    """Normal-only net body forces match Isaac ContactSensor force semantics."""
    net = np.zeros((len(body_ids),3))
    load = np.zeros(4)
    weighted_slip = np.zeros(4)
    samples = np.zeros(4)
    lookup = {b:i for i,b in enumerate(body_ids)}
    jp,jr = np.zeros((3,model.nv)),np.zeros((3,model.nv))
    wrench = np.zeros(6)
    for c in range(d.ncon):
        contact = d.contact[c]
        b1,b2 = model.geom_bodyid[contact.geom]
        if b1 != 0 and b2 != 0:
            continue
        body = int(b2 if b1 == 0 else b1)
        if body not in lookup:
            continue
        mujoco.mj_contactForce(model,d,c,wrench)
        normal = contact.frame[:3]
        f = abs(wrench[0])
        net[lookup[body]] += (1 if b1==0 else -1)*wrench[0]*normal
        if body in wheels and f >= 5.:
            w = wheels.index(body)
            mujoco.mj_jac(model,d,jp,jr,contact.pos,body)
            velocity = jp@d.qvel
            tangent = velocity-np.dot(velocity,normal)*normal
            load[w] += f
            weighted_slip[w] += f*np.dot(tangent,tangent)
            samples[w] += 1
    return net,np.stack([load,weighted_slip,samples],axis=-1)


def replay(variant, warm=False):
    name = 'warm_check' if warm else f'mujoco_{variant}'
    if (BASE/f'{name}.npz').exists():
        raise FileExistsError(name)
    src = np.load(BASE/'capture.npz')
    model,_ = make_model(variant,PHYSICS_DT,terrain='up_14x32')
    ctl,cfg = controller(model),load_contract()
    default,scale = np.asarray(cfg['default_dof_pos'],np.float32),np.asarray(cfg['action_scale'],np.float32)
    states = [mujoco.MjData(model) for _ in SEEDS]
    for i,d in enumerate(states):
        if warm:
            mujoco.mj_setState(model,d,src['integration'][i],STATE_SPEC)
            mujoco.mj_forward(model,d)
            mujoco.mj_setState(model,d,src['integration'][i],STATE_SPEC)
            d.sensordata[:] = src['sensors'][i]
        else:
            d.qpos[:7],d.qpos[ctl.qids] = src['root_pose'][i],src['q'][i]
            d.qvel[:] = src['qvel_native'][i]
            mujoco.mj_forward(model,d)
    actor = torch.jit.load(str(export_path(19999))).eval()
    previous = src['previous_action'].copy()
    body_ids = [model.body(n.replace('_foot','_wheel_link')).id for n in BODY_NAMES]
    wheels = [model.body(f'{leg}_wheel_link').id for leg in ('FR','FL','RR','RL')]
    protected = [BODY_NAMES.index(n) for n in ['base_link','FR_hip','FL_hip','RR_hip','RL_hip']]
    history = np.zeros((4,3,17,3))
    arrays = {k:[] for k in ['trace','root_pose','root_velocity_b','gravity','q','dq','ddq','tau',
        'action','previous_action','targets','contact_history','physics_tau','physics_requested_tau','physics_contact',
        'physics_wheel_positions']}
    telemetry = Telemetry(4,cfg['torque_limits'],model.jnt_range[ctl.joints[:12]],PHYSICS_DT)
    started = time.monotonic()
    with torch.inference_mode():
        for step in range(STEPS):
            action = actor(torch.from_numpy(actor_observation(states,ctl,previous,[.3,0,0],default))).numpy()
            targets = np.clip(action*scale+default,-100,100)
            arrays['action'].append(action.copy())
            arrays['previous_action'].append(previous.copy())
            arrays['targets'].append(targets.copy())
            previous = action.copy()
            for sub in range(10):
                q,dq,tau,requested,force,slip,gz,points,acc = [],[],[],[],[],[],[],[],[]
                for i,d in enumerate(states):
                    old_dq = d.qvel[ctl.vids].copy()
                    req = ctl.kp*(targets[i]-d.qpos[ctl.qids])-ctl.kd*old_dq
                    req[12:] += ctl.kd[12:]*targets[i,12:]
                    requested.append(req)
                    ctl.apply(d,targets[i])
                    mujoco.mj_step(model,d)
                    q.append(d.qpos[ctl.qids].copy())
                    dq.append(d.qvel[ctl.vids].copy())
                    acc.append((dq[-1]-old_dq)/PHYSICS_DT)
                    tau.append(d.actuator_force.copy())
                    net,s = contact_data(model,d,body_ids,wheels)
                    force.append(net)
                    slip.append(s)
                    points.append(d.xpos[wheels].copy())
                    gz.append(inverse(d.sensor('imu_quat').data,np.array([0.,0.,-1.]))[2])
                history = np.roll(history,1,axis=1)
                history[:,0] = force
                telemetry.update(np.array(q),np.array(dq),np.array(tau),np.array(gz),
                    np.linalg.norm(np.array(force)[:,protected],axis=-1).max(axis=1),
                    np.isfinite(q).all(axis=1)&np.isfinite(dq).all(axis=1),np.ones(4,bool),step*DT+(sub+1)*PHYSICS_DT)
                arrays['physics_tau'].append(tau)
                arrays['physics_requested_tau'].append(requested)
                arrays['physics_contact'].append(slip)
                arrays['physics_wheel_positions'].append(points)
            arrays['trace'].append(basic_trace(states))
            arrays['root_pose'].append([d.qpos[:7].copy() for d in states])
            arrays['root_velocity_b'].append([np.r_[inverse(d.sensor('imu_quat').data,d.sensor('frame_vel').data),d.sensor('imu_gyro').data] for d in states])
            arrays['gravity'].append([inverse(d.sensor('imu_quat').data,np.array([0.,0.,-1.])) for d in states])
            for key,value in [('q',q),('dq',dq),('ddq',acc),('tau',tau),('contact_history',history.copy())]:
                arrays[key].append(value)
    arrays = {k:np.asarray(v) for k,v in arrays.items()}
    extra = {'engine':'MuJoCo','variant':variant,'warm':warm,'safety':[telemetry.result(i) for i in range(4)],
        'body_names':BODY_NAMES,'wall_seconds':time.monotonic()-started,
        'contact_timing':'mj_step solver contacts/cached poses with post-integration qvel; 2 ms staging difference',
        'torque_semantics':'requested pre-clipping PD; applied solver actuator force'}
    if warm:
        error = float(np.max(np.abs(arrays['trace']-src['trace'][1350:1600])))
        extra['max_abs_source_continuation_error'] = error
    write_result(name,arrays,extra)
    if warm and error != 0:
        raise RuntimeError(f'Serialized continuation mismatch: {error}')


if __name__ == '__main__':
    configure_process()
    torch.set_num_threads(1)
    parser = argparse.ArgumentParser()
    parser.add_argument('mode',choices=['capture','warm','cooked_shapes','source_shapes'])
    args = parser.parse_args()
    if args.mode == 'capture':
        capture()
    else:
        replay('cooked_shapes' if args.mode=='warm' else args.mode, args.mode=='warm')
