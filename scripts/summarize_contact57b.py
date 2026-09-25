"""Summarize isolated cooking, open-loop sensitivity and 19999-only failures."""
from collections import Counter
import json
import numpy as np
from scipy.spatial.transform import Rotation
from contact57b_model import BASE,CONFIG,COOKED,make_model,controller
from physics57_protocol import ROOT,sha256,save_json

OUT=ROOT/'docs/results/evidence/contact57b_20260925'


def main():
    cfg=json.loads(CONFIG.read_text())
    paths=[BASE/'cooking.json',BASE/'static.json']
    paths += [BASE/f'impact_isaac_r{r:g}_{dt:g}.json' for dt in (.005,.002) for r in (1.,.5,0.)]
    paths += [BASE/f'impact_mujoco_{v}_d{d:g}_{dt:g}.json' for v in ('source_shapes','cooked_shapes') for dt in (.005,.002) for d in (.5,1.,2.)]
    paths += [BASE/f'micro_{t}_19999_cooked_shapes.json' for t in ('flat','up_14x32')]
    all_data={p.stem:json.loads(p.read_text()) for p in paths}
    for path in paths:
        item=all_data[path.stem]
        if 'config_sha256' in item:
            assert item['config_sha256']==sha256(CONFIG),path
        if 'trace_file' in item:
            assert item['trace_sha256']==sha256(ROOT/item['trace_file']),path
    impact=[]
    for stem,item in all_data.items():
        if not stem.startswith('impact_'):
            continue
        arrays=np.load(ROOT/item['trace_file'])
        dt=item['dt_s']
        for i,case in enumerate(item['cases']):
            z=arrays['root'][:,i,2]
            force=arrays['force_z'][:,i]
            contact=np.flatnonzero(force>5.)
            impact.append({'engine':item['engine'],'variant':item.get('variant'),
                'restitution':item.get('restitution'),'dampratio':item.get('dampratio'),
                'dt_s':dt,'case':case,'first_contact_s':float((contact[0]+1)*dt) if len(contact) else None,
                'vertical_force_peak_n':float(force.max()),'vertical_impulse_ns':float(force.sum()*dt),
                'root_z_min_m':float(z.min()),'root_z_final_m':float(z[-1]),
                'root_z_max_after_impact_m':float(z[contact[0]:].max()) if len(contact) else None,
                'final_x_m':float(arrays['root'][-1,i,0]),
                'leg_torque_peak_nm':float(np.abs(arrays['tau'][:,i,:12]).max())})
    comparisons=[]
    for dt in (.005,.002):
        for restitution in (1.,.5,0.):
            ia=np.load(ROOT/all_data[f'impact_isaac_r{restitution:g}_{dt:g}']['trace_file'])
            for variant in ('source_shapes','cooked_shapes'):
                mj=np.load(ROOT/all_data[f'impact_mujoco_{variant}_d1_{dt:g}']['trace_file'])
                for i,case in enumerate(cfg['impact']['cases']):
                    comparisons.append({'case':case,'dt_s':dt,'isaac_restitution':restitution,'mujoco_variant':variant,
                        'mujoco_dampratio':1.,'root_position_rmse_m':float(np.sqrt(np.mean(np.sum((ia['root'][:,i,:3]-mj['root'][:,i,:3])**2,axis=1)))),
                        'leg_q_max_abs_delta_rad':float(np.max(np.abs(ia['q'][:,i,:12]-mj['q'][:,i,:12])))})
    new=[]
    old=[]
    for terrain in ('flat','up_14x32'):
        item=all_data[f'micro_{terrain}_19999_cooked_shapes']
        control_path=ROOT/f'logs/contact57_20260925/micro_{terrain}_19999_source_shapes.json'
        control=json.loads(control_path.read_text())
        assert item['policy_export_sha256']==control['policy_export_sha256']
        assert item['protocol']==control['protocol']
        new.extend(item['records'])
        old.extend(control['records'])
    assert len(new)==20 and all(r['policy']==19999 for r in new)
    assert [(r['case'],r['seed']) for r in new]==[(r['case'],r['seed']) for r in old]
    case_rows=[]
    for case in sorted(set(r['case'] for r in new)):
        a=[r for r in old if r['case']==case]
        b=[r for r in new if r['case']==case]
        case_rows.append({'case':case,'episodes':len(b),'source_success':sum(r['outcome']=='success' for r in a),
            'cooked_success':sum(r['outcome']=='success' for r in b),'cooked_unsafe':sum(r['outcome']=='unsafe' for r in b)})
    trace=np.load(BASE/'micro_up_14x32_19999_cooked_shapes.npz')
    failure=[]
    model,_=make_model('cooked_shapes',terrain='up_14x32')
    ctl=controller(model)
    import mujoco
    for case in ('forward_0.30','forward_0.70'):
        motion=trace[case]
        detail=trace[case+'__detail']
        for i,seed in enumerate(cfg['seeds']):
            row=next(r for r in new if r['case']==case and r['seed']==seed)
            # Fixed final five seconds of the nonzero segment: t in [27,32].
            late=detail[1350:1600,i]
            moving=detail[100:1600,i]
            yaw=Rotation.from_quat(moving[:,3:7][:,[1,2,3,0]]).as_euler('xyz')[:,2]
            wheel_speed=late[:,35:39]
            # q/dq offsets: root7 + q16 + dq16 + tau16 + target16.
            wheel_tau=late[:,51:55]
            wheel_target=late[:,67:71]
            state=mujoco.MjData(model)
            state.qpos[:7]=late[-1,:7]
            state.qpos[ctl.qids]=late[-1,7:23]
            mujoco.mj_kinematics(model,state)
            centers={n:state.xpos[model.body(n+'_wheel_link').id].tolist() for n in ('FR','FL','RR','RL')}
            failure.append({'case':case,'seed':seed,'outcome':row['outcome'],'failure_flags':row['failure_flags'],
                'mean_vx_nonzero_m_s':row['segments'][0]['mean_velocity'][0],
                'late_mean_vx_m_s':float(motion[1350:1600,i,0].mean()),
                'late_x_progress_m':float(late[-1,0]-late[0,0]),'x_at_32s_m':float(late[-1,0]),
                'yaw_change_nonzero_rad':float(np.unwrap(yaw)[-1]-np.unwrap(yaw)[0]),
                'late_wheel_saturation_fraction':(np.abs(wheel_tau)>=19.8).mean(axis=0).tolist(),
                'late_wheel_mean_speed_rad_s':wheel_speed.mean(axis=0).tolist(),
                'late_wheel_mean_target_rad_s':wheel_target.mean(axis=0).tolist(),
                'late_leg_target_error_rms_rad':np.sqrt(np.mean((late[:,55:67]-late[:,7:19])**2,axis=0)).tolist(),
                'wheel_centers_at_32s':centers,
                'note':'policy-step diagnostic samples, not saturation duration or contact slip; no navigation gate'})
    result={'schema':'contact57b_results_v1','config_sha256':sha256(CONFIG),'cooked_geometry_sha256':sha256(COOKED),
        'static':all_data['static']['rows'],'runtime_offsets':all_data['impact_isaac_r1_0.005']['runtime_offsets'],
        'cooking_statuses':[{'body':r['body'],'status':r['status']} for r in all_data['cooking']['rows']],
        'impact_rows':impact,'matched_dt_default_solver_comparisons':comparisons,
        'micro_totals':{'policy':19999,'new_episodes':20,'source_outcomes':dict(Counter(r['outcome'] for r in old)),
            'cooked_outcomes':dict(Counter(r['outcome'] for r in new)),
            'cooked_failure_flags':dict(Counter(f for r in new for f in r['failure_flags']))},
        'micro_case_rows':case_rows,'failure_diagnostics':failure,
        'episode_outcomes':[{k:r[k] for k in ('case','seed','outcome','failure_flags')} for r in new],
        'raw_manifests':[{'file':str(p.relative_to(ROOT)),'sha256':sha256(p),
            **{k:all_data[p.stem][k] for k in ('trace_file','trace_sha256') if k in all_data[p.stem]}} for p in paths],
        'decision':'source/cooked geometry sensitivity confirmed; no policy promotion, no score-selected solver; 10000 excluded'}
    save_json(OUT/'summary.json',result)
    print('TOTALS',result['micro_totals'])
    for row in failure:
        print('FAILURE',row['case'],row['seed'],row['mean_vx_nonzero_m_s'],row['late_x_progress_m'],row['x_at_32s_m'],row['late_wheel_saturation_fraction'])
    for r in impact:
        if r['case']=='drop' and r['dt_s']==.002:
            print('DROP',r)
    print('VERIFIED',len(paths),'files,20 policy episodes,36 policy-free probes')


if __name__=='__main__':
    main()
