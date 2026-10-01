"""Pinned local 100-update A/B arm, supervised by the dashboard."""
import argparse
import os
import runpy
import sys

from run_support import ROOT,managed_entrypoint,read_json,sha256,write_json
from b2w_runtime import configure_process,project_kit_args


def main():
    managed_entrypoint()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',required=True,choices=('control','posture'))
    parser.add_argument('--seed',type=int,choices=(9901,9902),default=9901)
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args()
    os.environ.update(B2W_PILOT_ARM=args.arm,B2W_PILOT_SEED=str(args.seed),HYDRA_FULL_ERROR='1')
    configure_process()
    plan=read_json(ROOT/'configs/24650_tracking_posture_ab_20260930.json')
    parent=ROOT/plan['parent_checkpoint']
    for path,expected in ((parent,plan['parent_sha256']),
        (parent.parent/'env.yaml',plan['parent_env_sha256']),
        (parent.parent/'agent.yaml',plan['parent_agent_sha256']),
        (ROOT/plan['basis_summary'],plan['basis_summary_sha256'])):
        if sha256(path)!=expected:
            raise RuntimeError('Pinned pilot input changed: '+str(path))
    import torch
    import tensordict
    import isaaclab.app
    from isaaclab.app import AppLauncher
    launched=[]
    class PilotLauncher(AppLauncher):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);launched.append(self)
            from b2w_runtime import register_b2w_tasks
            register_b2w_tasks()
            import gymnasium as gym
            gym.register(id='B2W-Tracking-Pilot-v0',entry_point='isaaclab.envs:ManagerBasedRLEnv',disable_env_checker=True,
                kwargs={'env_cfg_entry_point':'b2w_tracking_pilot_cfg:env_config','rsl_rl_cfg_entry_point':'b2w_tracking_pilot_cfg:agent_config'})
            from b2w_finetune_runner import install_runner
            install_runner(parent,plan['parent_sha256'],ROOT,expected_iteration=24650,
                lr_cap=plan['lr_cap'],max_updates=100,
                extra_sources=('train_tracking_pilot.py','b2w_tracking_pilot_cfg.py','b2w_tracking_posture.py',
                    'b2w_core_stage3_cfg.py','b2w_core_stage3_sampling.py','b2w_regression500_sampling.py',
                    'b2w_correction_cfg.py','b2w_recovery_cfg.py','b2w_recovery_sampling.py','b2w_retention_cfg.py',
                    'b2w_training_audit.py','../configs/24650_tracking_posture_ab_20260930.json'),
                reward_note='Matched A/B '+args.arm+'; only bounded target-cohort pose multiplier changes')
            import rsl_rl.runners
            from b2w_tracking_pilot_cfg import audit
            runner=rsl_rl.runners.OnPolicyRunner
            original_load=runner.load
            def checked_load(instance,path,load_optimizer=True):
                audit(instance.env.unwrapped.cfg,instance.cfg,parent.parent,instance.run_path)
                return original_load(instance,path,load_optimizer)
            runner.load=checked_load
            if args.audit_only:
                def audit_only(instance,*a,**kw):
                    write_json(instance.run_path/'progress.json',{'status':'audit_only','completed_updates':0,
                               'target_updates':0,'arm':args.arm})
                runner.learn=audit_only
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path=lambda *a,**kw:str(parent)
    isaaclab.app.AppLauncher=PilotLauncher
    train=ROOT/'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py'
    sys.path.insert(0,str(train.parent))
    sys.argv=[str(train),'--headless','--num_envs',str(128 if args.audit_only else plan['num_envs']),
        '--max_iterations','100','--task','B2W-Tracking-Pilot-v0','--resume','--logger','tensorboard',
        '--device','cuda:0','--seed',str(args.seed),'--run_name','audit' if args.audit_only else 'pilot',
        '--kit_args',project_kit_args()]
    try:
        runpy.run_path(str(train),run_name='__main__')
    finally:
        for launcher in launched:
            if launcher.app.is_running():launcher.app.close()


if __name__=='__main__':main()
