"""Fail-closed, predeclared LR probe decision; retention and improvement are separate."""
from collections import defaultdict
import math
import statistics
import locomotion_v2_lr_pilot_protocol as protocol


def decide(records,plan,coverage):
    policies=['24650']+[f'{arm}_{24650+step}' for arm in plan['arms'] for step in plan['probe_updates']]
    expected={(p,t,c.name,s) for p in policies for t in protocol.TERRAINS
              for c in protocol.cases_for(t) for s in plan['evaluation']['reset_seeds']}
    keys=[(str(r['policy']),r['terrain'],r['case'],r['seed']) for r in records]
    if len(keys)!=len(expected) or set(keys)!=expected:
        raise ValueError('Incomplete/duplicate/foreign LR probe evidence')
    grouped=defaultdict(list)
    for record in records: grouped[str(record['policy'])].append(record)
    metrics={}
    for policy,rows in grouped.items():
        cells=defaultdict(int)
        for r in rows: cells[f'{r["terrain"]}/{r["case"]}']+=int(r['covered_scenario_success'])
        targets={}
        for case,axis,key in (('lateral',1,'linear_response_ratio'),('yaw',2,'angular_response_ratio')):
            values=[s[key] for r in rows if r['case']==case for s in r['segments']
                    if abs(abs(s['command'][axis])-.3)<1e-6 and key in s]
            targets[case]=statistics.mean(values) if len(values)==20 and all(math.isfinite(v) for v in values) else None
        metrics[policy]={'cells':dict(cells),'targets':targets,
            'success':sum(r['covered_scenario_success'] for r in rows),
            'unsafe':sum(bool(r['safety']['unsafe_flags']) for r in rows),
            'wheel_saturation':max(max(r['safety']['torque_saturation_fraction'][12:]) for r in rows),
            'leg_saturation':max(max(r['safety']['torque_saturation_fraction'][:12]) for r in rows)}
    baseline=metrics['24650'];rules=plan['advancement'];decisions={}
    coverage_ok={arm:all(coverage.get(arm,{}).get(group,{}).get('min_full_episodes_per_env',0)>=
                plan['coverage']['required_full_target_episodes_per_env'] for group in ('flat','rough','stairs_up','stairs_down'))
                 for arm in plan['arms']}
    for step in plan['probe_updates']:
        p,control=f'lrlow_{24650+step}',f'lrcontrol_{24650+step}'
        candidate,reference=metrics[p],metrics[control]
        reasons=[]
        if step not in rules['eligible_updates']: reasons.append('retrospective checkpoint; insufficient full-cycle budget')
        if not all(coverage_ok.values()): reasons.append('missing two full target episodes per environment')
        if candidate['unsafe']: reasons.append('unsafe')
        deficits={name:max(0,value-candidate['cells'][name]) for name,value in baseline['cells'].items()}
        control_deficits={name:max(0,value-reference['cells'][name]) for name,value in baseline['cells'].items()}
        for cell,value in candidate['cells'].items():
            if value<max(baseline['cells'][cell],reference['cells'][cell]): reasons.append(cell+': success regression')
        for target in rules['targets']:
            value=candidate['targets'][target];b=baseline['targets'][target];c=reference['targets'][target]
            if value is None or b is None or c is None: reasons.append(target+': incomplete target data');continue
            if value-b<rules['target_mean_gain_vs_parent']: reasons.append(target+': insufficient gain vs parent')
            if value-c<rules['target_mean_gain_vs_control']: reasons.append(target+': insufficient gain vs control')
        for group in ('wheel','leg'):
            if candidate[group+'_saturation']>baseline[group+'_saturation']+rules[group+'_saturation_fraction_extra_max']:
                reasons.append(group+': saturation regression')
        retained=candidate['unsafe']==0 and sum(deficits.values())==0
        decisions[p]={'advance':not reasons,'matched_control':control,'updates':step,'reasons':reasons,
            'retention_pass':retained,'parent_cell_success_deficit':sum(deficits.values()),
            'matched_control_cell_success_deficit':sum(control_deficits.values()),
            'stability_hypothesis_supported':step in rules['eligible_updates'] and all(coverage_ok.values()) and
                retained and (reference['unsafe']>0 or sum(control_deficits.values())>0)}
    selected=next((p for p,d in decisions.items() if d['advance']),None)
    return {'metrics':metrics,'decisions':decisions,'selected':selected,'coverage_ok':coverage_ok,
            'qualification':False,'hardware_approval':False,'automatic_promotion':False}
