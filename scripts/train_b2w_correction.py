"""Run exactly 100 corrective updates from measured checkpoint 20500.

Usage: scripts/run_local.ps1 scripts/train_b2w_correction.py --headless
       --num_envs 4096 --max_iterations 100
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

from b2w_runtime import configure_process, project_kit_args

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "policies/local/commands_stairs_20500/model_20500.pt"
PARENT_SHA = "b7ef4838068ebd17ec9bbcb92f725938f4f45a83b136d61e8f1ffd00f7083e7c"
VENDOR_TRAIN = ROOT / "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py"


def main():
    configure_process()
    os.environ["HYDRA_FULL_ERROR"] = "1"
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError("20500 parent SHA mismatch")
    forbidden = ("--resume", "--checkpoint", "--load_run", "--task", "--distributed")
    if any(arg.split("=")[0] in forbidden for arg in sys.argv[1:]):
        raise ValueError("This launcher fixes the local 20500 parent/task; no distributed run")
    # As in the verified local evaluator, load the Torch/tensordict native
    # libraries before Kit changes the Windows DLL search environment.
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
            from b2w_correction_cfg import TASK
            gym.register(id=TASK, entry_point="isaaclab.envs:ManagerBasedRLEnv", disable_env_checker=True,
                         kwargs={"env_cfg_entry_point": "b2w_correction_cfg:env_config",
                                 "rsl_rl_cfg_entry_point": "b2w_correction_cfg:agent_config"})
            from b2w_finetune_runner import install_runner
            install_runner(PARENT, PARENT_SHA, ROOT, expected_iteration=20500, lr_cap=2.5e-5,
                           max_updates=100, extra_sources=("train_b2w_correction.py", "b2w_correction_cfg.py"),
                           reward_note="yaw std 0.25 only for abs(command_yaw) in [0.2,0.6]; other rewards unchanged")
            # The upstream loader searches its log root for a checkpoint. Resolve
            # only the pinned parent here instead of copying it into mutable logs.
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *a, **kw: str(PARENT)

    isaaclab.app.AppLauncher = LocalTrainingLauncher
    sys.path.insert(0, str(VENDOR_TRAIN.parent))
    sys.argv = [str(VENDOR_TRAIN), *sys.argv[1:], "--task", "B2W-20500-Yaw-Response-Correction-v0",
                "--resume", "--logger", "tensorboard", "--device", "cuda:0", "--seed", "9602",
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


