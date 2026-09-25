"""Verify paired controls and summarize the frozen collision diagnosis."""
from collections import Counter, defaultdict
import json
import numpy as np
from physics57_protocol import ROOT, sha256, save_json
from contact57_model import BASE, CONFIG, GEOMETRY, VARIANTS, geometry, make_model
from probe_contact57 import source_support, model_support

OUT = ROOT/'docs/results/evidence/contact57_20260925'
OLD = ROOT/'logs/physics57_20260925'


def main():
    files = [BASE/'static.json']+[BASE/f'states_{v}_{dt:g}.json' for v in VARIANTS for dt in (.005,.002,.001)]
    files += [BASE/f'micro_{t}_{p}_source_shapes.json' for t in ('flat','up_14x32') for p in (10000,19999)]
    data = {p.stem:json.loads(p.read_text()) for p in files}
    for path in files:
        item = data[path.stem]
        assert item['config_sha256'] == sha256(CONFIG),path
        assert item['geometry_sha256'] == sha256(GEOMETRY),path
        assert item['adapter_sha256'] == sha256(ROOT/'scripts/contact57_model.py'),path
        assert item['mechanics_adapter_sha256'] == sha256(ROOT/'scripts/physics57_mujoco_model.py'),path
        script = 'eval_contact57_micro.py' if path.stem.startswith('micro_') else 'probe_contact57.py'
        assert item['source_sha256'] == sha256(ROOT/'scripts'/script),path
        if 'trace_file' in item:
            assert item['trace_sha256'] == sha256(ROOT/item['trace_file']),path
    contact,control_checks,dt_changes = [],[],[]
    for dt in (.005,.002,.001):
        refdt = min(dt,.005) if dt != .001 else .002
        reference = np.load(OLD/f'isaac_contact_states_{refdt:g}.npz')
        old = json.loads((OLD/f'mujoco_contact_states_mechanics_implicit_{dt:g}.json').read_text())
        new = data[f'states_mechanics_control_{dt:g}']
        control_errors = defaultdict(float)
        for i,row in enumerate(new['records']):
            for key in ('final_root_pose','final_joint_pos','final_joint_vel','base_hip_force_peak_n'):
                error = float(np.max(np.abs(np.asarray(row[key])-old['records'][i][key])))
                control_errors[key] = max(control_errors[key],error)
                np.testing.assert_allclose(row[key],old['records'][i][key],atol=1e-9,rtol=0)
        control_checks.append({'dt_s':dt,'states':16,'max_abs_deltas':dict(control_errors),
            'note':'roundoff from matrix vs scipy rotation application; numerical control tolerance 1e-9'})
        for variant in VARIANTS:
            for i,row in enumerate(data[f'states_{variant}_{dt:g}']['records']):
                assert row['finite']
                contact.append({'variant':variant,'dt_s':dt,'isaac_reference_dt_s':refdt,
                    'case':row['case'],'snapshot_time_s':row['snapshot_time_s'],
                    'leg_q_max_abs_delta_rad':float(np.max(np.abs(np.asarray(row['final_joint_pos'][:12])-reference['q'][-1,i,:12]))),
                    'root_position_delta_m':float(np.linalg.norm(np.asarray(row['final_root_pose'][:3])-reference['root'][-1,i,:3])),
                    'joint_dq_max_abs_delta_rad_s':float(np.max(np.abs(np.asarray(row['final_joint_vel'])-reference['dq'][-1,i]))),
                    **{k:row[k] for k in ('initial_contacts','final_contacts','sum_normal_impulse_abs_ns','max_penetration_m')}})
    for variant in VARIANTS:
        a = data[f'states_{variant}_0.002']['records']
        b = data[f'states_{variant}_0.001']['records']
        dt_changes.append({'variant':variant,
            'max_leg_q_delta_rad':max(float(np.max(np.abs(np.asarray(x['final_joint_pos'][:12])-y['final_joint_pos'][:12]))) for x,y in zip(a,b)),
            'max_root_position_delta_m':max(float(np.linalg.norm(np.asarray(x['final_root_pose'][:3])-y['final_root_pose'][:3])) for x,y in zip(a,b))})
    micro = []
    paired = []
    for terrain in ('flat','up_14x32'):
        for policy in (10000,19999):
            new = data[f'micro_{terrain}_{policy}_source_shapes']
            old_path = OLD/f'micro_{terrain}_{policy}_mechanics_implicit.json'
            old = json.loads(old_path.read_text())
            assert new['policy_export_sha256'] == old['policy_export_sha256']
            assert new['protocol'] == old['protocol']
            assert [(r['case'],r['seed']) for r in new['records']] == [(r['case'],r['seed']) for r in old['records']]
            paired.append({'file':str(old_path.relative_to(ROOT)),'sha256':sha256(old_path),
                'trace_file':old['trace_file'],'trace_sha256':old['trace_sha256']})
            assert sha256(ROOT/old['trace_file']) == old['trace_sha256']
            for label,item in (('mechanics_control',old),('source_shapes',new)):
                micro += [{'variant':label,**r} for r in item['records']]
    assert len(micro) == 80 and len(contact) == 192
    grouped = defaultdict(list)
    for row in micro:
        grouped[(row['variant'],row['policy'])].append(row)
    totals = [{'variant':v,'policy':p,'episodes':len(rows),
        'outcomes':dict(Counter(r['outcome'] for r in rows)),
        'failure_flags':dict(Counter(f for r in rows for f in r['failure_flags']))} for (v,p),rows in sorted(grouped.items())]
    cases = []
    for (v,p),rows in sorted(grouped.items()):
        for terrain,case in sorted({(r['terrain'],r['case']) for r in rows}):
            selected = [r for r in rows if (r['terrain'],r['case']) == (terrain,case)]
            cases.append({'variant':v,'policy':p,'terrain':terrain,'case':case,
                'success':sum(r['outcome']=='success' for r in selected),
                'unsafe':sum(r['outcome']=='unsafe' for r in selected),'episodes':len(selected)})
    static = []
    for profile in data['static']['profiles']:
        static.append({'variant':profile['variant'],'active_robot_shapes':profile['active_robot_shapes'],
            'max_position_error_m':max(r['position_error_m'] for pose in profile['kinematics'] for r in pose),
            'max_rotation_error_rad':max(r['rotation_error_rad'] for pose in profile['kinematics'] for r in pose),
            'max_shape_support_error_m':max((r['max_support_error_m'] for r in profile.get('shape_support_comparison',[])),default=None)})
    model,_ = make_model('mechanics_control',case='stand')
    directions = np.random.default_rng(20260925).normal(size=(4096,3))
    directions /= np.linalg.norm(directions,axis=1,keepdims=True)
    supports = []
    for shape in geometry()['shapes']:
        if shape['type'] != 'Mesh':
            continue
        body = model.body(shape['body'].replace('_foot','_wheel_link')).id
        geoms = [g for g in range(model.ngeom) if model.geom_bodyid[g]==body and (model.geom_contype[g] or model.geom_conaffinity[g])]
        before = np.max([model_support(model,g,directions) for g in geoms],axis=0)
        error = float(np.max(np.abs(before-source_support(shape,directions))))
        supports.append({'body':shape['body'],'vendor_collision_count':len(geoms),'source_collision_count':1,
            'max_sampled_union_support_delta_m':error,'source_bounds_body_m':shape['bounds_body_m']})
    result = {'schema':'contact57_results_v1','config_sha256':sha256(CONFIG),
        'geometry_sha256':sha256(GEOMETRY),'static':static,'source_geometry_comparison':supports,
        'contact_rows':contact,'mujoco_dt_sensitivity':dt_changes,'control_reproduction':control_checks,
        'micro_totals':totals,'micro_case_rows':cases,
        'micro_episode_outcomes':[{k:r[k] for k in ('variant','policy','terrain','case','seed','outcome','failure_flags')} for r in micro],
        'counts':{'new_policy_episodes':40,'reused_policy_controls':40,'new_contact_state_probes':192},
        'decision':'source_shapes remains opt-in; policy not accepted; cooked shapes and solver/restitution unresolved',
        'raw_manifests':[{'file':str(p.relative_to(ROOT)),'sha256':sha256(p),
            **{k:data[p.stem][k] for k in ('trace_file','trace_sha256') if k in data[p.stem]}} for p in files],
        'reused_control_manifests':paired}
    save_json(OUT/'summary.json',result)
    print('STATIC',static)
    for variant in VARIANTS:
        selected = [r for r in contact if r['variant']==variant and r['dt_s']==.002]
        print('CONTACT',variant,'q max',max(r['leg_q_max_abs_delta_rad'] for r in selected),
            'q median',np.median([r['leg_q_max_abs_delta_rad'] for r in selected]),
            'root max',max(r['root_position_delta_m'] for r in selected))
    print('DT',dt_changes)
    for row in totals:
        print('MICRO',row)
    print('SUPPORT',supports)
    print('VERIFIED',len(files),'result files; 48 numerically reproduced control states; 40 new policy episodes')


if __name__ == '__main__':
    main()
