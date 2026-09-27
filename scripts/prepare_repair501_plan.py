"""Freeze a 501-update repair plan from the completed 24499 development screen."""
import hashlib
import json
from pathlib import Path

from operating57_protocol import cases_for as flat_cases
from fullcycle_eval_protocol import cases_for as terrain_cases

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'configs/24499_repair501_20260927.json'


def main():
    report = ROOT/'docs/results/2026-09-27-fullcycle-24499-vs-23999.md'
    summary = ROOT/'docs/results/evidence/fullcycle_24499_20260927/summary.json'
    data = json.loads(summary.read_text())
    targets, weights = [], {'nonstairs': {}, 'stairs': {}}
    for row in data['rows']:
        values = row['policies']; current = values['24499']
        full_loss = max(0, max(values[p]['success'] for p in ('21999','23999')) - current['success'])
        zero_loss = max(0, max(values[p]['complete_zero_segments_pass'] for p in ('21999','23999')) - current['complete_zero_segments_pass'])
        exposure_loss = max(0, max(values[p]['exposed_zero_success'] for p in ('21999','23999')) - current['exposed_zero_success'])
        severity = 4*full_loss/32 + 2*min(32,zero_loss+exposure_loss)/32 + 3*bool(current['unsafe'])
        weight = min(8., 1. + .5*(32-current['success'])/32 + severity)
        bank = 'stairs' if row['terrain'].startswith('stairs_') else 'nonstairs'
        weights[bank][row['case']] = max(weights[bank].get(row['case'],1.),weight)
        if full_loss or zero_loss or exposure_loss or current['unsafe']:
            targets.append({'terrain':row['terrain'],'case':row['case'],'full_24499':current['success'],
                'full_loss_to_best_reference':full_loss,'zero_loss':zero_loss,'exposure_loss':exposure_loss,
                'unsafe':current['unsafe'],'weight':weight})
    banks = {}
    for name,cases in (('nonstairs',flat_cases()),('stairs',terrain_cases('stairs_up_06'))):
        entries = []
        for case in cases:
            segments = []
            for segment in case.segments:
                x,y,z = segment.command
                mode = 0 if not any(segment.command) else 1 if not (x or y) else 2 if not (y or z) else 3 if not (x or z) else 4 if not z else 6 if not y else 5
                seconds = 2. if segment.kind == 'initialization' else max(14.,segment.seconds) if mode == 0 else segment.seconds
                segments.append({'command':list(segment.command),'seconds':seconds,'mode':mode})
            if case.name == 'stand':
                segments.insert(0,{'command':[0.,0.,0.],'seconds':2.,'mode':0})
            assert sum(s['seconds'] for s in segments) <= 60
            entries.append({'case':case.name,'weight':weights[name][case.name],'segments':segments})
        banks[name] = entries
    plan = {'parent_iteration':24499,'additional_updates':501,'final_iteration':25000,'seed':9705,
        'num_envs':4096,'lr_cap':5e-6,'basis_report':report.relative_to(ROOT).as_posix(),
        'basis_report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),
        'basis_summary':summary.relative_to(ROOT).as_posix(),
        'basis_summary_sha256':hashlib.sha256(summary.read_bytes()).hexdigest(),
        'cohorts':{'original_vendor':'50% on each terrain','nonstairs':'25% parent recovery + 25% complete bank',
                   'stairs':'50% complete stair bank; all direct stair envs'},
        'bank_coverage':'36 nonstair and 9 stair schedules, including previously successful cases',
        'weight_formula':'min(8,1+0.5*(32-current_full)/32+4*full_loss/32+2*min(32,zero_loss+exposure_loss)/32+3*has_unsafe); max across geometries',
        'reward_changes':{'zero_kernel':'50% original + 50% std=0.15, only exactly zero body command; max weights unchanged',
                          'joint_pos_limits_weight':[-5.,-7.5]},
        'target_rows':targets,'banks':banks,'qualification':False}
    if OUTPUT.exists():
        raise FileExistsError('Plan already exists; do not replace a declared run')
    OUTPUT.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'sha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),'targets':len(targets),
                      'banks':{k:len(v) for k,v in banks.items()}},indent=2))


if __name__ == '__main__': main()
