"""Static geometry verification and preregistered 100 ms paired-state probes."""
from __future__ import annotations
import argparse
import json
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from physics57_protocol import ROOT, save_json, sha256
from physics57_mujoco_model import reference, compiled_inventory
from probe_physics57_mujoco import kinematic_comparison
from probe_physics57_contact_states import fixtures
from eval_locomotion57_mujoco import contacts
from contact57_model import BASE,CONFIG,GEOMETRY,VARIANTS,make_model,controller,geometry


def quat_matrix(quat):
    return Rotation.from_quat(np.asarray(quat)[[1,2,3,0]]).as_matrix()


def source_support(shape, directions):
    if shape['type'] == 'Mesh':
        return (np.asarray(shape['hull_vertices_body_m'])@directions.T).max(axis=0)
    transform = np.asarray(shape['local_to_body'])
    local = directions@transform[:3,:3]
    offset = directions@transform[:3,3]
    if shape['type'] == 'Cube':
        return offset+np.abs(local).sum(axis=1)*shape['size']/2
    return offset+np.linalg.norm(local[:,:2],axis=1)*shape['radius']+np.abs(local[:,2])*shape['height']/2


def model_support(model, geom, directions):
    rotation = quat_matrix(model.geom_quat[geom])
    local = directions@rotation
    offset = directions@model.geom_pos[geom]
    kind = model.geom_type[geom]
    if kind == mujoco.mjtGeom.mjGEOM_MESH:
        mesh = model.geom_dataid[geom]
        start,count = model.mesh_vertadr[mesh],model.mesh_vertnum[mesh]
        vertices = model.mesh_vert[start:start+count]
        return offset+(vertices@local.T).max(axis=0)
    if kind == mujoco.mjtGeom.mjGEOM_BOX:
        return offset+np.abs(local)@model.geom_size[geom]
    assert kind == mujoco.mjtGeom.mjGEOM_CYLINDER
    return offset+np.linalg.norm(local[:,:2],axis=1)*model.geom_size[geom,0]+np.abs(local[:,2])*model.geom_size[geom,1]


def manifest():
    return {'config_sha256':sha256(CONFIG),'geometry_sha256':sha256(GEOMETRY),
        'source_sha256':sha256(__file__),'adapter_sha256':sha256(ROOT/'scripts/contact57_model.py'),
        'mechanics_adapter_sha256':sha256(ROOT/'scripts/physics57_mujoco_model.py'),
        'mujoco_version':mujoco.__version__}


def static():
    source = geometry()
    rows = []
    directions = np.random.default_rng(20260925).normal(size=(2048,3))
    directions /= np.linalg.norm(directions,axis=1,keepdims=True)
    directions = np.r_[directions,np.eye(3),-np.eye(3)]
    for variant in VARIANTS:
        model,_ = make_model(variant,case='stand')
        physical = np.flatnonzero((model.geom_bodyid != 0)&((model.geom_contype != 0)|(model.geom_conaffinity != 0)))
        comparisons = kinematic_comparison(model,reference())
        item = {'variant':variant,'active_robot_shapes':len(physical),
            'kinematics':comparisons,'compiled':compiled_inventory(model)}
        if variant == 'source_shapes':
            assert len(physical) == 20
            support = []
            for i,shape in enumerate(source['shapes']):
                geom = model.geom(f'contact57_{i}').id
                error = float(np.max(np.abs(source_support(shape,directions)-model_support(model,geom,directions))))
                support.append({'body':shape['body'],'type':shape['type'],'max_support_error_m':error})
                assert error <= 1e-6, support[-1]
            assert np.all(model.geom_contype[physical] == 1)
            assert np.all(model.geom_conaffinity[physical] == 2)
            for pose in comparisons:
                assert max(r['position_error_m'] for r in pose) <= 1e-5
                assert max(r['rotation_error_rad'] for r in pose) <= 1e-4
            item['shape_support_comparison'] = support
        rows.append(item)
    save_json(BASE/'static.json',{'profiles':rows,**manifest()})
    print('DONE static',flush=True)


def states():
    cfg = json.loads(CONFIG.read_text())
    previous,meta,rows = fixtures()
    com = np.asarray(reference()['compiled']['com_pose_b_wxyz'][0][:3])
    for variant in VARIANTS:
        for dt in cfg['dt_s']:
            output = BASE/f'states_{variant}_{dt:g}.json'
            if output.exists():
                raise FileExistsError(output)
            records = []
            for row in rows:
                model,_ = make_model(variant,dt,case=row['case'])
                ctl = controller(model)
                data = mujoco.MjData(model)
                root = row['root']
                rotation = quat_matrix(root[3:7])
                data.qpos[:7] = root[:7]
                data.qpos[ctl.qids] = row['q']
                data.qvel[:3] = root[7:10]-np.cross(root[10:13],rotation@com)
                data.qvel[3:6] = rotation.T@root[10:13]
                data.qvel[ctl.vids] = row['dq']
                mujoco.mj_forward(model,data)
                protected = [model.body(n).id for n in ('base_link','FL_hip','FR_hip','RL_hip','RR_hip')]
                peak,impulse,penetration = 0.,0.,0.
                initial_contacts = data.ncon
                force = np.zeros(6)
                for _ in range(round(cfg['state_reset_horizon_s']/dt)):
                    ctl.apply(data,row['target'])
                    mujoco.mj_step(model,data)
                    peak = max(peak,contacts(model,data,protected))
                    for k in range(data.ncon):
                        mujoco.mj_contactForce(model,data,k,force)
                        impulse += abs(force[0])*dt
                        penetration = max(penetration,-float(data.contact[k].dist))
                records.append({'case':row['case'],'snapshot_time_s':row['time_s'],
                    'final_root_pose':data.qpos[:7].tolist(),'final_joint_pos':data.qpos[ctl.qids].tolist(),
                    'final_joint_vel':data.qvel[ctl.vids].tolist(),'base_hip_force_peak_n':peak,
                    'initial_contacts':initial_contacts,'final_contacts':data.ncon,
                    'sum_normal_impulse_abs_ns':impulse,'max_penetration_m':penetration,
                    'finite':bool(np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all())})
            save_json(output,{'variant':variant,'dt_s':dt,'records':records,**manifest()})
            print('DONE',output,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('static','states'))
    args = parser.parse_args()
    static() if args.mode == 'static' else states()
