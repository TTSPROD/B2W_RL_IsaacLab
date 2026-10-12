"""One pinned F1 arm; supervised locally by the dashboard."""
import argparse
import os
import runpy
import sys
from run_support import ROOT, managed_entrypoint, write_json
from short_flight_contract import load_plan, assert_exact_state
from b2w_runtime import configure_process, project_kit_args

EXTRA_SOURCES = ('train_short_flight.py','b2w_short_flight_cfg.py','b2w_short_flight_env.py','short_flight_contract.py',
    'b2w_short_flight_terrain.py','b2w_curriculum_env.py','stair_curriculum_monitor.py','training_coverage.py',
    'b2w_core_stage3_cfg.py','b2w_core_stage3_sampling.py','b2w_regression500_sampling.py',
    'b2w_correction_cfg.py','b2w_recovery_cfg.py','b2w_recovery_sampling.py','b2w_retention_cfg.py',
    'b2w_training_audit.py','../configs/24650_short_flight_20261001.json')


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',required=True,choices=('shortflight',))
    parser.add_argument('--audit-only',action='store_true')
    parser.add_argument('--updates',type=int,choices=(1500,),default=1500)
    args = parser.parse_args()
    plan = load_plan()
    parent = ROOT/plan['parent_checkpoint']
    os.environ.update(B2W_SHORT_FLIGHT_ARM=args.arm,HYDRA_FULL_ERROR='1')
    configure_process()
    import torch
    import tensordict
    import isaaclab.app
    from isaaclab.app import AppLauncher
    launched = []
    class F1Launcher(AppLauncher):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw); launched.append(self)
            from b2w_runtime import register_b2w_tasks
            register_b2w_tasks()
            import gymnasium as gym
            gym.register(id='B2W-Short-Flight-v0',entry_point='b2w_short_flight_env:ShortFlightEnv',disable_env_checker=True,
                         kwargs={'env_cfg_entry_point':'b2w_short_flight_cfg:env_config',
                                 'rsl_rl_cfg_entry_point':'b2w_short_flight_cfg:agent_config'})
            from b2w_finetune_runner import install_runner
            from b2w_short_flight_env import install_coverage
            install_runner(parent,plan['parent_sha256'],ROOT,expected_iteration=24650,
                lr_cap=plan['arms'][args.arm]['lr_cap'],max_updates=1500,extra_sources=EXTRA_SOURCES,
                reward_note='All parent rewards unchanged; common safety terminals; straight short flight target stairs',diagnostics_factory=install_coverage)
            import rsl_rl.runners
            from b2w_short_flight_cfg import audit
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
            original_log=runner.log
            def exact_checkpoints(instance,locs,*a,**kw):
                original_log(instance,locs,*a,**kw)
                if instance.completed_updates in plan['probe_updates'] or instance.completed_updates==args.updates:
                    instance.save(str(instance.run_path/f"model_{24650+instance.completed_updates}.pt"))
            runner.log=exact_checkpoints
            if args.audit_only:
                def audit_only(instance,*a,**kw):
                    from b2w_short_flight_env import preflight
                    preflight(instance,plan)
                    write_json(instance.run_path/'progress.json',{'status':'audit_only','arm':args.arm,
                               'completed_updates':0,'target_updates':0})
                runner.learn = audit_only
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *a,**kw:str(parent)
    isaaclab.app.AppLauncher = F1Launcher
    train = ROOT/'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py'
    sys.path.insert(0,str(train.parent))
    sys.argv = [str(train),'--headless','--num_envs',str(128 if args.audit_only else plan['num_envs']),
        '--max_iterations',str(args.updates),'--task','B2W-Short-Flight-v0','--resume','--logger','tensorboard',
        '--device','cuda:0','--seed',str(plan['seed']),'--run_name','audit' if args.audit_only else 'pilot',
        '--kit_args',project_kit_args()]
    try:
        runpy.run_path(str(train),run_name='__main__')
    except BaseException:
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        raise
    finally:
        for launcher in launched:
            if launcher.app.is_running(): launcher.app.close()


if __name__=='__main__': main()
