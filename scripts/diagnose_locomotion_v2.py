"""Read-only trace analysis; reward reconstructions are diagnostics, not causal evidence."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import numpy as np
import yaml

from run_support import ROOT, read_json, write_json, sha256
from summarize_locomotion import validate_terrain

DEFAULT_BASE = ROOT / 'logs/dashboard/jobs/6d5e7918ea824e8893e752976b5b65a0/evaluation'


def analyze(base, output):
    plan = read_json(base / 'declared_plan.json')
    parent = ROOT / 'policies/local/core_24650'
    cfg = yaml.load((parent / 'env.yaml').read_text(), Loader=yaml.BaseLoader)
    contract = read_json(parent / 'export/manifest.json')['contract']
    default = np.array(contract['default_dof_pos'])
    limits = np.array(contract['torque_limits'])
    grouped, stairs, inputs = defaultdict(list), [], {}
    for terrain in plan['variants']:
        data = validate_terrain(base, terrain, plan)
        for suffix in ('.json', '.npz'):
            path = base / (terrain + suffix)
            inputs[path.relative_to(ROOT).as_posix()] = sha256(path)
        with np.load(base / (terrain + '.npz')) as trace:
            for index, record in enumerate(data['records']):
                if str(record['policy']) != '24650':
                    continue
                if record['terrain_exposure'] is not None:
                    stairs.append({key: record[key] for key in ('terrain', 'case', 'seed', 'outcome', 'terrain_exposure')})
                    continue
                case = next(c for c in plan['variants'][terrain]['cases'] if c['name'] == record['case'])
                starts = np.cumsum([0] + [round(s['seconds'] / .02) for s in case['segments']])
                for segment in record['segments']:
                    command = np.array(segment['command'])
                    if not np.any(command):
                        continue
                    number = segment['segment']
                    begin, end = int(starts[number] + 100), int(starts[number + 1])
                    v = trace['trace'][begin:end, index, :3]
                    ticks = np.arange((begin + 4)//5, (end + 4)//5)
                    j = trace['joints_10hz'][ticks, index]
                    q, dq, tau = j[:, :16], j[:, 16:32], j[:, 32:]
                    quat = trace['quaternion_wxyz_10hz'][ticks, index]
                    upright = np.clip(1 - 2*(quat[:, 1]**2 + quat[:, 2]**2), 0, .7)/.7
                    pose = np.linalg.norm(q[:, :12] - default[:12], axis=1)*upright
                    sampled_v = trace['trace'][ticks*5, index, :3]
                    lin = 3*np.exp(-np.sum((sampled_v[:, :2]-command[:2])**2, axis=1)/.5**2)*upright
                    width = .25 if .2 <= abs(command[2]) <= .6 else .5
                    yaw = 1.5*np.exp(-(sampled_v[:, 2]-command[2])**2/width**2)*upright
                    active = np.flatnonzero(command)
                    axis = int(active[0]) if len(active)==1 else None
                    row = {'seed': record['seed'], 'command': command.tolist(),
                        'mean_velocity': segment['mean_velocity'], 'rmse': segment['rmse'],
                        'response_ratio': segment.get('angular_response_ratio' if axis==2 else 'linear_response_ratio'),
                        'response_time_s': segment.get('response_time_s'),
                        'late_minus_early_velocity': (v[-50:].mean(0)-v[:50].mean(0)).tolist(),
                        'wheel_saturation_sample_fraction': float(np.mean(np.abs(tau[:,12:]) >= .99*limits[12:])),
                        'leg_saturation_sample_fraction': float(np.mean(np.abs(tau[:,:12]) >= .99*limits[:12])),
                        'reward_density_10hz': {'joint_pos_penalty': -float(pose.mean()),
                            'leg_power': -1e-5*float(np.abs(dq[:,:12]*tau[:,:12]).sum(1).mean()),
                            'leg_torque': -1e-5*float((tau[:,:12]**2).sum(1).mean()),
                            'lin_tracking_loss_to_perfect': float((3*upright-lin).mean()),
                            'yaw_tracking_loss_to_perfect': float((1.5*upright-yaw).mean())}}
                    grouped[(terrain, record['case'], tuple(command))].append(row)
    rows=[]
    for (terrain, case, command), samples in grouped.items():
        rows.append({'terrain':terrain,'case':case,'command':command,'trials':samples,
            'mean_response_ratio':float(np.mean([s['response_ratio'] for s in samples if s['response_ratio'] is not None])),
            'mean_rmse':np.mean([s['rmse'] for s in samples],axis=0).tolist(),
            'mean_late_minus_early_velocity':np.mean([s['late_minus_early_velocity'] for s in samples],axis=0).tolist(),
            'wheel_saturation_sample_fraction':float(np.mean([s['wheel_saturation_sample_fraction'] for s in samples])),
            'reward_density_10hz':{k:float(np.mean([s['reward_density_10hz'][k] for s in samples]))
                                  for k in samples[0]['reward_density_10hz']}})
    result={'schema':'b2w_trace_diagnosis_v1','policy':'24650','rows':rows,'stairs':stairs,
        'input_sha256':inputs,'parent_env_sha256':sha256(parent/'env.yaml'),
        'analysis_source_sha256':sha256(Path(__file__)),
        'mass_kg':float(sum(data['compiled_model']['mass_kg'])),
        'reward_weights':{k:float(v['weight']) for k,v in cfg['rewards'].items() if isinstance(v,dict)},
        'limitations':['10 Hz reconstruction of selected state-based reward terms; not the full 50 Hz training reward',
            'Reward values along one policy do not establish gradients or causality',
            'Implicit wheel torque is simulator telemetry, not current measurement',
            'Steady analysis uses existing post-2s windows; raw bytes are unchanged']}
    write_json(output, result)
    for row in rows:
        if row['case'] in ('yaw','lateral') and max(map(abs,row['command'])) == .3:
            print(row['terrain'], row['case'], row['command'],
                  'ratio',round(row['mean_response_ratio'],3),
                  'wheel_sat',round(row['wheel_saturation_sample_fraction'],4),
                  'reward', {k:round(v,3) for k,v in row['reward_density_10hz'].items()}, flush=True)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=DEFAULT_BASE)
    parser.add_argument('--output',type=Path,default=ROOT/'logs/diagnostics/24650_v2_20260930.json')
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    analyze(args.base,args.output)
