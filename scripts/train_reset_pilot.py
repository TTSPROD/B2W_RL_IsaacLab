"""Minimal local bootstrap of unchanged Robot Lab train.py and standard runner."""
import argparse
import os
import runpy
import sys
import faulthandler
from pathlib import Path
from run_support import ROOT, managed_entrypoint, write_json, sha256
from reset_pilot_contract import load_plan
from b2w_runtime import configure_process, project_kit_args


def main():
    managed_entrypoint()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',choices=('control','upright'),required=True)
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args();plan=load_plan()
    faulthandler.enable()
    if args.preflight:faulthandler.dump_traceback_later(60,repeat=True)
    job=Path(os.environ['B2W_JOB_DIR'])
    output=job/('preflight_' if args.preflight else 'training_')/args.arm
    output.mkdir(parents=True,exist_ok=False)
    mode='preflight' if args.preflight else 'train'
    os.environ.update(B2W_RESET_ARM=args.arm,B2W_RESET_MODE=mode,B2W_RESET_OUTPUT=str(output),
        B2W_RESET_RUN_NAME=job.name,HYDRA_FULL_ERROR='1')
    configure_process()
    import torch
    import tensordict
    import isaaclab.app
    from isaaclab.app import AppLauncher
    launched=[]
    class LocalLauncher(AppLauncher):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);launched.append(self)
            from b2w_runtime import register_b2w_tasks
            register_b2w_tasks()
            import gymnasium as gym
            gym.register(id='B2W-Reset-Pilot-v0',entry_point='b2w_reset_pilot_env:ResetPilotEnv',disable_env_checker=True,
                kwargs={'env_cfg_entry_point':'b2w_reset_pilot_cfg:env_config',
                        'rsl_rl_cfg_entry_point':'b2w_reset_pilot_cfg:agent_config'})
            from rsl_rl.runners import OnPolicyRunner
            import rsl_rl.algorithms.ppo as ppo_module
            assert OnPolicyRunner.__module__=='rsl_rl.runners.on_policy_runner'
            runtime_sources=[Path(sys.modules[OnPolicyRunner.__module__].__file__),Path(ppo_module.__file__)]
            write_json(output/'runtime_sources.json',{'standard_runner':True,'custom_runner_hooks':False,
                'source_sha256':{str(p):sha256(p) for p in runtime_sources},
                'runtime':{'gpu':torch.cuda.get_device_name(),'torch':torch.__version__}})
    isaaclab.app.AppLauncher=LocalLauncher
    train=ROOT/'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py'
    sys.path.insert(0,str(train.parent))
    sys.argv=[str(train),'--headless','--task','B2W-Reset-Pilot-v0','--resume',
        '--num_envs',str(128 if args.preflight else plan['num_envs']),
        '--max_iterations',str(plan['updates']),'--seed',str(plan['seed']),
        '--load_run','_parent','--checkpoint','model_24650.pt',
        '--device','cuda:0','--logger','tensorboard','--kit_args',project_kit_args()]
    try:
        if not args.preflight:
            runpy.run_path(str(train),run_name='__main__')
            # Kit fast shutdown may terminate this process at simulation_app.close().
            # The independent parent validates final weights, Adam and runner logs.
            return
        # Load upstream definitions/launch SimulationApp without calling training main.
        upstream=runpy.run_path(str(train),run_name='b2w_standard_preflight')
        import gymnasium as gym
        from b2w_reset_pilot_cfg import env_config,agent_config
        from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
        from rsl_rl.runners import OnPolicyRunner
        from stair_curriculum_contract import assert_exact_state
        cfg=env_config();cfg.scene.num_envs=128;cfg.seed=plan['seed'];cfg.log_dir=str(output)
        agent=agent_config();env=RslRlVecEnvWrapper(gym.make('B2W-Reset-Pilot-v0',cfg=cfg),clip_actions=agent.clip_actions)
        runner=OnPolicyRunner(env,agent.to_dict(),log_dir=str(output),device=agent.device)
        runner.load(str(ROOT/plan['parent_checkpoint']))
        saved=torch.load(ROOT/plan['parent_checkpoint'],map_location='cpu',weights_only=True)
        assert_exact_state(runner.alg.policy.state_dict(),saved['model_state_dict'],'model')
        assert_exact_state(runner.alg.optimizer.state_dict(),saved['optimizer_state_dict'],'Adam')
        obs=env.get_observations()
        assert obs['policy'].shape==(128,57) and env.num_actions==16 and abs(env.unwrapped.step_dt-.02)<1e-9
        with torch.inference_mode():
            for step in range(plan['preflight_steps']):
                obs,reward,done,extra=env.step(runner.alg.policy.act_inference(obs))
                assert torch.isfinite(obs['policy']).all() and torch.isfinite(reward).all()
                assert not (env.unwrapped.reset_terminated&extra['time_outs']).any()
                if step%120==0:print('RESET_PREFLIGHT',args.arm,step,'/3600',flush=True)
        # Exercise simultaneous timeout/safety without changing physical predicates.
        raw=env.unwrapped;raw.monitor.flags[0,3]=True;raw.episode_length_buf[0]=3500
        raw.termination_manager.compute()
        assert raw.termination_manager.terminated[0] and not raw.termination_manager.time_outs[0]
        result=raw.snapshot();result.update(status='completed',updates=0,parent_state_exact=True,
            adam_state_exact=True,terminal_overrides_timeout=True,
            runner_source_sha256=sha256(Path(sys.modules[OnPolicyRunner.__module__].__file__)),
            train_source_sha256=sha256(train),runtime={'gpu':torch.cuda.get_device_name(),
            'torch':torch.__version__,'rsl_rl':__import__('importlib.metadata',fromlist=['version']).version('rsl-rl-lib')})
        write_json(output/'result.json',result)
        env.close()
    finally:
        if args.preflight:faulthandler.cancel_dump_traceback_later()
        for launcher in launched:
            if launcher.app.is_running():launcher.app.close()


if __name__=='__main__':main()
