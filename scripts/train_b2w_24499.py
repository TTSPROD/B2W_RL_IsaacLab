"""Local 501-update repair of the measured 24499 checkpoint."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

from b2w_runtime import configure_process, project_kit_args

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/'policies/local/rehearsal_24499/model_24499.pt'
PARENT_SHA = 'c6c6494780d11ffc822bc08447a759e3a57945e71e6588befd8bc709cd031368'
VENDOR_TRAIN = ROOT/'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py'


def main():
    configure_process()
    os.environ['HYDRA_FULL_ERROR'] = '1'
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError('24499 parent SHA mismatch')
    forbidden = ('--resume', '--checkpoint', '--load_run', '--task', '--distributed', '--seed', '--device')
    if any(arg.split('=')[0] in forbidden for arg in sys.argv[1:]):
        raise ValueError('This launcher pins local 24499, task, seed and GPU')
    import torch  # noqa: F401
    import tensordict  # noqa: F401
    from isaaclab.app import AppLauncher
    import isaaclab.app
    launched = []

    class LocalTrainingLauncher(AppLauncher):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            launched.append(self)
            from b2w_runtime import register_b2w_tasks
            register_b2w_tasks()
            import gymnasium as gym
            from b2w_repair501_cfg import TASK
            gym.register(id=TASK, entry_point='isaaclab.envs:ManagerBasedRLEnv', disable_env_checker=True,
                         kwargs={'env_cfg_entry_point': 'b2w_repair501_cfg:env_config',
                                 'rsl_rl_cfg_entry_point': 'b2w_repair501_cfg:agent_config'})
            from b2w_finetune_runner import install_runner
            install_runner(PARENT, PARENT_SHA, ROOT, expected_iteration=24499, lr_cap=5e-6,
                           max_updates=501,
                           extra_sources=('train_b2w_24499.py', 'b2w_repair501_cfg.py',
                               'b2w_regression500_sampling.py', 'b2w_repair501_rewards.py', 'b2w_repair501_audit.py',
                               '../configs/24499_repair501_20260927.json',
                               'b2w_recovery_cfg.py', 'b2w_recovery_sampling.py', 'b2w_retention_cfg.py',
                               'b2w_correction_cfg.py', 'b2w_training_audit.py'),
                           reward_note='exact-zero 50% original + 50% std=.15 kernels; joint_pos_limits -5 to -7.5; other rewards and physics retained')
            import rsl_rl.runners
            from b2w_repair501_audit import audit_repair
            runner = rsl_rl.runners.OnPolicyRunner
            original_load = runner.load

            def checked_load(instance, path, load_optimizer=True):
                audit_repair(instance.env.unwrapped.cfg, PARENT.parent, instance.run_path)
                return original_load(instance, path, load_optimizer)

            runner.load = checked_load
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *a, **kw: str(PARENT)

    isaaclab.app.AppLauncher = LocalTrainingLauncher
    sys.path.insert(0, str(VENDOR_TRAIN.parent))
    sys.argv = [str(VENDOR_TRAIN), *sys.argv[1:], '--task', 'B2W-24499-Repair501-v0',
                '--resume', '--logger', 'tensorboard', '--device', 'cuda:0', '--seed', '9705',
                '--kit_args', project_kit_args()]
    print('VENDOR_TRAIN_ARGV='+json.dumps(sys.argv), flush=True)
    try:
        runpy.run_path(str(VENDOR_TRAIN), run_name='__main__')
    finally:
        for launcher in launched:
            if launcher.app.is_running():
                launcher.app.close()


if __name__ == '__main__':
    main()
