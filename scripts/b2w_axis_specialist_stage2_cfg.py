"""Cumulative-300 continuation config for one isolated axis."""
from pathlib import Path
import os

import b2w_axis_specialist_cfg as baseline
from axis_specialists_stage2_contract import load_spec
from run_support import write_json


SPEC = load_spec()
ARM = os.environ["B2W_AXIS_ARM"]


def env_config():
    cfg = baseline.env_config()
    cfg.seed = SPEC["training"]["seed"]
    return cfg


def agent_config():
    cfg = baseline.agent_config()
    training = SPEC["training"]
    cfg.seed = training["seed"]
    cfg.max_iterations = training["additional_updates_per_arm"]
    cfg.save_interval = training["save_interval"]
    cfg.experiment_name = f"b2w_axis_stage2_{ARM}_{cfg.seed}"
    cfg.run_name = os.environ.get("B2W_RESET_RUN_NAME", "axis_specialist_stage2")
    if os.environ.get("B2W_RESET_OUTPUT"):
        write_json(Path(os.environ["B2W_RESET_OUTPUT"]) / "axis_stage2_agent_audit.json", {
            "status": "passed", "arm": ARM, "seed": cfg.seed,
            "additional_updates": cfg.max_iterations,
            "parent_checkpoint_iteration": training["parent_checkpoint_iteration"],
            "final_checkpoint_iteration": training["final_checkpoint_iteration"],
            "learning_rate": cfg.algorithm.learning_rate,
            "num_learning_epochs": cfg.algorithm.num_learning_epochs,
            "num_mini_batches": cfg.algorithm.num_mini_batches,
            "schedule": cfg.algorithm.schedule,
        })
    return cfg
