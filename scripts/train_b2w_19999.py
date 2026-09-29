"""Bootstrap the unmodified vendor Robot Lab train.py for local continuation.

Usage: scripts/run_local.ps1 scripts/train_b2w_19999.py --headless
       --num_envs 4096 --max_iterations 2000
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

from b2w_runtime import configure_process, project_kit_args

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "policies/server/upstream_19999/upstream_model_19999.pt"
PARENT_SHA = "e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc"
VENDOR_TRAIN = ROOT / "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py"


def main():
    configure_process()
    os.environ["HYDRA_FULL_ERROR"] = "1"
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError("19999 parent SHA mismatch")
    forbidden = ("--resume", "--checkpoint", "--load_run", "--task", "--distributed")
    if any(arg.split("=")[0] in forbidden for arg in sys.argv[1:]):
        raise ValueError("This launcher fixes the local 19999 parent/task; no distributed run")
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
            from b2w_retention_cfg import TASK
            gym.register(id=TASK, entry_point="isaaclab.envs:ManagerBasedRLEnv", disable_env_checker=True,
                         kwargs={"env_cfg_entry_point": "b2w_retention_cfg:env_config",
                                 "rsl_rl_cfg_entry_point": "b2w_retention_cfg:agent_config"})
            from b2w_finetune_runner import install_runner
            install_runner(PARENT, PARENT_SHA, ROOT, max_updates=2000,
                           extra_sources=("b2w_retention_cfg.py", "b2w_training_audit.py"))
            # The upstream loader searches its log root for a checkpoint. Resolve
            # only the pinned parent here instead of copying it into mutable logs.
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *a, **kw: str(PARENT)

    isaaclab.app.AppLauncher = LocalTrainingLauncher
    sys.path.insert(0, str(VENDOR_TRAIN.parent))
    sys.argv = [str(VENDOR_TRAIN), *sys.argv[1:], "--task", "B2W-19999-Retention-Fullcycle-v0",
                "--resume", "--logger", "tensorboard", "--device", "cuda:0", "--seed", "9701",
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

