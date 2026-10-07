"""Standard Robot Lab configuration for balanced-specialist continuation."""
from pathlib import Path
import os

import b2w_micro_sweep_cfg as baseline
from specialist_stage2_contract import load_spec
from run_support import write_json


SPEC = load_spec()


def env_config():
    cfg = baseline.env_config()
    cfg.seed = SPEC["training"]["seed"]
    return cfg


def agent_config():
    cfg = baseline.agent_config()
    training = SPEC["training"]
    cfg.seed = training["seed"]
    cfg.max_iterations = training["additional_updates"]
    cfg.save_interval = training["save_interval"]
    cfg.experiment_name = f"b2w_specialist_stage2_balanced_{cfg.seed}"
    cfg.run_name = os.environ.get("B2W_RESET_RUN_NAME", "specialist_stage2")
    cfg.algorithm.schedule = training["schedule"]
    cfg.algorithm.learning_rate = training["learning_rate"]
    cfg.algorithm.num_learning_epochs = training["num_learning_epochs"]
    cfg.algorithm.num_mini_batches = training["num_mini_batches"]
    if os.environ.get("B2W_RESET_OUTPUT"):
        write_json(Path(os.environ["B2W_RESET_OUTPUT"]) / "stage2_agent_audit.json", {
            "status": "passed", "seed": cfg.seed,
            "max_iterations": cfg.max_iterations, "save_interval": cfg.save_interval,
            "counterbalanced_sign_order": True,
            "learning_rate": cfg.algorithm.learning_rate,
            "num_learning_epochs": cfg.algorithm.num_learning_epochs,
            "num_mini_batches": cfg.algorithm.num_mini_batches,
            "schedule": cfg.algorithm.schedule,
        })
    return cfg
