"""Auditable replay evidence; short diagnostics do not receive acceptance scores."""
import json
import numpy as np
from replay57_protocol import ROOT, BASE, CONFIG, SEEDS, DT, PHYSICS_DT, reward_terms
from physics57_protocol import save_json, sha256

OUT = ROOT/'docs/results/evidence/replay57_19999_20260925'
CONDITIONS = ('mujoco_cooked_shapes','mujoco_source_shapes','isaac_contactmesh')


def summarize():
    capture = np.load(BASE/'capture.npz')
    captured = json.loads((BASE/'capture.json').read_text())
    warm = json.loads((BASE/'warm_check.json').read_text())
    assert captured['max_abs_original_trace_error'] == warm['max_abs_source_continuation_error'] == 0.
    rows = []
    for name in CONDITIONS:
        a = np.load(BASE/f'{name}.npz')
        meta = json.loads((BASE/f'{name}.json').read_text())
        if name.startswith('isaac'):
            rates,names = a['reward_rates'],meta['reward_names']
        else:
            rates = np.load(BASE/f'{name}_ledger.npz')['reward_rates']
            names = json.loads((BASE/f'{name}_ledger.json').read_text())['reward_names']
        assert a['q'].shape == (250,4,16) and rates.shape == (250,4,17)
        assert np.isfinite(rates).all() and np.isfinite(a['trace']).all()
        for i,seed in enumerate(SEEDS):
            v = a['root_velocity_b'][:,i]
            contact = a['physics_contact'][:,i]
            tau = a['physics_tau'][:,i]
            req = a['physics_requested_tau'][:,i]
            rates_i = rates[:,i]
            load = contact[...,0].sum(axis=0)
            assert np.min(load)>0
            rows.append({'condition':name,'seed':seed,'source_state':'stall' if seed in (7201,7203) else 'moving_control',
                'mean_body_velocity':v.mean(axis=0).tolist(),
                'tracking_rmse_vx_vy_wz':np.sqrt(np.mean((v[:,[0,1,5]]-[.3,0,0])**2,axis=0)).tolist(),
                'diagnostic_dx_m':float(a['root_pose'][-1,i,0]-capture['root_pose'][i,0]),
                'last_second_vx_m_s':float(v[-50:,0].mean()),
                'wheel_slip_rms_m_s':np.sqrt(contact[...,1].sum(axis=0)/load).tolist(),
                'wheel_mean_loaded_normal_force_n':contact[...,0].mean(axis=0).tolist(),
                'wheel_saturation_fraction':np.mean(np.abs(tau[:,12:])>=19.8,axis=0).tolist(),
                'wheel_requested_peak_nm':np.abs(req[:,12:]).max(axis=0).tolist(),
                'wheel_applied_peak_nm':np.abs(tau[:,12:]).max(axis=0).tolist(),
                'leg_requested_peak_nm':np.abs(req[:,:12]).max(axis=0).tolist(),
                'leg_applied_peak_nm':np.abs(tau[:,:12]).max(axis=0).tolist(),
                'reward_rate_mean':dict(zip(names,rates_i.mean(axis=0).astype(float))),
                'reward_integral':dict(zip(names,(rates_i.sum(axis=0)*DT).astype(float))),
                'total_reward_rate_mean':float(rates_i.sum(axis=1).mean()),
                'total_reward_rate_after_100ms':float(rates_i[5:].sum(axis=1).mean()),
                'safety':meta['safety'][i]})
    isaac = json.loads((BASE/'isaac_contactmesh.json').read_text())
    original = np.load(BASE/'isaac_nominal.npz')
    repaired = np.load(BASE/'isaac_contactmesh.npz')
    repair_error = float(np.max(np.abs(original['trace']-repaired['trace'])))
    assert repair_error == 0. and max(isaac['reward_proxy_max_errors'].values())<2e-5
    inputs = sorted(BASE.glob('*.json'))+sorted(BASE.glob('*.npz'))
    sources = {p.name:sha256(p) for p in sorted((ROOT/'scripts').glob('replay57_*.py'))}
    # Keep the exact loader revision used by the initial MuJoCo runs.
    protocol = (ROOT/'scripts/replay57_protocol.py').read_bytes()
    prior = protocol.replace(b"ConfigLoader.add_constructor('tag:yaml.org,2002:python/tuple',\n    lambda loader, node: tuple(loader.construct_sequence(node)))\n",b'')
    import hashlib
    assert hashlib.sha256(prior).hexdigest() == captured['sources']['replay57_protocol.py']
    OUT.mkdir(parents=True,exist_ok=True)
    prior_file = OUT/'replay57_protocol_initial.py.txt'
    if prior_file.exists():
        assert prior_file.read_bytes() == prior
    else:
        prior_file.write_bytes(prior)
    # Every historical source hash must match current source or this recorded loader revision.
    known = set(sources.values())|{sha256(prior_file)}
    for p in BASE.glob('*.json'):
        item = json.loads(p.read_text())
        assert item['config_sha256']==sha256(CONFIG)
        assert sha256(ROOT/item['trace_path'])==item['trace_sha256']
        assert set(item['sources'].values()) <= known,(p,set(item['sources'].values())-known)
    save_json(OUT/'summary.json',{'schema':'replay57_19999_summary_v1','policy':19999,
        'accepted':False,'config_sha256':sha256(CONFIG),'seeds':SEEDS,
        'counts':{'source_captures':4,'valid_fresh_replays':12,'exact_continuation_checks':4,
                  'incomplete_isaac_full_replays':4,'aborted_contact_report_probe_batches':2,
                  'aborted_probe_envs':4,'aborted_probe_seconds':.12,'pre_rollout_yaml_failure':1},
        'recapture_max_abs_error':0.,'warm_continuation_max_abs_error':0.,
        'instrumentation_repair_trace_max_abs_error':repair_error,
        'isaac_initial_state_errors':isaac['initial_state_errors'],
        'reward_proxy_max_errors':isaac['reward_proxy_max_errors'],
        'maximum_contacts_per_wheel_pair':isaac['maximum_contacts_per_wheel_pair'],
        'reward_source_terms':reward_terms_serializable(),
        'rows':rows,'inputs':{str(p.relative_to(ROOT)):sha256(p) for p in inputs},
        'sources':sources,'initial_loader_revision':{'path':str(prior_file.relative_to(ROOT)),'sha256':sha256(prior_file)},
        'limitations':['four selected states, not independent qualification episodes',
            'fresh solver contacts; original warmstart available only for same-engine check',
            'MuJoCo post-step contact velocity has a 2 ms kinematic/velocity staging difference',
            'Isaac wheel applied torque is implicit PD estimate, MuJoCo is solver actuator force',
            'saved reward functions on diagnostic physics/command traces, not complete original training returns',
            'moving states and stalled states have different terrain/body poses; reward comparisons are not causal rescue rollouts'],
        'decision':'Prepare one recovery-reset-mixture PPO A/B; preserve all rewards and actuator limits. No PPO executed.'})


def reward_terms_serializable():
    def clean(v):
        if isinstance(v,slice):
            return {'slice':[v.start,v.stop,v.step]}
        if isinstance(v,dict):
            return {k:clean(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):
            return [clean(x) for x in v]
        return v
    return clean(reward_terms())


if __name__ == '__main__':
    summarize()
