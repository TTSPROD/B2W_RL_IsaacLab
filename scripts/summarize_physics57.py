"""Validate the bounded physics diagnosis and publish compact evidence."""
from __future__ import annotations
from collections import Counter,defaultdict
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from physics57_protocol import ROOT,BASE,CONFIG,VARIANTS,sha256

OUT=ROOT/'docs/results/evidence/physics57_20260925'


def load(path):
    data=json.loads(path.read_text())
    for field in ('config_sha256','contact_states_config_sha256'):
        if field in data:
            config=CONFIG if field=='config_sha256' else ROOT/'configs/physics57_contact_states_20260925.json'
            assert data[field]==sha256(config),path
    if 'trace_file' in data:
        assert sha256(ROOT/data['trace_file'])==data['trace_sha256'],path
    elif 'trace_path' in data:
        assert sha256(data['trace_path'])==data['trace_sha256'],path
    return data


def main():
    expected=[BASE/f'isaac_{suite}_{dt:g}.json' for suite in ('airborne','contact','contact_states') for dt in (.005,.002)]
    expected += [BASE/f'mujoco_{suite}_{v}_{dt:g}.json' for suite in ('airborne','contact') for v in VARIANTS for dt in (.005,.002,.001)]
    expected += [BASE/f'mujoco_contact_states_{v}_{dt:g}.json' for v in ('vendor','damping_only','mechanics_implicit') for dt in (.005,.002,.001)]
    expected += [BASE/f'micro_{t}_{p}_{v}.json' for v in ('vendor','damping_only','mechanics_implicit') for t in ('flat','up_14x32') for p in (10000,19999)]
    expected += [BASE/f'adapter_control4/mujoco_up_14x32_{p}.json' for p in (10000,19999)]
    all_data={p.stem:load(p) for p in expected}
    assert len(all_data)==71
    source=all_data['isaac_contact_0.005']['compiled']
    vendor=all_data['mujoco_airborne_vendor_0.002']['compiled']
    aligned=all_data['mujoco_airborne_mechanics_implicit_0.002']['compiled']
    body_rows=[]
    for i,name in enumerate(source['body_names']):
        original=next(b for b in vendor['bodies'] if b['name']==name.replace('_foot','_wheel_link'))
        adapted=next(b for b in aligned['bodies'] if b['name']==original['name'])
        body_rows.append({'body':name,'isaac_mass_kg':source['mass_kg'][i],
            'vendor_mass_kg':original['mass_kg'],
            'vendor_com_delta_m':(np.asarray(original['com_m'])-source['com_pose_b_wxyz'][i][:3]).tolist(),
            'vendor_inertia_max_abs_delta_kg_m2':float(np.max(np.abs(np.asarray(original['inertia_body_frame_kg_m2'])-source['inertia_body_frame_kg_m2'][i]))),
            'adapted_mass_abs_delta_kg':abs(adapted['mass_kg']-source['mass_kg'][i]),
            'adapted_com_max_abs_delta_m':float(np.max(np.abs(np.asarray(adapted['com_m'])-source['com_pose_b_wxyz'][i][:3]))),
            'adapted_inertia_max_abs_delta_kg_m2':float(np.max(np.abs(np.asarray(adapted['inertia_body_frame_kg_m2'])-source['inertia_body_frame_kg_m2'][i])))})
    air=[]
    for dt in (.005,.002,.001):
        refdt=.002 if dt==.001 else dt
        ref=np.load(BASE/f'isaac_airborne_{refdt:g}.npz')
        for v in VARIANTS:
            d=all_data[f'mujoco_airborne_{v}_{dt:g}']
            a=np.load(ROOT/d['trace_file'])
            assert np.max(a['base_hip_force'])==0
            air.append({'variant':v,'dt_s':dt,'isaac_reference_dt_s':refdt,
                'leg_q_max_abs_delta_rad_by_case':np.max(np.abs(a['q'][:,:,:12]-ref['q'][:,:,:12]),axis=(0,2)).tolist(),
                'wheel_steady_rad_s':np.median(a['dq'][100:125,4,12:],axis=0).tolist(),
                'wheel_stop_peak_rad_s':float(np.max(np.abs(a['dq'][-20:,4,12:]))),
                'kinematic_position_max_abs_delta_m':max(r['position_error_m'] for pose in d['kinematic_comparison'] for r in pose),
                'kinematic_rotation_max_delta_rad':max(r['rotation_error_rad'] for pose in d['kinematic_comparison'] for r in pose)})
    contact=[]
    for dt in (.005,.002,.001):
        refdt=.002 if dt==.001 else dt
        ref=np.load(BASE/f'isaac_contact_states_{refdt:g}.npz')
        for v in ('vendor','damping_only','mechanics_implicit'):
            d=all_data[f'mujoco_contact_states_{v}_{dt:g}']
            for i,r in enumerate(d['records']):
                assert r['finite']
                contact.append({'variant':v,'dt_s':dt,'isaac_reference_dt_s':refdt,
                    'case':r['case'],'snapshot_time_s':r['snapshot_time_s'],
                    'root_position_delta_m':float(np.linalg.norm(np.asarray(r['final_root_pose'][:3])-ref['root'][-1,i,:3])),
                    'leg_q_max_abs_delta_rad':float(np.max(np.abs(np.asarray(r['final_joint_pos'][:12])-ref['q'][-1,i,:12]))),
                    'joint_dq_max_abs_delta_rad_s':float(np.max(np.abs(np.asarray(r['final_joint_vel'])-ref['dq'][-1,i]))),
                    'base_hip_force_peak_n':r['base_hip_force_peak_n']})
    # Long replay can leave its 2 m wide physical lane. Flag that limitation;
    # never interpret a free fall after leaving the support as contact parity.
    long_contact=[]
    for v in VARIANTS:
        d=all_data[f'mujoco_contact_{v}_0.002']
        a=np.load(ROOT/d['trace_file'])
        for i,case in enumerate(d['cases']):
            outside=np.flatnonzero((np.abs(a['root'][:,i,1])>1.) | (np.abs(a['root'][:,i,0])>40.))
            long_contact.append({'variant':v,'case':case,
                'physical_lane_exit_time_s':float((outside[0]+1)*.02) if len(outside) else None,
                'long_horizon_is_not_parity_gate':True})
    micro=[]
    parity=[]
    for name,d in all_data.items():
        if not name.startswith('micro_'):
            continue
        for r in d['records']:
            micro.append({'variant':d['variant'],**r})
        if d['variant']=='vendor':
            first=d['records'][0]
            old=ROOT/f'logs/locomotion57_upstream_20260925/development/mujoco_{first["terrain"]}_{first["policy"]}.json'
            old_data=json.loads(old.read_text())
            lookup={(r['case'],r['seed']):r for r in old_data['records']}
            assert all(r['outcome']==lookup[(r['case'],r['seed'])]['outcome'] for r in d['records'])
            old_trace=np.load(old.with_suffix('.npz'))
            new_trace=np.load(ROOT/d['trace_file'])
            deltas={}
            for case in new_trace.files:
                a,b=old_trace[case][:,:4],new_trace[case]
                assert np.array_equal(np.isnan(a),np.isnan(b)),(name,case)
                deltas[case]=float(np.nanmax(np.abs(a-b)))
            same_batch_exact=all(value==0 for value in deltas.values())
            if first['terrain']=='up_14x32':
                control=all_data[f'mujoco_up_14x32_{first["policy"]}']
                control_trace=np.load(control['trace_path'])
                same_batch_exact=all(np.array_equal(control_trace[c],new_trace[c],equal_nan=True) for c in new_trace.files)
                assert same_batch_exact,(name,'original evaluator with four seeds')
            parity.append({'file':name,'episodes':len(d['records']),
                'outcomes_match_original_16_seed_batch':True,
                'original_16_seed_batch_trace_max_abs_difference_by_case':deltas,
                'original_evaluator_same_batch_size_exact':same_batch_exact})
    assert len(micro)==120
    keys={(r['variant'],r['policy'],r['terrain'],r['case'],r['seed']) for r in micro}
    assert len(keys)==120
    grouped=defaultdict(list)
    for r in micro:
        grouped[(r['variant'],r['policy'])].append(r)
    totals=[{'variant':v,'policy':p,'episodes':len(rows),'outcomes':dict(Counter(r['outcome'] for r in rows)),
        'all_failure_flags':dict(Counter(f for r in rows for f in r['failure_flags']))} for (v,p),rows in sorted(grouped.items())]
    case_rows=[]
    for v in ('vendor','damping_only','mechanics_implicit'):
        for p in (10000,19999):
            for terrain in ('flat','up_14x32'):
                for case in sorted({r['case'] for r in micro if r['terrain']==terrain}):
                    rows=[r for r in micro if (r['variant'],r['policy'],r['terrain'],r['case'])==(v,p,terrain,case)]
                    case_rows.append({'variant':v,'policy':p,'terrain':terrain,'case':case,
                        'success':sum(r['outcome']=='success' for r in rows),'unsafe':sum(r['outcome']=='unsafe' for r in rows),'episodes':len(rows)})
    contact_dt={}
    for suite in ('airborne','contact_states'):
        a=np.load(BASE/f'isaac_{suite}_0.005.npz')
        b=np.load(BASE/f'isaac_{suite}_0.002.npz')
        contact_dt[suite]={'leg_q_max_abs_delta_rad':float(np.max(np.abs(a['q'][:,:,:12]-b['q'][:,:,:12]))),
            'root_position_max_l2_delta_m':float(np.max(np.linalg.norm(a['root'][:,:,:3]-b['root'][:,:,:3],axis=2)))}
    evidence={'schema':'physics57_diagnostics_results_v1','config_sha256':sha256(CONFIG),
        'contact_states_config_sha256':sha256(ROOT/'configs/physics57_contact_states_20260925.json'),
        'body_rows':body_rows,'isaac_compiled':source,'mujoco_vendor_compiled':vendor,
        'mujoco_mechanics_implicit_compiled':aligned,'airborne_rows':air,
        'contact_states_rows':contact,'isaac_dt_sensitivity':contact_dt,'long_contact_limits':long_contact,
        'micro_totals':totals,'micro_case_rows':case_rows,'vendor_reproduction':parity,
        'micro_episode_outcomes':[{k:r[k] for k in ('variant','policy','terrain','case','seed','outcome','failure_flags')} for r in micro],
        'decision':'mechanical adapter remains opt-in diagnostic; contact/geometry parity and policy acceptance open',
        'raw_manifests':[{'file':str(p.relative_to(ROOT)),'sha256':sha256(p),
                          **{k:all_data[p.stem][k] for k in ('trace_file','trace_sha256') if k in all_data[p.stem]}} for p in expected]}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'summary.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for row in totals:
        print(row)
    print('AIRBORNE',[(r['variant'],max(r['leg_q_max_abs_delta_rad_by_case']),r['wheel_steady_rad_s'][0]) for r in air if r['dt_s']==.002])
    print('CONTACT',[(v,max(r['leg_q_max_abs_delta_rad'] for r in contact if r['variant']==v and r['dt_s']==.002)) for v in ('vendor','damping_only','mechanics_implicit')])
    print('ISAAC_DT',contact_dt)
    print('VERIFIED',len(expected),'result files,',len(micro),'policy episodes; baseline outcomes and same-batch original evaluator traces verified')


if __name__=='__main__':
    main()
