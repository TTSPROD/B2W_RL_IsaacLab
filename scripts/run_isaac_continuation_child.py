"""Isolated local CUDA child: standard training, no-update preflight, export/eval."""
import argparse
import os
from pathlib import Path
import runpy
import sys

from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('preflight', 'train', 'export', 'evaluate'), required=True)
    parser.add_argument('--arm', choices=('control', 'focus'), default='control')
    args, remainder = parser.parse_known_args()
    plan = read_json(ROOT/'configs/24650_native_continuation_20261012.json')
    runtime = read_json(ROOT/'.runtime/isaac-ubuntu-runtime.json')
    if runtime['hardware_enabled'] or not runtime['eula_accepted'] or runtime['isaaclab_commit'] != '37ddf626871758333d6ed89cf64ad702aef127d0':
        raise ValueError('Licensed isolated simulator-only runtime required')
    if sha256(ROOT/plan['parent']) != plan['parent_sha256']:
        raise ValueError('Parent checkpoint drift')
    job = Path(os.environ['B2W_JOB_DIR'])
    root = job/'native_continuation'
    manifest = read_json(root/'preflight_manifest.json')
    for name, digest in manifest['source_sha256'].items():
        if sha256(ROOT/name) != digest:
            raise ValueError('Frozen source changed: '+name)
    os.environ.update(OMNI_KIT_ACCEPT_EULA='YES', B2W_NATIVE_ARM=args.arm, B2W_NATIVE_MODE=args.mode,
                      HYDRA_FULL_ERROR='1')
    libraries = ROOT/'.runtime/isaac-native-libs/usr/lib/x86_64-linux-gnu'
    if str(libraries) not in os.environ.get('LD_LIBRARY_PATH', '').split(':'):
        raise ValueError('Local native libraries missing')
    config = root/'kit-config'
    config.mkdir(parents=True, exist_ok=True)
    paths = {'cache_root': ROOT/'.cache/isaac-kit', 'data_root': ROOT/'.cache/isaac-kit-data',
             'logs_root': root/'kit-logs'}
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    (config/'omniverse.toml').write_text('[paths]\n'+'\n'.join(f'{k} = "{v}"' for k, v in paths.items())+'\n')
    os.environ['OMNI_CONFIG_PATH'] = str(config)
    from b2w_runtime import configure_process, project_kit_args
    configure_process()
    import torch
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    if args.mode == 'export':
        if remainder:
            raise ValueError('Unexpected export args')
        from check_policy_contract import check_training_export, run_checks
        receipt = read_json(root/args.arm/'completion.json')
        checkpoint = ROOT/receipt['checkpoint']
        if sha256(checkpoint) != receipt['checkpoint_sha256']:
            raise ValueError('Training checkpoint changed')
        result = check_training_export(checkpoint, root/'exports'/f'std{args.arm}_24799', run_checks())
        write_json(root/args.arm/'export.json', result)
        return
    if args.mode == 'evaluate':
        # The protocol, seeds and maps must be frozen under this job.
        allowed = ('--terrain', '--output', '--seeds', '--policy-map', '--protocol-module')
        if len(remainder) != 10 or any(remainder[i] not in allowed for i in range(0, 10, 2)):
            raise ValueError('Only declared evaluation arguments allowed')
        options = dict(zip(remainder[::2], remainder[1::2]))
        if options['--protocol-module'] != 'locomotion_v2_protocol' or options['--seeds'] != '5':
            raise ValueError('Full v2 only')
        for key in ('--policy-map', '--output'):
            if not Path(options[key]).resolve().is_relative_to(root/'evaluation'):
                raise ValueError('Evaluation must stay in this job')
        sys.argv = [str(ROOT/'scripts/eval_fullcycle_terrain.py'), *remainder]
        runpy.run_path(sys.argv[0], run_name='__main__')
        return
    if remainder:
        raise ValueError('Frozen training budget does not accept overrides')
    import isaaclab.app
    from isaaclab.app import AppLauncher
    launched = []

    def register():
        from b2w_runtime import register_b2w_tasks
        register_b2w_tasks()
        import gymnasium as gym
        from b2w_native_continuation_cfg import TASK
        gym.register(id=TASK, entry_point='b2w_native_continuation_env:NativeContinuationEnv', disable_env_checker=True,
                     kwargs={'env_cfg_entry_point': 'b2w_native_continuation_cfg:env_config',
                             'rsl_rl_cfg_entry_point': 'b2w_native_continuation_cfg:agent_config'})
        from rsl_rl.runners import OnPolicyRunner
        import rsl_rl.algorithms.ppo as ppo
        runtime_paths = [Path(sys.modules[OnPolicyRunner.__module__].__file__), Path(ppo.__file__)]
        out = root/args.arm/args.mode
        write_json(out/'runtime.json', {'torch': torch.__version__, 'gpu': torch.cuda.get_device_name(),
                   'standard_runner': True, 'custom_runner_hooks': False,
                   'sources': {str(p): sha256(p) for p in runtime_paths}})

    class LocalLauncher(AppLauncher):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            launched.append(self)
            register()

    isaaclab.app.AppLauncher = LocalLauncher
    if args.mode == 'train':
        train = ROOT/plan['standard_train']
        sys.path.insert(0, str(train.parent))
        sys.argv = [str(train), '--headless', '--task', 'B2W-Native-Standard-Continuation-v0', '--resume',
                    '--num_envs', str(plan['training']['num_envs']), '--max_iterations', str(plan['training']['updates_per_arm']),
                    '--seed', str(plan['training']['seed']), '--load_run', '_parent', '--checkpoint', 'model_24650.pt',
                    '--device', 'cuda:0', '--logger', 'tensorboard', '--kit_args', project_kit_args()]
        try:
            runpy.run_path(str(train), run_name='__main__')
        finally:
            for launcher in launched:
                if launcher.app.is_running():
                    launcher.app.close()
        return
    # Exercise the real wrapper and native checkpoint load, with no PPO calls.
    launcher = LocalLauncher({'headless': True, 'device': 'cuda:0', 'kit_args': project_kit_args()})
    env = None
    try:
        from b2w_native_continuation_cfg import env_config, agent_config
        from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
        from rsl_rl.runners import OnPolicyRunner
        import gymnasium as gym
        cfg = env_config()
        cfg.scene.num_envs = plan['preflight']['num_envs']
        cfg.seed = plan['training']['seed']
        env = gym.make('B2W-Native-Standard-Continuation-v0', cfg=cfg)
        wrapper = RslRlVecEnvWrapper(env, clip_actions=None)
        agent = agent_config()
        runner = OnPolicyRunner(wrapper, agent.to_dict(), log_dir=None, device='cuda:0')
        runner.load(str(ROOT/plan['parent']))
        saved = torch.load(ROOT/plan['parent'], map_location='cpu', weights_only=False)
        for name, value in runner.alg.policy.state_dict().items():
            assert torch.equal(value.cpu(), saved['model_state_dict'][name]), name
        def optimizer_equal():
            current = runner.alg.optimizer.state_dict()
            assert current['param_groups'] == saved['optimizer_state_dict']['param_groups']
            for key, values in current['state'].items():
                for name, value in values.items():
                    assert torch.equal(value.cpu(), saved['optimizer_state_dict']['state'][key][name]), (key, name)
        optimizer_equal()
        command = env.unwrapped.command_manager.get_term('base_velocity')
        # This deterministic preflight keeps training noise/DR in observations.
        with torch.inference_mode():
            obs = wrapper.get_observations()
            for step in range(plan['preflight']['steps']):
                action = runner.alg.policy.act_inference(obs)
                obs, reward, done, extra = wrapper.step(action)
                assert torch.isfinite(obs['policy']).all() and torch.isfinite(reward).all()
                if step % 500 == 0:
                    print('NATIVE_PREFLIGHT', args.arm, step, flush=True)
            for name, value in runner.alg.policy.state_dict().items():
                assert torch.equal(value.cpu(), saved['model_state_dict'][name]), name
            optimizer_equal()
            base = env.unwrapped
            base.safety_flags[0, 1] = True
            base.episode_length_buf[0] = base.max_episode_length
            base.termination_manager.compute()
            assert base.termination_manager.terminated[0] and not base.termination_manager.time_outs[0]
        snapshot = base.snapshot()
        assert snapshot['initial_tilt_invalid'] == 0, snapshot
        assert all(x > 0 for x in snapshot['command_cycles']), snapshot
        write_json(root/args.arm/'preflight'/'result.json', {
            'status': 'passed', 'ppo_updates': 0, 'steps': plan['preflight']['steps'],
            'parent_weights_exact': True, 'adam_exact': True, 'terminal_overrides_timeout': True,
            'coverage': snapshot})
    finally:
        if env is not None:
            env.close()
        launcher.app.close()


if __name__ == '__main__':
    main()
