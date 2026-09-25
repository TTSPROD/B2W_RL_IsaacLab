"""Preregistered policy-free drop and rolling/braking contact sensitivity."""
from __future__ import annotations
import argparse
import json
import sys
import numpy as np
from physics57_protocol import ROOT,save_json,sha256
from contact57b_model import BASE,CONFIG,COOKED,make_model,controller,impact_targets


def run_isaac(env,robot,compiled,dt,restitution):
    import torch
    from check_policy_contract import load_contract
    cfg=json.loads(CONFIG.read_text())['impact']
    cases=cfg['cases']
    scene=env.scene
    ids,_=robot.find_joints(load_contract()['joint_names'],preserve_order=True)
    view=robot.root_physx_view
    materials=view.get_material_properties().clone()
    original_materials=materials[0].cpu().numpy().tolist()
    materials[:,:,2]=restitution
    view.set_material_properties(materials,torch.arange(len(cases),device='cpu'))
    offsets={'contact_m':view.get_contact_offsets()[0].cpu().numpy().tolist(),
             'rest_m':view.get_rest_offsets()[0].cpu().numpy().tolist()}
    default=torch.tensor(load_contract()['default_dof_pos'],device=env.device)
    scales=torch.tensor(load_contract()['action_scale'],device=env.device)
    roots=robot.data.default_root_state.clone()
    roots[:,:3]+=scene.env_origins
    roots[:,1]+=torch.arange(len(cases),device=env.device)*4
    for i,case in enumerate(cases):
        roots[i,2]=scene.env_origins[i,2]+cfg['root_height_m'][case]
    q=robot.data.default_joint_pos.clone()
    q[:,ids]=default
    robot.write_root_state_to_sim(roots)
    robot.write_joint_state_to_sim(q,torch.zeros_like(q))
    scene.reset()
    env.sim.forward()
    scene.update(dt)
    records={k:[] for k in ('root','q','dq','tau','force_z','targets')}
    with torch.inference_mode():
        for step in range(round(cfg['duration_s']/.02)):
            target=torch.tensor(np.stack([impact_targets(c,step*.02) for c in cases]),device=env.device,dtype=torch.float32)
            env.action_manager.process_action((target-default)/scales)
            for sub in range(round(.02/dt)):
                env.action_manager.apply_action()
                scene.write_data_to_sim()
                env.sim.step(render=False)
                scene.update(dt)
                root=robot.data.root_state_w.clone()
                root[:,:3]-=scene.env_origins
                root[:,1]-=torch.arange(len(cases),device=env.device)*4
                values={'root':root,'q':robot.data.joint_pos[:,ids],'dq':robot.data.joint_vel[:,ids],
                    'tau':robot.data.applied_torque[:,ids],'targets':target,
                    'force_z':scene['contact_forces'].data.net_forces_w[:,:,2].sum(dim=1)}
                for key,value in values.items():
                    records[key].append(value.cpu().numpy().copy())
    path=BASE/f'impact_isaac_r{restitution:g}_{dt:g}.json'
    trace=path.with_suffix('.npz')
    arrays={k:np.asarray(v) for k,v in records.items()}
    assert all(np.isfinite(v).all() for v in arrays.values())
    np.savez_compressed(trace,**arrays)
    save_json(path,{'engine':'Isaac','restitution':restitution,'dt_s':dt,'cases':cases,
        'original_materials':original_materials,'runtime_offsets':offsets,
        'effective_materials':view.get_material_properties()[0].cpu().numpy().tolist(),
        'config_sha256':sha256(CONFIG),'source_sha256':sha256(__file__),
        'trace_file':str(trace.relative_to(ROOT)),'trace_sha256':sha256(trace)})
    print('DONE',path,flush=True)


def isaac(dt,restitution):
    path=BASE/f'impact_isaac_r{restitution:g}_{dt:g}.json'
    assert not path.exists()
    code=(ROOT/'logs/contact57_20260925/generated_export_geometry.py').read_text(encoding='utf-8')
    substitutions={
        "output = ROOT/'logs/contact57_20260925/isaac_geometry.json'":f'output = ROOT/{str(path.relative_to(ROOT)).replace(chr(92),chr(47))!r}',
        "cases = AIRBORNE if args.suite == 'airborne' else CONTACT":"cases = ('drop','roll_brake')",
        'from export_contact57_geometry import extract\n    extract(env, robot, compiled)':
            f'from probe_contact57b_impacts import run_isaac\n    run_isaac(env, robot, compiled, args.dt, {restitution!r})'}
    for a,b in substitutions.items():
        assert code.count(a)==1,a
        code=code.replace(a,b)
    generated=path.with_suffix('.py')
    assert not generated.exists()
    generated.write_text(code,encoding='utf-8')
    sys.argv=[str(generated),'--suite','contact','--dt',str(dt)]
    exec(compile(code,str(generated),'exec'),{'__file__':str(generated),'__name__':'__main__'})


def mujoco_probe():
    import mujoco
    from check_policy_contract import load_contract
    cfg=json.loads(CONFIG.read_text())['impact']
    for variant in cfg['mujoco_shapes']:
        for dt in cfg['dt_s']:
            for ratio in cfg['mujoco_solref_dampratio']:
                path=BASE/f'impact_mujoco_{variant}_d{ratio:g}_{dt:g}.json'
                assert not path.exists()
                all_records={k:[] for k in ('root','q','dq','tau','force_z','targets')}
                for case in cfg['cases']:
                    model,_=make_model(variant,dt)
                    model.geom_solref[:]=[cfg['mujoco_solref_timeconst_s'],ratio]
                    state=mujoco.MjData(model)
                    ctl=controller(model)
                    state.qpos[:7]=[0,0,cfg['root_height_m'][case],1,0,0,0]
                    state.qpos[ctl.qids]=np.asarray(load_contract()['default_dof_pos'],np.float32)
                    mujoco.mj_forward(model,state)
                    records={k:[] for k in all_records}
                    force=np.zeros(6)
                    for step in range(round(cfg['duration_s']/.02)):
                        target=impact_targets(case,step*.02).astype(np.float32)
                        for _ in range(round(.02/dt)):
                            ctl.apply(state,target)
                            mujoco.mj_step(model,state)
                            fz=0.
                            for k in range(state.ncon):
                                contact=state.contact[k]
                                b1,b2=model.geom_bodyid[contact.geom1],model.geom_bodyid[contact.geom2]
                                if b1 and b2:
                                    continue
                                mujoco.mj_contactForce(model,state,k,force)
                                fz+=(contact.frame.reshape(3,3).T@force[:3])[2]*(1 if b1==0 else -1)
                            values={'root':state.qpos[:7],'q':state.qpos[ctl.qids],'dq':state.qvel[ctl.vids],
                                'tau':state.actuator_force,'force_z':np.asarray(fz),'targets':target}
                            for key,value in values.items():
                                records[key].append(value.copy())
                    for key,values in records.items():
                        all_records[key].append(values)
                arrays={k:np.stack(v,axis=1) for k,v in all_records.items()}
                assert all(np.isfinite(v).all() for v in arrays.values())
                trace=path.with_suffix('.npz')
                np.savez_compressed(trace,**arrays)
                save_json(path,{'engine':'MuJoCo','variant':variant,'dampratio':ratio,'dt_s':dt,
                    'cases':cfg['cases'],'config_sha256':sha256(CONFIG),'source_sha256':sha256(__file__),
                    'adapter_sha256':sha256(ROOT/'scripts/contact57b_model.py'),
                    'trace_file':str(trace.relative_to(ROOT)),'trace_sha256':sha256(trace)})
                print('DONE',path,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine',choices=('isaac','mujoco'))
    parser.add_argument('--dt',type=float,default=.005)
    parser.add_argument('--restitution',type=float,default=1.)
    args=parser.parse_args()
    isaac(args.dt,args.restitution) if args.engine=='isaac' else mujoco_probe()
