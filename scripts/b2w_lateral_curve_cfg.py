"""Dense-checkpoint continuation of the cumulative-150 lateral specialist."""
from pathlib import Path
import os

import b2w_axis_specialist_cfg as baseline
from lateral_curve_contract import load_spec
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
    cfg.experiment_name = f"b2w_lateral_curve_{cfg.seed}"
    cfg.run_name = os.environ.get("B2W_RESET_RUN_NAME", "lateral_curve")
    if os.environ.get("B2W_RESET_OUTPUT"):
        write_json(Path(os.environ["B2W_RESET_OUTPUT"]) / "lateral_curve_agent_audit.json", {
            "status": "passed", "seed": cfg.seed, "arm": "lateral",
            "additional_updates": cfg.max_iterations, "save_interval": cfg.save_interval,
            "learning_rate": cfg.algorithm.learning_rate,
            "num_learning_epochs": cfg.algorithm.num_learning_epochs,
            "num_mini_batches": cfg.algorithm.num_mini_batches,
            "schedule": cfg.algorithm.schedule,
        })
    return cfg
