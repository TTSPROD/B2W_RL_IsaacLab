"""Isolated PhysX cooked-hull model, retaining the frozen source-shape control."""
import json
import math
import mujoco
import numpy as np
from physics57_protocol import ROOT, save_json, sha256
from contact57_model import geometry, copy_frames, add_shapes, controller, make_model as source_model
from physics57_mujoco_model import adapt_model
from sim2sim_mujoco_b2w import DEFAULT_XML
from locomotion57_protocol import terrain_boxes

BASE = ROOT/'logs/contact57b_20260925'
CONFIG = ROOT/'configs/contact57b_diagnostics_20260925.json'
COOKED = ROOT/'configs/contact57b_cooked_geometry_20260925.json'


def make_model(variant,dt=.002,*,terrain='flat'):
    if variant=='source_shapes':
        return source_model(variant,dt,terrain=terrain)
    if variant!='cooked_shapes':
        raise ValueError(variant)
    source = json.loads(COOKED.read_text())
    spec = mujoco.MjSpec.from_file(str(DEFAULT_XML))
    copy_frames(spec)
    add_shapes(spec,source)
    definition = terrain_boxes(terrain)
    for i,box in enumerate(definition['boxes']):
        pitch=box['pitch']
        spec.worldbody.add_geom(name=f'contact57b_terrain_{i}',type=mujoco.mjtGeom.mjGEOM_BOX,
            size=np.asarray(box['size'])/2,pos=box['pos'],quat=[math.cos(pitch/2),0,math.sin(pitch/2),0],
            friction=[1.,.005,.0001],condim=3,contype=2,conaffinity=1)
    model=spec.compile()
    model.opt.timestep=dt
    return adapt_model(model,'mechanics_implicit',source['compiled']),definition


def impact_targets(case,t):
    from check_policy_contract import load_contract
    target=np.asarray(load_contract()['default_dof_pos']).copy()
    if case=='roll_brake' and 1 <= t < 2.5:
        target[12:]=4.
    return target


def freeze():
    raw=BASE/'cooking.json'
    cooked=json.loads(raw.read_text())
    source=geometry()
    rows={r['body']:r for r in cooked['rows']}
    for shape in source['shapes']:
        if shape['type']=='Mesh':
            row=rows[shape['body']]
            assert row['status'].endswith('RESULT_VALID') and len(row['hulls'])==1
            shape['hull_vertices_body_m']=row['hulls'][0]['vertices_body_m']
            shape['source_bounds_body_m']=shape.pop('bounds_body_m')
            points=np.asarray(shape['hull_vertices_body_m'])
            shape['bounds_body_m']=[points.min(axis=0).tolist(),points.max(axis=0).tolist()]
            shape.pop('hull_volume_m3')
    source['cooking_sha256']=sha256(raw)
    source['note']='isolated PhysX cooking with source-authored settings; not direct live shape buffer readback'
    save_json(COOKED,source)
    save_json(CONFIG,{'schema':'contact57b_diagnostics_v1','policy':19999,
        'excluded_policy':10000,'cooked_geometry_sha256':sha256(COOKED),
        'policy_dt_s':.02,'seeds':[7201,7202,7203,7204],
        'micro_screen':{'policies':[19999],'variants':['cooked_shapes'],'terrains':['flat','up_14x32'],
            'cases':{'flat':['vx_+0.50','vx_+1.00'],'up_14x32':['forward_0.30','forward_0.70','interrupted']},
            'seeds':[7201,7202,7203,7204],'dt_s':.002},
        'impact':{'cases':['drop','roll_brake'],'duration_s':4.,'root_height_m':{'drop':.85,'roll_brake':.65},
            'dt_s':[.005,.002],'isaac_robot_restitution':[1.,.5,0.],
            'isaac_ground_restitution':1.,'mujoco_shapes':['source_shapes','cooked_shapes'],
            'mujoco_solref_timeconst_s':.02,'mujoco_solref_dampratio':[.5,1.,2.],
            'interpretation':'open-loop whole-robot sensitivity, not an estimate of restitution; no mapping between coefficient and solref ratio'},
        'selection':'cooked geometry chosen by model provenance; no score-based solver choice',
        'budget':'20 new policy episodes, 12 Isaac and 24 MuJoCo 4-second open-loop probes; no PPO/server/hardware',
        'source_sha256':sha256(__file__)})
    print('FROZEN',CONFIG,flush=True)


if __name__=='__main__':
    freeze()
