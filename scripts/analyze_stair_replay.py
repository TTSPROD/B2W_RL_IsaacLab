"""Pair all stair replay records by actor/case/reset, including failures."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
from run_support import ROOT, read_json, write_json, sha256
from summarize_locomotion import validate_terrain


def record_key(record):
    return str(record['policy']), record['case'], record['seed']


def compare_records(before, after):
    old = {record_key(r): r for r in before}
    new = {record_key(r): r for r in after}
    if len(old) != len(before) or len(new) != len(after) or old.keys() != new.keys():
        raise ValueError('Missing, duplicate or foreign paired record')
    return [{'policy': p, 'case': c, 'seed': s,
             'success_before': old[p,c,s]['covered_scenario_success'],
             'success_after': new[p,c,s]['covered_scenario_success'],
             'flags_before': old[p,c,s]['failure_flags'],
             'flags_after': new[p,c,s]['failure_flags']}
            for p,c,s in old if (old[p,c,s]['covered_scenario_success'], old[p,c,s]['failure_flags']) !=
                                (new[p,c,s]['covered_scenario_success'], new[p,c,s]['failure_flags'])]


def analyze(folders):
    datasets, hashes, result = {}, {}, {'diagnostic_only': True, 'qualification': False,
                                      'candidate': '24650', 'runs': {}, 'comparisons': {}}
    for label, base in folders.items():
        plan = read_json(base / 'declared_plan.json')
        for relative in ('declared_plan.json', 'policy_map.json'):
            path = base / relative
            hashes[path.relative_to(ROOT).as_posix()] = sha256(path)
        datasets[label] = {}
        report = {'policies': {}, 'unsafe': []}
        for terrain in ('stairs_up_18', 'stairs_down_18'):
            data = validate_terrain(base, terrain, plan)
            datasets[label][terrain] = data
            for suffix in ('.json', '.npz'):
                path = base / (terrain + suffix)
                hashes[path.relative_to(ROOT).as_posix()] = sha256(path)
            for p in map(str, plan['policies']):
                records = [r for r in data['records'] if str(r['policy']) == p]
                report['policies'].setdefault(p, {})[terrain] = {
                    'success': sum(r['covered_scenario_success'] for r in records),
                    'episodes': len(records),
                    'unsafe': sum(bool(r['safety']['unsafe_flags']) for r in records),
                    'flags': dict(Counter(flag for r in records for flag in r['failure_flags']))}
            for r in data['records']:
                if r['safety']['unsafe_flags']:
                    margins = r['safety']['hard_joint_margin_min_rad']
                    j = int(np.argmin(margins))
                    report['unsafe'].append({'terrain': terrain, 'policy': r['policy'],
                        'case': r['case'], 'seed': r['seed'], 'flags': r['safety']['unsafe_flags'],
                        'time_s': r['safety']['unsafe_time_s'], 'minimum_margin_rad': margins[j],
                        'joint': data['compiled_model']['joint_names'][j]})
        result['runs'][label] = report
    for label in ('same', 'reverse'):
        report = {}
        for terrain in ('stairs_up_18', 'stairs_down_18'):
            a, b = datasets['original'][terrain], datasets[label][terrain]
            if a['compiled_model'] != b['compiled_model'] or a['runtime'] != b['runtime']:
                raise ValueError('Runtime/compiled model changed')
            if a['policy_exports'] != b['policy_exports']:
                raise ValueError('Actor bytes/paths changed')
            changes = compare_records(a['records'], b['records'])
            old_ids = {record_key(r): i for i,r in enumerate(a['records'])}
            trace_stats = []
            with np.load(folders['original'] / (terrain + '.npz')) as old, np.load(folders[label] / (terrain + '.npz')) as new:
                exact_arrays = (all(np.array_equal(old[k], new[k], equal_nan=True) for k in old.files)
                                if a['protocol']['policies'] == b['protocol']['policies'] else None)
                x, y = old['trace'], new['trace']
                for j,r in enumerate(b['records']):
                    i = old_ids[record_key(r)]
                    left, right = x[:,i], y[:,j]
                    common = np.isfinite(left).all(axis=1) & np.isfinite(right).all(axis=1)
                    difference = np.abs(left[common].astype(float) - right[common].astype(float))
                    different = np.flatnonzero((difference > 1e-6).any(axis=1))
                    trace_stats.append({'policy': str(r['policy']), 'case': r['case'], 'seed': r['seed'],
                        'common_steps': int(common.sum()),
                        'max_abs_vxy_wz_xyz': difference.max(axis=0).tolist() if len(difference) else None,
                        'first_difference_over_1e_minus6_s': float((np.flatnonzero(common)[different[0]]+1)*.02) if len(different) else None})
            report[terrain] = {'paired_records': len(b['records']), 'changed_outcomes': changes,
                'all_arrays_exact_equal_same_order': exact_arrays,
                'success_flips': sum(c['success_before'] != c['success_after'] for c in changes),
                'trajectory_comparison': trace_stats}
        result['comparisons'][label] = report
    result['input_sha256'] = hashes
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ('original', 'same', 'reverse'):
        parser.add_argument('--'+label, type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    write_json(args.output, analyze({label: getattr(args,label).resolve() for label in ('original','same','reverse')}))


if __name__ == '__main__':
    main()
