"""Frozen decision for stair curriculum; never promotes a policy automatically."""
import statistics
import math
from collections import defaultdict
import locomotion_v2_curriculum_protocol as protocol


def coverage_ok(value,plan):
    for name,cases in plan['banks'].items():
        group=value.get(name,{})
        attempts=group.get('segment_attempts',[])
        complete=group.get('segment_completions',[])
        from b2w_core_stage3_sampling import build_banks
        expanded=build_banks(plan)[name]
        for c,case in enumerate(expanded):
            for p in range(len(case['segments'])):
                if (c>=len(attempts) or c>=len(complete) or p>=len(attempts[c]) or p>=len(complete[c])
                        or attempts[c][p]<plan['coverage']['attempts_per_phase_min']
                        or complete[c][p]<plan['coverage']['completed_segments_per_phase_min']):return False
        if name.startswith('stairs'):
            levels=group.get('level_attempts',[])
            if len(levels)!=10 or levels[9]<plan['coverage']['highest_level_stair_attempts_min']:return False
    return True


def decide(records,plan,coverage):
    policies=['24650']+[f'{arm}_{24650+step}' for arm in plan['arms'] for step in plan['probe_updates']]
    expected={(p,t,c.name,s) for p in policies for t in protocol.TERRAINS
              for c in protocol.cases_for(t) for s in plan['evaluation']['reset_seeds']}
    keys=[(str(r['policy']),r['terrain'],r['case'],r['seed']) for r in records]
    if len(keys)!=len(expected) or set(keys)!=expected:raise ValueError('Incomplete or duplicate probe matrix')
    metrics={}
    for p in policies:
        rows=[r for r in records if str(r['policy'])==p];cells=defaultdict(int)
        for r in rows:cells[f'{r["terrain"]}/{r["case"]}']+=int(r['covered_scenario_success'])
        targets={}
        for case,axis,key in (('lateral',1,'linear_response_ratio'),('yaw',2,'angular_response_ratio')):
            values=[s[key] for r in rows if r['case']==case for s in r['segments']
                    if abs(abs(s['command'][axis])-.3)<1e-6 and key in s]
            targets[case]=statistics.mean(values) if len(values)==20 and all(map(math.isfinite,values)) else None
        metrics[p]={'cells':dict(cells),'targets':targets,'success':sum(cells.values()),
            'unsafe':sum(bool(r['safety']['unsafe_flags']) for r in rows),
            'wheel_saturation':max(max(r['safety']['torque_saturation_fraction'][12:]) for r in rows),
            'leg_saturation':max(max(r['safety']['torque_saturation_fraction'][:12]) for r in rows)}
    covered={a:coverage_ok(coverage.get(a,{}),plan) for a in plan['arms']}
    decisions={};base=metrics['24650'];rules=plan['advancement']
    for step in plan['probe_updates']:
        p=f'stairadaptive_{24650+step}';candidate=metrics[p];control=metrics[f'stairfixed_{24650+step}'];reasons=[]
        if step not in rules['eligible_updates']:reasons.append('diagnostic checkpoint only')
        if not all(covered.values()):reasons.append('incomplete phase/level coverage')
        if candidate['unsafe']:reasons.append('unsafe')
        for cell,value in candidate['cells'].items():
            if value<max(base['cells'][cell],control['cells'][cell]):reasons.append(cell+': regression')
        for ref_name,ref in [('parent',base),('control',control)]:
            gain=sum(v-ref['cells'][k] for k,v in candidate['cells'].items() if k.startswith('stairs_up'))
            if gain<rules['ascent_success_gain']:reasons.append('insufficient ascent gain vs '+ref_name)
            for axis in rules['targets']:
                c,r=candidate['targets'][axis],ref['targets'][axis]
                if c is None or r is None or c<r-rules['target_retention_tolerance']:reasons.append(axis+': retention failure vs '+ref_name)
        for group in ('wheel','leg'):
            if candidate[group+'_saturation']>base[group+'_saturation']+rules[group+'_saturation_fraction_extra_max']:reasons.append(group+': saturation regression')
        decisions[p]={'advance':not reasons,'reasons':reasons,'updates':step}
    selected=next((p for p,d in decisions.items() if d['advance']),None)
    return {'metrics':metrics,'decisions':decisions,'coverage_ok':covered,'selected':selected,
            'qualification':False,'hardware_approval':False,'automatic_promotion':False}
