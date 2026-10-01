"""Predeclared A/B advancement rules; no dependency on training or simulator."""
from collections import defaultdict
import statistics


def decide(records,plan):
    grouped=defaultdict(list)
    for record in records:grouped[str(record['policy'])].append(record)
    metrics={}
    for policy,rows in grouped.items():
        targets={}
        for case,axis,key in (('lateral',1,'linear_response_ratio'),('yaw',2,'angular_response_ratio')):
            values=[s[key] for r in rows if r['case']==case for s in r['segments']
                    if abs(abs(s['command'][axis])-.3)<1e-6 and key in s]
            targets[case]=statistics.mean(values) if values else None
        regression={name:sum(r['covered_scenario_success'] for r in rows
                    if (r['terrain'].startswith(name) if name.startswith('stairs') else r['case']==name))
                    for name in plan['advancement']['regression_groups']}
        metrics[policy]={'targets':targets,'regression':regression,
            'success':sum(r['covered_scenario_success'] for r in rows),
            'unsafe':sum(bool(r['safety']['unsafe_flags']) for r in rows),
            'wheel_saturation':max(max(r['safety']['torque_saturation_fraction'][12:]) for r in rows),
            'leg_saturation':max(max(r['safety']['torque_saturation_fraction'][:12]) for r in rows)}
    baseline=metrics['24650'];rules=plan['advancement'];decisions={}
    for updates in plan['probe_updates']:
        policy=f'posture_{24650+updates}';control=f'control_{24650+updates}'
        candidate,reference=metrics[policy],metrics[control]
        reasons=[]
        if candidate['unsafe']:reasons.append('unsafe')
        for target in rules['targets']:
            value=candidate['targets'][target]
            if value is None or baseline['targets'][target] is None or reference['targets'][target] is None:
                reasons.append(target+': missing target segments');continue
            if value-baseline['targets'][target]<rules['target_mean_gain_vs_parent']:
                reasons.append(target+': insufficient gain vs parent')
            if value-reference['targets'][target]<rules['target_mean_gain_vs_control']:
                reasons.append(target+': insufficient gain vs matched control')
        for name in rules['regression_groups']:
            if candidate['regression'][name]<max(baseline['regression'][name],reference['regression'][name]):
                reasons.append(name+': success regression')
        for group in ('wheel','leg'):
            if candidate[group+'_saturation']>baseline[group+'_saturation']+rules[group+'_saturation_fraction_extra_max']:
                reasons.append(group+': saturation regression')
        decisions[policy]={'advance':not reasons,'reasons':reasons,'matched_control':control,'updates':updates}
    eligible=[policy for policy,value in decisions.items() if value['advance']]
    selected=max(eligible,key=lambda p:(min(metrics[p]['targets'].values()),metrics[p]['success'])) if eligible else None
    return {'metrics':metrics,'decisions':decisions,'selected':selected,
            'qualification':False,'hardware_approval':False,'automatic_promotion':False}
