"""One pinned LR arm; supervised locally by the dashboard."""
import argparse
import os
import runpy
import sys
from run_support import ROOT, managed_entrypoint, write_json
from lr_pilot_contract import load_plan, assert_exact_state
from b2w_runtime import configure_process, project_kit_args

EXTRA_SOURCES = ('train_lr_pilot.py','b2w_lr_pilot_cfg.py','lr_pilot_contract.py','training_coverage.py',
    'b2w_core_stage3_cfg.py','b2w_core_stage3_sampling.py','b2w_regression500_sampling.py',
    'b2w_correction_cfg.py','b2w_recovery_cfg.py','b2w_recovery_sampling.py','b2w_retention_cfg.py',
    'b2w_training_audit.py','../configs/24650_lr_ab_20260930.json')


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',required=True,choices=('lrcontrol','lrlow'))
    parser.add_argument('--audit-only',action='store_true')
    args = parser.parse_args()
    plan = load_plan()
    parent = ROOT/plan['parent_checkpoint']
    os.environ.update(B2W_LR_ARM=args.arm,HYDRA_FULL_ERROR='1')
    configure_process()
    import torch
    import tensordict
    import isaaclab.app
    from isaaclab.app import AppLauncher
    launched = []
    class LRLauncher(AppLauncher):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw); launched.append(self)
            from b2w_runtime import register_b2w_tasks
            register_b2w_tasks()
            import gymnasium as gym
            gym.register(id='B2W-LR-Pilot-v0',entry_point='isaaclab.envs:ManagerBasedRLEnv',disable_env_checker=True,
                         kwargs={'env_cfg_entry_point':'b2w_lr_pilot_cfg:env_config',
                                 'rsl_rl_cfg_entry_point':'b2w_lr_pilot_cfg:agent_config'})
            from b2w_finetune_runner import install_runner
            from training_coverage import install_coverage
            install_runner(parent,plan['parent_sha256'],ROOT,expected_iteration=24650,
                lr_cap=plan['arms'][args.arm]['lr_cap'],max_updates=300,extra_sources=EXTRA_SOURCES,
                reward_note='All parent rewards unchanged; matched LR-cap experiment',diagnostics_factory=install_coverage)
            import rsl_rl.runners
            from b2w_lr_pilot_cfg import audit
            runner = rsl_rl.runners.OnPolicyRunner
            original_load = runner.load
            def checked_load(instance,path,load_optimizer=True):
                audit(instance.env.unwrapped.cfg,instance.cfg,parent.parent,instance.run_path)
                result = original_load(instance,path,load_optimizer)
                saved = torch.load(parent,map_location='cpu',weights_only=True)['optimizer_state_dict']
                actual = instance.alg.optimizer.state_dict()
                assert_exact_state(actual['state'],saved['state'],'Adam')
                saved_groups = [{k:v for k,v in group.items() if k!='lr'} for group in saved['param_groups']]
                actual_groups = [{k:v for k,v in group.items() if k!='lr'} for group in actual['param_groups']]
                assert_exact_state(actual_groups,saved_groups,'Adam.groups_except_declared_lr')
                write_json(instance.run_path/'optimizer_restore_audit.json',{'status':'passed',
                           'state_tensors_exact':True,'lr_cap':plan['arms'][args.arm]['lr_cap']})
                return result
            runner.load = checked_load
            if args.audit_only:
                def audit_only(instance,*a,**kw):
                    write_json(instance.run_path/'progress.json',{'status':'audit_only','arm':args.arm,
                               'completed_updates':0,'target_updates':0})
                runner.learn = audit_only
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *a,**kw:str(parent)
    isaaclab.app.AppLauncher = LRLauncher
    train = ROOT/'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py'
    sys.path.insert(0,str(train.parent))
    sys.argv = [str(train),'--headless','--num_envs',str(128 if args.audit_only else plan['num_envs']),
        '--max_iterations',str(plan['additional_updates']),'--task','B2W-LR-Pilot-v0','--resume','--logger','tensorboard',
        '--device','cuda:0','--seed',str(plan['seed']),'--run_name','audit' if args.audit_only else 'pilot',
        '--kit_args',project_kit_args()]
    try:
        runpy.run_path(str(train),run_name='__main__')
    finally:
        for launcher in launched:
            if launcher.app.is_running(): launcher.app.close()


if __name__=='__main__': main()
