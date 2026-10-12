"""Frozen decision for DeepSeek F1; never promotes a policy automatically."""
import statistics
import math
from collections import defaultdict
import locomotion_v2_curriculum_protocol as protocol
from stair_curriculum_decision import coverage_ok


def decide(records, plan, coverage):
    policies = ['24650'] + [f'{arm}_{24650+step}' for arm in plan['arms'] for step in plan['probe_updates']]
    expected = {(p, t, c.name, s) for p in policies for t in protocol.TERRAINS
                for c in protocol.cases_for(t) for s in plan['evaluation']['reset_seeds']}
    keys = [(str(r['policy']), r['terrain'], r['case'], r['seed']) for r in records]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError('Incomplete or duplicate probe matrix')
    metrics = {}
    for p in policies:
        rows = [r for r in records if str(r['policy']) == p]; cells = defaultdict(int)
        for r in rows: cells[f'{r["terrain"]}/{r["case"]}'] += int(r['covered_scenario_success'])
        targets = {}
        for case, axis, key in (('lateral', 1, 'linear_response_ratio'), ('yaw', 2, 'angular_response_ratio')):
            values = [s[key] for r in rows if r['case'] == case for s in r['segments']
                      if abs(abs(s['command'][axis]) - .3) < 1e-6 and key in s]
            targets[case] = statistics.mean(values) if len(values) == 20 and all(map(math.isfinite, values)) else None
        metrics[p] = {'cells': dict(cells), 'targets': targets, 'success': sum(cells.values()),
            'unsafe': sum(bool(r['safety']['unsafe_flags']) for r in rows),
            'wheel_saturation': max(max(r['safety']['torque_saturation_fraction'][12:]) for r in rows),
            'leg_saturation': max(max(r['safety']['torque_saturation_fraction'][:12]) for r in rows)}
    covered = {a: coverage_ok(coverage.get(a, {}), plan) for a in plan['arms']}
    base = metrics['24650']; rules = plan['advancement']
    decisions = {}
    for arm in plan['arms']:
        for step in plan['probe_updates']:
            p = f'{arm}_{24650+step}'; candidate = metrics[p]; reasons = []
            if step not in rules['eligible_updates']: reasons.append('diagnostic checkpoint only')
            if not covered[arm]: reasons.append('incomplete phase/level coverage')
            if candidate['unsafe']: reasons.append('unsafe')
            for cell, value in candidate['cells'].items():
                if value < base['cells'][cell]: reasons.append(cell + ': regression vs parent')
            gain = sum(v - base['cells'][k] for k, v in candidate['cells'].items() if k.startswith('stairs_up'))
            if gain < rules['ascent_success_gain']: reasons.append('insufficient ascent gain vs parent')
            for axis in rules['targets']:
                c, r = candidate['targets'][axis], base['targets'][axis]
                if c is None or r is None or c < r - rules['target_retention_tolerance']:
                    reasons.append(axis + ': retention failure vs parent')
            for group in ('wheel', 'leg'):
                if candidate[group+'_saturation'] > base[group+'_saturation'] + rules[group+'_saturation_fraction_extra_max']:
                    reasons.append(group + ': saturation regression')
            decisions[p] = {'advance': not reasons, 'reasons': reasons, 'updates': step}
    selected = next((p for p, d in decisions.items() if d['advance']), None)
    return {'metrics': metrics, 'decisions': decisions, 'coverage_ok': covered, 'selected': selected,
            'qualification': False, 'hardware_approval': False, 'automatic_promotion': False}
