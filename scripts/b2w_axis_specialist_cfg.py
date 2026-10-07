"""Axis-specific Flat/Rough bank on the standard balanced training task."""
from copy import deepcopy
from pathlib import Path
import os

import b2w_micro_sweep_cfg as baseline
from axis_specialists_contract import ARMS, load_spec
from b2w_core_stage3_sampling import build_banks
from run_support import write_json


SPEC = load_spec()
ARM = os.environ["B2W_AXIS_ARM"]
if ARM not in ARMS:
    raise ValueError("Unknown axis-specialist arm")
AXIS = SPEC["axis_sampling"][ARM]
AXIS_PLAN = deepcopy(baseline.CounterbalancedVelocityCommand.plan)
for cohort in ("flat", "rough"):
    AXIS_PLAN["banks"][cohort] = [{"case": AXIS["case"], "weight": 1.0,
                                    "axis": AXIS["axis"]}]


class AxisVelocityCommand(baseline.CounterbalancedVelocityCommand):
    plan = AXIS_PLAN
    banks = build_banks(AXIS_PLAN)
    training_profile = {**AXIS_PLAN, "arm": "fixed", "axis_arm": ARM, "axis_specialist": True,
                        "target_axis": AXIS["axis"], "adaptive": False}


def env_config():
    cfg = baseline.env_config()
    cfg.commands.base_velocity.class_type = AxisVelocityCommand
    cfg.seed = SPEC["training"]["seed"]
    return cfg


def agent_config():
    cfg = baseline.agent_config()
    training = SPEC["training"]
    cfg.seed = training["seed"]
    cfg.max_iterations = training["updates_per_arm"]
    cfg.save_interval = training["save_interval"]
    cfg.experiment_name = f"b2w_axis_{ARM}_{cfg.seed}"
    cfg.run_name = os.environ.get("B2W_RESET_RUN_NAME", "axis_specialist")
    cfg.algorithm.schedule = training["schedule"]
    cfg.algorithm.learning_rate = training["learning_rate"]
    cfg.algorithm.num_learning_epochs = training["num_learning_epochs"]
    cfg.algorithm.num_mini_batches = training["num_mini_batches"]
    if os.environ.get("B2W_RESET_OUTPUT"):
        write_json(Path(os.environ["B2W_RESET_OUTPUT"]) / "axis_agent_audit.json", {
            "status": "passed", "arm": ARM, "axis": AXIS["axis"], "seed": cfg.seed,
            "max_iterations": cfg.max_iterations, "save_interval": cfg.save_interval,
            "counterbalanced_sign_order": True,
            "learning_rate": cfg.algorithm.learning_rate,
            "num_learning_epochs": cfg.algorithm.num_learning_epochs,
            "num_mini_batches": cfg.algorithm.num_mini_batches,
            "schedule": cfg.algorithm.schedule,
        })
    return cfg
