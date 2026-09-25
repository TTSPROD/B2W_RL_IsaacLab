"""Opt-in compiled-model adaptations; immutable vendor/evaluators stay intact."""
from __future__ import annotations
import json
import math
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from check_policy_contract import load_contract
from sim2sim_mujoco_b2w import DEFAULT_XML, dc_motor_clip, validate_model_contract
from physics57_protocol import BASE, VARIANTS, case_boxes


def reference():
    return json.loads((BASE/'isaac_airborne_0.005.json').read_text())


def indices(model):
    names = load_contract()['joint_names']
    joints = [model.joint(n.replace('_foot_joint','_wheel_joint')).id for n in names]
    return np.asarray(joints), model.jnt_qposadr[joints], model.jnt_dofadr[joints]


def adapt_model(model, variant, compiled):
    if variant not in VARIANTS:
        raise ValueError(variant)
    joints, qids, vids = indices(model)
    combined = variant in ('mechanics','mechanics_implicit')
    if variant == 'damping_only' or combined:
        # Solver damping for implicit wheels is active actuator damping, not passive loss.
        friction = np.asarray(compiled['joint_friction'])
        assert np.max(np.abs(friction)) < 1e-9
        model.dof_damping[vids] = 0.
    if variant == 'armature_only' or combined:
        model.dof_armature[vids] = compiled['armature']
    if variant == 'inertials_only' or combined:
        for i,name in enumerate(compiled['body_names']):
            body = model.body(name.replace('_foot','_wheel_link')).id
            tensor = np.asarray(compiled['inertia_body_frame_kg_m2'][i])
            values,vectors = np.linalg.eigh((tensor+tensor.T)/2)
            if values.min() <= 0:
                raise ValueError(f'Invalid inertia: {name}')
            if np.linalg.det(vectors) < 0:
                vectors[:,0] *= -1
            quat = Rotation.from_matrix(vectors).as_quat()
            model.body_mass[body] = compiled['mass_kg'][i]
            model.body_ipos[body] = compiled['com_pose_b_wxyz'][i][:3]
            model.body_inertia[body] = values
            model.body_iquat[body] = quat[[3,0,1,2]]
    if variant == 'effort_only' or combined:
        limits = np.asarray(load_contract()['torque_limits'])
        model.actuator_ctrlrange[:] = np.column_stack((-limits,limits))
    if variant == 'mechanics_implicit':
        kd = np.asarray(load_contract()['rl_kd'])[12:]
        model.actuator_gainprm[12:] = 0
        model.actuator_gainprm[12:,0] = kd
        model.actuator_biasprm[12:] = 0
        model.actuator_biasprm[12:,2] = -kd
        model.actuator_biastype[12:] = int(mujoco.mjtBias.mjBIAS_AFFINE)
        model.actuator_ctrllimited[12:] = False
        model.actuator_forcelimited[12:] = True
        model.actuator_forcerange[12:] = [-20.,20.]
        model.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    mujoco.mj_setConst(model,mujoco.MjData(model))
    validate_model_contract(model,load_contract())
    return model


def make_probe_model(case, variant, dt, compiled, airborne):
    spec = mujoco.MjSpec.from_file(str(DEFAULT_XML))
    spec.geom('floor').contype = spec.geom('floor').conaffinity = 0
    for i,box in enumerate(case_boxes(case)):
        pitch=box['pitch']
        spec.worldbody.add_geom(name=f'probe_{i}',type=mujoco.mjtGeom.mjGEOM_BOX,
            size=np.asarray(box['size'])/2,pos=box['pos'],quat=[math.cos(pitch/2),0,math.sin(pitch/2),0],
            friction=[1.,.005,.0001],condim=3)
    model=spec.compile()
    model.opt.timestep=dt
    if airborne:
        model.opt.gravity[:] = 0
    return adapt_model(model,variant,compiled)


class Physics57Controller:
    def __init__(self, model, variant):
        cfg=load_contract()
        self.joints,self.qids,self.vids=indices(model)
        self.kp,self.kd=np.asarray(cfg['rl_kp']),np.asarray(cfg['rl_kd'])
        self.limits=np.asarray(cfg['torque_limits'])
        self.no_load=np.asarray(cfg['isaac_velocity_limits'])
        self.implicit_wheels=variant=='mechanics_implicit'

    def apply(self, data, target):
        velocity=data.qvel[self.vids]
        desired_velocity=np.zeros(16)
        desired_velocity[12:]=target[12:]
        effort=self.kp*(target-data.qpos[self.qids])+self.kd*(desired_velocity-velocity)
        effort[:12]=dc_motor_clip(effort[:12],velocity[:12],self.limits[:12],self.no_load[:12],self.limits[:12])
        effort[12:]=np.clip(effort[12:],-self.limits[12:],self.limits[12:])
        if self.implicit_wheels:
            effort[12:]=target[12:]
        data.ctrl[:]=effort


def compiled_inventory(model):
    joints,qids,vids=indices(model)
    bodies=[]
    for i in range(1,model.nbody):
        rot=Rotation.from_quat(model.body_iquat[i][[1,2,3,0]]).as_matrix()
        bodies.append({'name':model.body(i).name,'mass_kg':float(model.body_mass[i]),
            'com_m':model.body_ipos[i].tolist(),
            'inertia_body_frame_kg_m2':(rot@np.diag(model.body_inertia[i])@rot.T).tolist(),
            'parent':model.body(int(model.body_parentid[i])).name,
            'local_pos':model.body_pos[i].tolist(),'local_quat_wxyz':model.body_quat[i].tolist()})
    geoms=[{'name':model.geom(i).name,'body':model.body(int(model.geom_bodyid[i])).name,
        'type':int(model.geom_type[i]),'size':model.geom_size[i].tolist(),
        'pos':model.geom_pos[i].tolist(),'quat_wxyz':model.geom_quat[i].tolist(),
        'friction':model.geom_friction[i].tolist(),'condim':int(model.geom_condim[i]),
        'contype':int(model.geom_contype[i]),'conaffinity':int(model.geom_conaffinity[i]),
        'solref':model.geom_solref[i].tolist(),'solimp':model.geom_solimp[i].tolist()}
        for i in range(model.ngeom) if model.geom_contype[i] or model.geom_conaffinity[i]]
    return {'bodies':bodies,'collisions':geoms,'damping':model.dof_damping[vids].tolist(),
        'armature':model.dof_armature[vids].tolist(),'joint_frictionloss':model.dof_frictionloss[vids].tolist(),
        'ctrlrange':model.actuator_ctrlrange.tolist(),'forcerange':model.actuator_forcerange.tolist(),
        'forcerange_enabled':model.actuator_forcelimited.tolist(),
        'gainprm':model.actuator_gainprm.tolist(),'biasprm':model.actuator_biasprm.tolist(),
        'integrator':int(model.opt.integrator),'dt_s':float(model.opt.timestep)}
