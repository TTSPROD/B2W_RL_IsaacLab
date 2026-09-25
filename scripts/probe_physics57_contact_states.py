"""Reset both engines to identical recorded states before a 100 ms contact probe.

The isolated Isaac harness is derived from the checked target-trace probe. Only
initial states, constant targets and horizon are replaced; robot/terrain unchanged.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
from physics57_protocol import ROOT,BASE,CONFIG,sha256,save_json,CONTACT,DT

ADDITION=ROOT/'configs/physics57_contact_states_20260925.json'


def freeze():
    save_json(ADDITION,{'schema':'physics57_paired_contact_states_v1','cases':CONTACT,
        'snapshot_time_s':[1.,3.,5.,7.], 'horizon_s':.1,'dt_s':[.005,.002,.001],
        'isaac_dt_s':[.005,.002], 'variants':['vendor','damping_only','mechanics_implicit'],
        'targets':'constant next policy target after each snapshot; identical in both engines',
        'state':'root link pose, root COM world velocity transformed to MuJoCo origin velocity, joint q/dq',
        'source':str((BASE/'isaac_contact_0.005.npz').relative_to(ROOT)),
        'source_sha256':sha256(BASE/'isaac_contact_0.005.npz'),
        'interpretation':'descriptive state-reset contact diagnosis; no acceptance gate, no tuning to score'})


def fixtures():
    cfg=json.loads(ADDITION.read_text())
    trace=np.load(ROOT/cfg['source'])
    meta=json.loads((BASE/'isaac_contact_0.005.json').read_text())
    rows=[]
    for j,case in enumerate(cfg['cases']):
        for t in cfg['snapshot_time_s']:
            k=round(t/DT)-1
            rows.append({'case':case,'time_s':t,'root':trace['root'][k,j],
                'q':trace['q'][k,j],'dq':trace['dq'][k,j],'target':trace['targets'][k+1,j]})
    return cfg,meta,rows


def isaac(dt):
    cfg,meta,rows=fixtures()
    source=ROOT/'scripts/probe_physics57_isaac.py'
    code=source.read_text(encoding='utf-8')
    # This derivation uses exact, asserted substitutions; the generated code is
    # retained and hashed so the experiment does not hide a modified evaluator.
    def replace(old,new):
        nonlocal code
        assert code.count(old)==1,old
        code=code.replace(old,new)
    replace("tag = f'isaac_{args.suite}_{args.dt:g}'", "tag = f'isaac_contact_states_{args.dt:g}'")
    replace("from physics57_protocol import ROOT, BASE, CONFIG, AIRBORNE, CONTACT, DT, case_boxes, targets, command, save_json, sha256",
        "from physics57_protocol import ROOT, BASE, CONFIG, AIRBORNE, CONTACT, DT, case_boxes, targets, command, save_json, sha256\nfrom probe_physics57_contact_states import fixtures\nstate_cfg, state_meta, state_rows = fixtures()")
    replace("cases = AIRBORNE if args.suite == 'airborne' else CONTACT", "cases = tuple(r['case'] for r in state_rows)")
    replace("duration = 4. if args.suite == 'airborne' else 10.", "duration = state_cfg['horizon_s']")
    replace("    robot.write_root_state_to_sim(roots)\n    robot.write_joint_state_to_sim(positions,velocities)\n    scene.reset()",
        "    for i,row in enumerate(state_rows):\n"+
        "        roots[i] = torch.as_tensor(row['root'],device=env.device)\n"+
        "        roots[i,:3] += scene.env_origins[i]\n"+
        "        roots[i,1] += 4*i\n"+
        "        positions[i,ids] = torch.as_tensor(row['q'],device=env.device)\n"+
        "        velocities[i,ids] = torch.as_tensor(row['dq'],device=env.device)\n"+
        "    robot.write_root_state_to_sim(roots)\n    robot.write_joint_state_to_sim(positions,velocities)\n    scene.reset()")
    replace("model = torch.jit.load(str(export_path(10000)),map_location=env.device).eval() if args.suite=='contact' else None", "model = None")
    replace("np.stack([targets(c,t) for c in cases])", "np.stack([r['target'] for r in state_rows])")
    replace("'compiled':compiled,'kinematics':kinematics,'initial_root':initial_root.tolist(),",
        "'compiled':compiled,'kinematics':kinematics,'initial_root':initial_root.tolist(),\n"+
        "        'snapshot_time_s':[r['time_s'] for r in state_rows],\n"+
        "        'initial_joint_vel':array(velocities[:,ids]).tolist(),\n"+
        "        'contact_states_config_sha256':sha256(ROOT/'configs/physics57_contact_states_20260925.json'),")
    path=BASE/f'generated_isaac_contact_states_{dt:g}.py'
    if path.exists():
        raise FileExistsError(path)
    path.write_text(code,encoding='utf-8')
    sys.argv=[str(path),'--suite','contact','--dt',str(dt)]
    exec(compile(code,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})


def mujoco_probe():
    import mujoco
    from scipy.spatial.transform import Rotation
    from physics57_mujoco_model import reference,make_probe_model,Physics57Controller
    from eval_locomotion57_mujoco import contacts
    cfg,meta,rows=fixtures()
    compiled=reference()['compiled']
    base_i=compiled['body_names'].index('base_link')
    com=np.asarray(compiled['com_pose_b_wxyz'][base_i][:3])
    for variant in cfg['variants']:
        # Each source model has its own COM; keep origin velocity equal, not COM velocity.
        for dt in cfg['dt_s']:
            output=BASE/f'mujoco_contact_states_{variant}_{dt:g}.json'
            if output.exists():
                raise FileExistsError(output)
            all_records=[]
            for row in rows:
                model=make_probe_model(row['case'],variant,dt,compiled,False)
                state=mujoco.MjData(model)
                ctl=Physics57Controller(model,variant)
                root=row['root']
                rot=Rotation.from_quat(root[3:7][[1,2,3,0]])
                state.qpos[:7]=root[:7]
                state.qpos[ctl.qids]=row['q']
                state.qvel[:3]=root[7:10]-np.cross(root[10:13],rot.apply(com))
                state.qvel[3:6]=rot.inv().apply(root[10:13])
                state.qvel[ctl.vids]=row['dq']
                mujoco.mj_forward(model,state)
                protected=[model.body(n).id for n in ('base_link','FL_hip','FR_hip','RL_hip','RR_hip')]
                peak=0.
                for _ in range(round(cfg['horizon_s']/dt)):
                    ctl.apply(state,row['target'])
                    mujoco.mj_step(model,state)
                    peak=max(peak,contacts(model,state,protected))
                all_records.append({'case':row['case'],'snapshot_time_s':row['time_s'],
                    'final_root_pose':state.qpos[:7].tolist(),'final_joint_pos':state.qpos[ctl.qids].tolist(),
                    'final_joint_vel':state.qvel[ctl.vids].tolist(),'base_hip_force_peak_n':peak,
                    'finite':bool(np.isfinite(state.qpos).all() and np.isfinite(state.qvel).all())})
            save_json(output,{'engine':'MuJoCo','variant':variant,'dt_s':dt,'records':all_records,
                'contact_states_config_sha256':sha256(ADDITION),'source_sha256':sha256(__file__),
                'model_adapter_sha256':sha256(ROOT/'scripts/physics57_mujoco_model.py')})
            print('DONE',output,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('freeze','isaac','mujoco'))
    parser.add_argument('--dt',type=float,default=.005)
    args=parser.parse_args()
    if args.mode=='freeze':
        freeze()
    elif args.mode=='isaac':
        isaac(args.dt)
    else:
        mujoco_probe()
