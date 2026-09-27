"""Local, bounded 2000-update recovery from the measured final 21999 checkpoint."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

from b2w_runtime import configure_process, project_kit_args

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "policies/local/fullcycle_21999/model_21999.pt"
PARENT_SHA = "f8f3c7d4fa2600453ebe3af0fdd68d2b105d28fbaa24d3c4d86cb08786d2afd0"
VENDOR_TRAIN = ROOT / "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py"


def main():
    configure_process()
    os.environ["HYDRA_FULL_ERROR"] = "1"
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError("21999 parent SHA mismatch")
    forbidden = ("--resume", "--checkpoint", "--load_run", "--task", "--distributed", "--seed", "--device")
    if any(arg.split("=")[0] in forbidden for arg in sys.argv[1:]):
        raise ValueError("This launcher pins local 21999, task, seed and GPU")
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
            from b2w_recovery_cfg import TASK
            gym.register(id=TASK, entry_point="isaaclab.envs:ManagerBasedRLEnv", disable_env_checker=True,
                         kwargs={"env_cfg_entry_point": "b2w_recovery_cfg:env_config",
                                 "rsl_rl_cfg_entry_point": "b2w_recovery_cfg:agent_config"})
            from b2w_finetune_runner import install_runner
            install_runner(PARENT, PARENT_SHA, ROOT, expected_iteration=21999, lr_cap=2.5e-5,
                           max_updates=2000,
                           extra_sources=("train_b2w_21999.py", "b2w_recovery_cfg.py", "b2w_recovery_sampling.py",
                                          "b2w_retention_cfg.py", "b2w_correction_cfg.py", "b2w_training_audit.py"),
                           reward_note="yaw std 0.25 only for abs(command_yaw) in [0.2,0.6]; other rewards unchanged")
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *a, **kw: str(PARENT)

    isaaclab.app.AppLauncher = LocalTrainingLauncher
    sys.path.insert(0, str(VENDOR_TRAIN.parent))
    sys.argv = [str(VENDOR_TRAIN), *sys.argv[1:], "--task", "B2W-21999-Yaw-Stair-Recovery-v0",
                "--resume", "--logger", "tensorboard", "--device", "cuda:0", "--seed", "9703",
                "--kit_args", project_kit_args()]
    print("VENDOR_TRAIN_ARGV=" + json.dumps(sys.argv), flush=True)
    try:
        runpy.run_path(str(VENDOR_TRAIN), run_name="__main__")
    except BaseException:
        import traceback
        traceback.print_exc()
        raise
    finally:
        for launcher in launched:
            if launcher.app.is_running():
                launcher.app.close()


if __name__ == "__main__":
    main()
