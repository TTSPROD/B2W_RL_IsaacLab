"""Continue one axis specialist from its cumulative-150 checkpoint."""
import argparse
import os
from pathlib import Path
import runpy
import sys

from axis_specialists_stage2_contract import ARMS, load_spec
from b2w_runtime import configure_process, project_kit_args
from run_support import ROOT, managed_entrypoint, sha256, write_json


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, required=True)
    args = parser.parse_args()
    spec = load_spec()
    job = Path(os.environ["B2W_JOB_DIR"])
    output = job / "training" / args.arm
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(B2W_AXIS_ARM=args.arm, B2W_MICRO_ARM="standard_balanced",
                      B2W_RESET_ARM="upright", B2W_SCHEDULE_ARM="fixed",
                      B2W_RESET_MODE="axis_specialist_stage2", B2W_RESET_OUTPUT=str(output),
                      B2W_RESET_RUN_NAME=job.name, HYDRA_FULL_ERROR="1")
    configure_process()
    import torch
    import isaaclab.app
    from isaaclab.app import AppLauncher

    class LocalLauncher(AppLauncher):
        def __init__(self, *launcher_args, **launcher_kwargs):
            super().__init__(*launcher_args, **launcher_kwargs)
            from b2w_runtime import register_b2w_tasks
            register_b2w_tasks()
            import gymnasium as gym
            gym.register(id="B2W-Axis-Specialist-Stage2-v0",
                         entry_point="b2w_axis_specialist_stage2_env:AxisSpecialistStage2Env",
                         disable_env_checker=True,
                         kwargs={"env_cfg_entry_point": "b2w_axis_specialist_stage2_cfg:env_config",
                                 "rsl_rl_cfg_entry_point": "b2w_axis_specialist_stage2_cfg:agent_config"})
            from rsl_rl.runners import OnPolicyRunner
            import rsl_rl.algorithms.ppo as ppo_module
            paths = (Path(sys.modules[OnPolicyRunner.__module__].__file__), Path(ppo_module.__file__))
            write_json(output / "runtime_sources.json", {
                "standard_runner": True, "custom_runner_hooks": False,
                "source_sha256": {str(path): sha256(path) for path in paths},
                "runtime": {"gpu": torch.cuda.get_device_name(), "torch": torch.__version__},
            })

    isaaclab.app.AppLauncher = LocalLauncher
    training = spec["training"]
    train = ROOT / training["standard_train"]
    sys.path.insert(0, str(train.parent))
    sys.argv = [str(train), "--headless", "--task", "B2W-Axis-Specialist-Stage2-v0", "--resume",
                "--num_envs", str(training["num_envs"]),
                "--max_iterations", str(training["additional_updates_per_arm"]),
                "--seed", str(training["seed"]), "--load_run", "_parent",
                "--checkpoint", f"model_{training['parent_checkpoint_iteration']}.pt",
                "--device", "cuda:0", "--logger", "tensorboard",
                "--kit_args", project_kit_args()]
    runpy.run_path(str(train), run_name="__main__")


if __name__ == "__main__":
    main()
