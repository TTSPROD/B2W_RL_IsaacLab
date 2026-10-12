"""Managed offline forensic analysis of the 9930 continuation, zero PPO/sim steps."""
from __future__ import annotations
import collections
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256, utc_now
from native_trace_analysis import settled_segments, physical_targets, margins, near_event

SOURCE_JOB = '710e7cc2749b496bb8fdc7f51ebb323f'
POLICIES = ('24650', 'stdcontrol_24799', 'stdfocus_24799')


def main():
    managed_entrypoint()
    output = Path(os.environ['B2W_JOB_DIR'])/'trace_diagnosis'
    output.mkdir(exist_ok=False)
    sources = ('scripts/run_native_trace_diagnosis.py', 'scripts/native_trace_analysis.py',
               'tests/test_native_trace_analysis.py', 'scripts/run_support.py', 'scripts/job_manager.py')
    for name in sources:
        p = output/'sources'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_native_trace_analysis.py', '-q'], cwd=ROOT, check=True)
    baseline = ROOT/'logs/dashboard/jobs'/SOURCE_JOB/'native_continuation'
    original = read_json(baseline/'manifest.json')
    for name, digest in original['raw_sha256'].items():
        if sha256(baseline/name) != digest:
            raise ValueError('Original evidence changed: '+name)
    from check_policy_contract import load_contract
    cfg = load_contract()
    default, scales = np.asarray(cfg['default_dof_pos']), np.asarray(cfg['action_scale'])
    inputs, rows, data = {}, [], {}
    unsafe = []
    from summarize_locomotion import validate_terrain
    for policy in POLICIES:
        folder = baseline/'evaluation'/policy
        plan = read_json(folder/'declared_plan.json')
        for terrain in plan['variants']:
            j = validate_terrain(folder, terrain, plan)
            xp = folder/(terrain+'.npz')
            inputs[xp.relative_to(ROOT).as_posix()] = sha256(xp)
            inputs[xp.with_suffix('.json').relative_to(ROOT).as_posix()] = sha256(xp.with_suffix('.json'))
            with np.load(xp) as loaded:
                x = {k: loaded[k].copy() for k in loaded.files}
            data[policy, terrain] = (j, x)
            for entry, record in enumerate(j['records']):
                command = x['commands'][entry, :int(x['lengths'][entry])]
                velocity = x['trace'][:len(command), entry, :3]
                segments = settled_segments(command, velocity)
                for seg in segments:
                    seg.update(policy=policy, terrain=terrain, case=record['case'], seed=record['seed'])
                    rows.append(seg)
                if record['outcome']=='unsafe':
                    joint = int(np.argmin(record['safety']['hard_joint_margin_min_rad']))
                    unsafe.append({'policy': policy, 'terrain': terrain, 'case': record['case'], 'seed': record['seed'],
                                   'joint': joint, 'joint_name': cfg['joint_names'][joint], 'safety': record['safety']})
    phase_groups = {}
    for row in rows:
        if row['case'] not in ('longitudinal', 'lateral', 'yaw') or row['axis'] is None:
            continue
        value = round(row['command'][row['axis']], 2)
        key = '/'.join((row['policy'], row['terrain'], row['case'], str(value)))
        phase_groups.setdefault(key, []).append(row)
    phases = {k: {'n': len(v), 'mean_response_ratio': float(np.mean([r['response_ratio'] for r in v])),
                  'min_response_ratio': float(min(r['response_ratio'] for r in v)),
                  'under_0_8': sum(r['response_ratio'] < .8 for r in v),
                  'rmse_failure': int(sum(np.any(np.asarray(r['rmse']) > [.2, .2, .25]) for r in v))}
              for k, v in phase_groups.items()}
    events = []
    for event in unsafe:
        terrain, case, seed = event['terrain'], event['case'], event['seed']
        matched = {}
        for policy in POLICIES:
            j, x = data[policy, terrain]
            entry = next(i for i, r in enumerate(j['records']) if r['case']==case and r['seed']==seed)
            ranges = np.asarray(j['compiled_model']['hard_joint_ranges'])
            matched[policy] = near_event(x, entry, ranges, default, scales, event['safety']['unsafe_time_s'], event['joint'])
        events.append({**event, 'matched_preceding_2s': matched})
    # Same deterministic evaluator states: reward kernels can be reconstructed
    # at 10Hz, but these are counterfactual nominal diagnostics, not training GAE.
    reward_diagnostics = {}
    for (policy, terrain), (j, x) in data.items():
        ranges = np.asarray(j['compiled_model']['hard_joint_ranges'])
        center, half = ranges.mean(axis=1), np.diff(ranges, axis=1)[:, 0]*.45
        soft = np.stack((center-half, center+half), axis=1)
        for entry, r in enumerate(j['records']):
            if r['case'] not in ('lateral', 'yaw'):
                continue
            q = x['joints_10hz'][:, entry, :12]
            cmd = x['commands'][entry, ::5]
            velocity = x['trace'][::5, entry, :3]
            quat = x['quaternion_wxyz_10hz'][:, entry]
            axis = 1 if r['case']=='lateral' else 2
            mask = (np.isfinite(q).all(axis=1) & np.isfinite(velocity).all(axis=1)
                    & np.isclose(np.abs(cmd[:, axis]), .3))
            gyro_z = 2*(quat[:, 1]**2+quat[:, 2]**2)-1
            factor = np.clip(-gyro_z, 0, .7)/.7
            err = velocity[:, axis]-cmd[:, axis]
            width = .5 if axis==1 else .25
            weight = 3. if axis==1 else 1.5
            squared_error = ((velocity[:, :2]-cmd[:, :2])**2).sum(axis=1) if axis==1 else err**2
            reward = weight*np.exp(-squared_error/width**2)*factor
            posture = -np.linalg.norm(q-default[:12], axis=1)*factor
            soft_cost = -5*np.maximum(soft[:, 0]-q, 0).sum(axis=1)-5*np.maximum(q-soft[:, 1], 0).sum(axis=1)
            values = reward_diagnostics.setdefault(policy+'/'+r['case'], {'tracking': [], 'posture': [], 'soft_limits': [], 'n': 0})
            for key, array in (('tracking', reward), ('posture', posture), ('soft_limits', soft_cost)):
                values[key].extend(array[mask].astype(float).tolist())
            values['n'] += int(mask.sum())
    reward_diagnostics = {k: {**{'n': v['n']}, **{n: float(np.mean(v[n])) for n in ('tracking', 'posture', 'soft_limits')}}
                          for k, v in reward_diagnostics.items()}
    training = {}
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    import torch
    torch.set_num_threads(2)
    parent = torch.load(ROOT/'policies/local/core_24650/model_24650.pt', map_location='cpu', weights_only=True)
    actor_norm = sum(v.double().square().sum().item() for k,v in parent['model_state_dict'].items() if k.startswith('actor.'))**.5
    for arm in ('control', 'focus'):
        receipt = read_json(baseline/arm/'completion.json')
        run = ROOT/receipt['run']
        events_path = next(run.glob('events.out.tfevents.*'))
        inputs[events_path.relative_to(ROOT).as_posix()] = sha256(events_path)
        ea = EventAccumulator(str(events_path), size_guidance={'scalars': 0}).Reload()
        scalars = {key: [{'step': s.step, 'value': s.value} for s in ea.Scalars(key)] for key in ea.Tags()['scalars']}
        write_json(output/(arm+'_training_scalars.json'), scalars)
        drift = []
        for cp in sorted(run.glob('model_*.pt')):
            inputs[cp.relative_to(ROOT).as_posix()] = sha256(cp)
            c = torch.load(cp, map_location='cpu', weights_only=True)
            norm = sum((v.double()-parent['model_state_dict'][k].double()).square().sum().item()
                       for k,v in c['model_state_dict'].items() if k.startswith('actor.'))**.5
            drift.append({'iteration': c['iter'], 'actual_updates': c['iter']-24650+1,
                          'actor_relative_l2': norm/actor_norm, 'std_mean': float(c['model_state_dict']['std'].mean())})
        training[arm] = {'safety': read_json(baseline/arm/'train/training_safety.json'), 'weight_drift': drift,
                         'scalar_tags': list(scalars), 'scalar_first_last': {k:[v[0],v[-1]] for k,v in scalars.items() if v}}
    stalls = []
    terrain, case, seed = 'stairs_down_06', 'stop_restart_0.5', 73005
    for policy in POLICIES:
        j,x = data[policy, terrain]
        entry = next(i for i,r in enumerate(j['records']) if r['case']==case and r['seed']==seed)
        qdq = x['joints_10hz'][:, entry]
        target = physical_targets(x['raw_actions_10hz'][:, entry], default, scales)
        ts = np.arange(len(qdq))*.1+.02
        ids = np.flatnonzero(np.isfinite(qdq).all(axis=1) & (np.abs(qdq[:, 32+12])>=19.))
        stalls.append({'policy': policy, 'record': j['records'][entry], 'saturated_times_s': ts[ids].tolist(),
                       'FR_wheel_target_rad_s': target[ids,12].tolist(), 'FR_wheel_dq_rad_s': qdq[ids,16+12].tolist(),
                       'FR_wheel_tau_est_nm': qdq[ids,32+12].tolist(),
                       'FR_wheel_upforce_n': x['wheels_xyz_upforce_50hz'][ids*5,entry,0,3].tolist(),
                       'command': x['commands'][entry,ids*5].tolist(), 'velocity_body':x['trace'][ids*5,entry,:3].tolist()})
    write_json(output/'analysis.json', {'source_job':SOURCE_JOB, 'phase_groups':phases, 'unsafe_events':events,
               'training':training, 'reward_diagnostics':reward_diagnostics, 'wheel_stall':stalls,
               'limits_unchanged':True, 'ppo_updates':0, 'simulation_steps':0,
               'limitations':['q/dq/torque/action traces10Hz omit exact first unsafe tick; 200Hz safety summaries authoritative',
                              'No full57 observations/raw previous actions50Hz or stored PPO rollout/GAE; exact counterfactual actor-gradient attribution unavailable',
                              'Reconstructed reward kernels are nominal evaluator diagnostics, not measured training returns']})
    write_json(output/'phase_rows.json', rows)
    plot(output, data, events, phases)
    for name, digest in inputs.items():
        if sha256(ROOT/name) != digest:
            raise ValueError('Evidence changed while analyzing: '+name)
    write_json(output/'manifest.json', {'created_utc':utc_now(),'source_sha256':{n:sha256(ROOT/n) for n in sources},
               'input_sha256':inputs,'ppo_updates':0,'simulation_steps':0,'hardware_enabled':False,
               'raw_sha256':{p.relative_to(output).as_posix():sha256(p) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json'}})
    print('TRACE_DIAGNOSIS_COMPLETE', len(rows),'phases',len(events),'unsafe events',flush=True)


def plot(output, data, events, phases):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = ['#485666','#3478c8','#d36b32']
    fig, axes = plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
    for ax,event in zip(axes,events):
        for policy,color in zip(POLICIES,colors):
            values = event['matched_preceding_2s'][policy]
            ax.plot(values['time_after_step_s'],values['q'],label=policy,color=color)
        j,_ = data['24650',event['terrain']]
        limits = j['compiled_model']['hard_joint_ranges'][event['joint']]
        # Culprit boundary is whichever is nearest the last logged actual pose.
        finalq = event['matched_preceding_2s'][event['policy']]['q'][-1]
        boundary = min(limits,key=lambda q:abs(q-finalq))
        ax.axhline(boundary,color='black',ls='--',label='mechanical bound')
        ax.axvline(event['safety']['unsafe_time_s'],color='red',ls=':',label='200 Hz first violation')
        ax.set(title=event['policy']+' '+event['case']+' seed'+str(event['seed']),xlabel='Time after physics step, s',ylabel=event['joint_name']+', rad')
        ax.legend(fontsize=7)
    fig.savefig(output/'unsafe_preceding.png',dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
    labels=[.3,.7,1.,-1.,-.7,-.3]
    for ax,case in zip(axes,('lateral','yaw')):
        for policy,color in zip(POLICIES,colors):
            vals=[phases['/'.join((policy,'flat_mu_100',case,str(m)))]['mean_response_ratio'] for m in labels]
            ax.plot(range(6),vals,'o-',label=policy,color=color)
        ax.axhline(.8,color='black',ls='--',label='response gate 0.8')
        ax.set_xticks(range(6),[str(x) for x in labels]);ax.set(title='flat_mu_100 '+case,xlabel='Command (m/s or rad/s)',ylabel='Mean measured / commanded')
        ax.legend(fontsize=7)
    fig.savefig(output/'axis_phases.png',dpi=160)
    plt.close(fig)


if __name__=='__main__':
    main()
