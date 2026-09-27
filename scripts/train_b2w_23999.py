"""Local 500-update continuation of the measured 23999 checkpoint."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

from b2w_runtime import configure_process, project_kit_args

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/'policies/local/recovery_23999/model_23999.pt'
PARENT_SHA = '780a8b486ff25c15f2eb1cadc2bc135a14534c5e5e31debd4583ce1c74c31f81'
VENDOR_TRAIN = ROOT/'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py'


def main():
    configure_process()
    os.environ['HYDRA_FULL_ERROR'] = '1'
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError('23999 parent SHA mismatch')
    forbidden = ('--resume', '--checkpoint', '--load_run', '--task', '--distributed', '--seed', '--device')
    if any(arg.split('=')[0] in forbidden for arg in sys.argv[1:]):
        raise ValueError('This launcher pins local 23999, task, seed and GPU')
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
            from b2w_regression500_cfg import TASK
            gym.register(id=TASK, entry_point='isaaclab.envs:ManagerBasedRLEnv', disable_env_checker=True,
                         kwargs={'env_cfg_entry_point': 'b2w_regression500_cfg:env_config',
                                 'rsl_rl_cfg_entry_point': 'b2w_regression500_cfg:agent_config'})
            from b2w_finetune_runner import install_runner
            install_runner(PARENT, PARENT_SHA, ROOT, expected_iteration=23999, lr_cap=1e-5,
                           max_updates=500,
                           extra_sources=('train_b2w_23999.py', 'b2w_regression500_cfg.py',
                               'b2w_regression500_sampling.py', '../configs/23999_rehearsal500_20260927.json',
                               'b2w_recovery_cfg.py', 'b2w_recovery_sampling.py', 'b2w_retention_cfg.py',
                               'b2w_correction_cfg.py', 'b2w_training_audit.py'),
                           reward_note='unchanged from 23999, including moderate-yaw kernel; command rehearsal only')
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *a, **kw: str(PARENT)

    isaaclab.app.AppLauncher = LocalTrainingLauncher
    sys.path.insert(0, str(VENDOR_TRAIN.parent))
    sys.argv = [str(VENDOR_TRAIN), *sys.argv[1:], '--task', 'B2W-23999-Regression-Rehearsal500-v0',
                '--resume', '--logger', 'tensorboard', '--device', 'cuda:0', '--seed', '9704',
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
