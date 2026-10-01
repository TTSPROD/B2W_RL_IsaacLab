"""Local 100-update pure-axis sampling experiment from selected checkpoint 24650."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import traceback

from b2w_runtime import configure_process, project_kit_args

ROOT = Path(__file__).resolve().parents[1]
PARENT_DIR = ROOT / "policies/local/core_24650"
PARENT = PARENT_DIR / "model_24650.pt"
PARENT_SHA = "458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123"
VENDOR_TRAIN = ROOT / "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py"


def main():
    from run_support import managed_entrypoint
    managed_entrypoint()
    configure_process()
    os.environ["HYDRA_FULL_ERROR"] = "1"
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError("24650 parent SHA mismatch")
    forbidden = ("--resume", "--checkpoint", "--load_run", "--task", "--distributed", "--seed", "--device")
    if any(arg.split("=")[0] in forbidden for arg in sys.argv[1:]):
        raise ValueError("This launcher pins local 24650, task, seed and GPU")
    supplied = sys.argv[1:]

    def option(name):
        for index, arg in enumerate(supplied):
            if arg == name and index + 1 < len(supplied):
                return supplied[index + 1]
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
        return None

    num_envs = option("--num_envs")
    max_iterations = option("--max_iterations")
    run_name = option("--run_name")
    smoke = (run_name == "audit_smoke" and max_iterations == "1"
             and num_envs is not None and 1 <= int(num_envs) <= 128)
    if (num_envs is not None or max_iterations is not None) and not smoke:
        raise ValueError("num_envs/max_iterations overrides are allowed only for the one-update audit_smoke")
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
            from b2w_core_stage3_cfg import TASK, PLAN
            gym.register(id=TASK, entry_point="isaaclab.envs:ManagerBasedRLEnv", disable_env_checker=True,
                         kwargs={"env_cfg_entry_point": "b2w_core_stage3_cfg:env_config",
                                 "rsl_rl_cfg_entry_point": "b2w_core_stage3_cfg:agent_config"})
            from b2w_finetune_runner import install_runner
            install_runner(
                PARENT, PARENT_SHA, ROOT, expected_iteration=PLAN["parent_iteration"],
                lr_cap=PLAN["lr_cap"], max_updates=PLAN["additional_updates"],
                extra_sources=(
                    "train_b2w_24650_core_stage3.py", "b2w_core_stage3_cfg.py",
                    "b2w_core_stage3_sampling.py", "b2w_core_stage3_audit.py",
                    "../configs/24650_core_stage3_20260929.json",
                    "../docs/experiments/24650_core_stage3_20260929.md",
                    "b2w_retention_cfg.py", "b2w_correction_cfg.py",
                    "b2w_recovery_cfg.py", "b2w_recovery_sampling.py",
                    "b2w_regression500_sampling.py", "b2w_training_audit.py"),
                reward_note=(
                    "exactly retained from selected 24650; stage 3 changes only Flat/Rough command-bank weights; "
                    "no anchor or new reward term"))
            import rsl_rl.runners
            from b2w_core_stage3_audit import audit_core_stage3
            runner = rsl_rl.runners.OnPolicyRunner
            original_load = runner.load

            def checked_load(instance, path, load_optimizer=True):
                audit_core_stage3(instance.env.unwrapped.cfg, instance.cfg, PARENT_DIR,
                                  instance.run_path)
                return original_load(instance, path, load_optimizer)

            runner.load = checked_load
            import isaaclab_tasks.utils
            isaaclab_tasks.utils.get_checkpoint_path = lambda *args, **kwargs: str(PARENT)

    isaaclab.app.AppLauncher = LocalTrainingLauncher
    sys.path.insert(0, str(VENDOR_TRAIN.parent))
    sys.argv = [str(VENDOR_TRAIN), *sys.argv[1:], "--task", "B2W-24650-Core-Stage3-v0",
                "--resume", "--logger", "tensorboard", "--device", "cuda:0", "--seed", "9803",
                "--kit_args", project_kit_args()]
    print("VENDOR_TRAIN_ARGV=" + json.dumps(sys.argv), flush=True)
    try:
        runpy.run_path(str(VENDOR_TRAIN), run_name="__main__")
    except BaseException:
        traceback.print_exc()
        raise
    finally:
        for launcher in launched:
            if launcher.app.is_running():
                launcher.app.close()


if __name__ == "__main__":
    main()
