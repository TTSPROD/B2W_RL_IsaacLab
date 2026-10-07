"""Independent completion proof for the native schedule A/B."""
import re
from run_support import ROOT,read_json,write_json,sha256,utc_now

def validate_training_completion(job,arm,plan,returncode):
    """Validate completed PPO outside Kit, whose fast shutdown exits Python."""
    if returncode!=0:raise ValueError('Training child did not exit successfully')
    import torch
    import yaml
    folder=job/'training_'/arm
    audit=read_json(folder/'config_audit.json')
    if (audit['status']!='passed' or audit['arm']!=arm
        or audit['environment_sha256']!=sha256(folder/'reset_environment.yaml')):
        raise ValueError('Training configuration audit mismatch')
    run=(ROOT/read_json(job/'training_run.json')['path']).resolve()
    run.relative_to(ROOT/'logs/rsl_rl')
    agent=yaml.safe_load((run/'params/agent.yaml').read_text(encoding='utf-8'))
    from schedule_pilot_contract import audit_agent
    audit_agent(agent,arm)
    if agent['experiment_name']!=f'b2w_24650_schedule_{arm}_{plan["seed"]}':
        raise ValueError('Training experiment drift')
    progress=read_json(folder/'progress.json')
    steps=24*plan['updates']
    if (progress['policy_steps']!=steps or progress['completed_updates']!=plan['updates']
        or progress['target_updates']!=plan['updates']):raise ValueError('Incomplete training rollout')
    stdout=(job/f'pilot_{arm}_stdout.log').read_text(encoding='utf-8')
    clean=re.sub(r'\x1b\[[0-9;]*m','',stdout)
    iterations=[int(n) for n in re.findall(r'Learning iteration\s+(\d+)/',clean)]
    total=[int(n) for n in re.findall(r'Total timesteps:\s+(\d+)',clean)]
    end=plan['final_checkpoint_iteration']
    if (iterations!=list(range(24650,end+1)) or not total or total[-1]!=steps*plan['num_envs']
        or 'Training time:' not in clean):raise ValueError('Incomplete standard runner log')
    checkpoint=run/f'model_{end}.pt'
    saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
    parent=torch.load(ROOT/plan['parent_checkpoint'],map_location='cpu',weights_only=True)
    def finite(value):
        if torch.is_tensor(value):return bool(torch.isfinite(value).all())
        if isinstance(value,dict):return all(finite(v) for v in value.values())
        if isinstance(value,(tuple,list)):return all(finite(v) for v in value)
        return True
    if saved['iter']!=end or not finite(saved):raise ValueError('Invalid final checkpoint')
    updates=plan['updates']*agent['algorithm']['num_learning_epochs']*agent['algorithm']['num_mini_batches']
    previous=parent['optimizer_state_dict']['state'];current=saved['optimizer_state_dict']['state']
    if (current.keys()!=previous.keys() or not current or
        any(float(current[k]['step'])-float(previous[k]['step'])!=updates for k in previous)):
        raise ValueError('Incomplete Adam update count')
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    ea=EventAccumulator(str(run),size_guidance={'scalars':0});ea.Reload()
    rates=ea.Scalars('Loss/learning_rate')
    if len(rates)!=plan['updates']:raise ValueError('Incomplete learning rate log')
    if arm=='fixed' and (any(abs(r.value-1e-5)>1e-10 for r in rates) or
        any(abs(g['lr']-1e-5)>1e-10 for g in saved['optimizer_state_dict']['param_groups'])):
        raise ValueError('Fixed learning rate drift')
    completed={**progress,'status':'completed','completion_verified':True}
    receipt={'run':run.relative_to(ROOT).as_posix(),'checkpoint':checkpoint.relative_to(ROOT).as_posix(),
        'checkpoint_sha256':sha256(checkpoint),'progress':completed,'verified_utc':utc_now(),
        'learning_rate':{'min_logged':min(r.value for r in rates),'max_logged':max(r.value for r in rates),
        'last_logged':rates[-1].value,'final_optimizer_lr':saved['optimizer_state_dict']['param_groups'][0]['lr']},
        'child_returncode':returncode,'final_iteration':end,'adam_updates_per_parameter':updates,
        'completed_progress_projection':{'source_sha256':sha256(folder/'progress.json'),
            'target':(run/'progress.json').relative_to(ROOT).as_posix(),
            'added_fields':{'status':'completed','completion_verified':True}},
        'raw_sha256':{str(p.relative_to(ROOT)):sha256(p) for p in
            (folder/'progress.json',folder/'config_audit.json',
             job/f'pilot_{arm}_stdout.log',run/'params/agent.yaml',folder/'runtime_sources.json')}}
    return checkpoint,receipt
