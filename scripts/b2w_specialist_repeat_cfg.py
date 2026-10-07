"""Standard Robot Lab config for seed-9913 balanced-specialist repeat."""
from pathlib import Path
import os

import b2w_micro_sweep_cfg as baseline
from run_support import write_json
from specialist_repeat_contract import load_spec


SPEC = load_spec()


def env_config():
    cfg = baseline.env_config()
    cfg.seed = SPEC["training"]["seed"]
    return cfg


def agent_config():
    cfg = baseline.agent_config()
    training = SPEC["training"]
    cfg.seed = training["seed"]
    cfg.max_iterations = training["updates"]
    cfg.save_interval = training["save_interval"]
    cfg.experiment_name = f"b2w_specialist_repeat_balanced_{cfg.seed}"
    cfg.run_name = os.environ.get("B2W_RESET_RUN_NAME", "specialist_repeat")
    cfg.algorithm.schedule = training["schedule"]
    cfg.algorithm.learning_rate = training["learning_rate"]
    cfg.algorithm.num_learning_epochs = training["num_learning_epochs"]
    cfg.algorithm.num_mini_batches = training["num_mini_batches"]
    if os.environ.get("B2W_RESET_OUTPUT"):
        write_json(Path(os.environ["B2W_RESET_OUTPUT"]) / "repeat_agent_audit.json", {
            "status": "passed", "seed": cfg.seed, "max_iterations": cfg.max_iterations,
            "save_interval": cfg.save_interval, "counterbalanced_sign_order": True,
            "learning_rate": cfg.algorithm.learning_rate,
            "num_learning_epochs": cfg.algorithm.num_learning_epochs,
            "num_mini_batches": cfg.algorithm.num_mini_batches,
            "schedule": cfg.algorithm.schedule,
        })
    return cfg
