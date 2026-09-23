"""Artifact checks and frozen source list shared by Rough preflight and R1."""
from pathlib import Path
from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import sha256,validate_checkpoints,validate_tensorboard
from run_rough_r0 import read

ANCHOR=ROOT/'logs/qualification/flat_reference_qualification_20260919_resume1/seed54/export/policy-contract-export/policy.pt'
SOURCES=('train_b2w_desktop.py','b2w_runtime.py','b2w_rough_runtime.py','b2w_rough_terrain.py','rough_curriculum.py','rough_tilt_termination.py',
         'reference_transfer.py','b2w_yaw_commands.py','yaw_command_sampling.py','b2w_height_rewards.py',
         'rough_evaluation.py','rough_metrics.py','replay_rough_b2w.py','physical_evaluation.py',
         'replay_reference_b2w.py','flat_evaluation.py','check_stand_b2w.py','smoke_b2w_desktop.py','benchmark_b2w.py',
         'run_rough_r0.py','rough_training_protocol.py')


def verify_run(label,count,start,updates,seed,frozen):
    import torch
    matches=list((ROOT/'logs/rsl_rl/unitree_b2w_rough').glob('*_'+label+'/manifest.json'))
    if len(matches)!=1:raise ValueError('Expected one Rough training manifest')
    path=matches[0];m=read(path)
    if (m['status']!='completed' or m['seed']!=seed or m['num_envs']!=count
            or m['starting_runner_iteration']!=start or m['ending_runner_iteration']!=start+updates-1
            or not m['rough_transfer'] or m['validated_contract']['critic_observations']!=247):
        raise ValueError('Registered Rough workload did not complete')
    checkpoint=path.parent/f'model_{start+updates-1}.pt'
    saved=torch.load(checkpoint,map_location='cpu',weights_only=True);state=saved['model_state_dict']
    actor=torch.jit.load(str(ANCHOR),map_location='cpu').actor.state_dict()
    equal=all(torch.equal(state['actor.'+k],v) for k,v in actor.items())
    if equal!=frozen or not torch.equal(state['std'],torch.full_like(state['std'],.1)):
        raise ValueError('Actor calibration/exploration contract failed')
    if state['critic.0.weight'].shape[1]!=247 or not saved['infos'].get('rough_curriculum'):
        raise ValueError('Critic or curriculum checkpoint state missing')
    if not saved['optimizer_state_dict']['state']:raise ValueError('Empty optimizer')
    before=ROOT/m['resume']['path'] if m['resume'] else path.parent/'model_0.pt'
    initial=torch.load(before,map_location='cpu',weights_only=True)
    if not any(not torch.equal(state[k],initial['model_state_dict'][k]) for k in state if k.startswith('critic.')):
        raise ValueError('Critic did not change')
    steps=[float(v['step']) for v in saved['optimizer_state_dict']['state'].values() if 'step' in v]
    if m['resume']:
        old=[float(v['step']) for v in initial['optimizer_state_dict']['state'].values() if 'step' in v]
        if max(steps)<=max(old):raise ValueError('Optimizer restart lost its accumulated state')
    if m['export_parity']['max_abs_error']>1e-5:raise ValueError('Export parity failed')
    return dict(seed=seed,training_manifest=str(path.relative_to(ROOT)),checkpoint=str(checkpoint.relative_to(ROOT)),
                checkpoint_sha256=sha256(checkpoint),policy=str((path.parent/'export/policy.pt').relative_to(ROOT)),
                policy_sha256=sha256(path.parent/'export/policy.pt'),actor_equal_to_anchor=equal,
                optimizer_max_step=max(steps),curriculum=saved['infos']['rough_curriculum'],
                final_rough_drift=m['reference_transfer']['latest_drift'],flat_bank_drift=m['flat_bank_drift'],
                checkpoints=validate_checkpoints(path.parent,m),
                timings=validate_tensorboard(path.parent,m,updates,5 if updates>=50 else 0))
