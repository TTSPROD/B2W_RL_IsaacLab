"""Evidence-driven 2x2 command-order/PPO-intensity task configuration."""
from __future__ import annotations

import os
from pathlib import Path
import torch

import b2w_schedule_pilot_cfg as baseline
from micro_sweep_contract import ARMS, load_spec
from run_support import write_json


SPEC = load_spec()
ARM = os.environ["B2W_MICRO_ARM"]
if ARM not in ARMS:
    raise ValueError("Unknown micro-sweep arm")
VARIANT = SPEC["variants"][ARM]


class CounterbalancedVelocityCommand(baseline.ScheduleVelocityCommand):
    """Flip complete Flat/Rough programs per cycle; preserve every magnitude/duration."""

    def __init__(self, cfg, env):
        self._counterbalance_ready = False
        super().__init__(cfg, env)
        self._cycle_sign = torch.ones(self.num_envs, device=self.device)
        target = self.target_masks["flat"] | self.target_masks["rough"]
        count = int(target.sum())
        initial = 2 * torch.randint(2, (count,), device=self.device) - 1
        self._cycle_sign[target] = initial.to(self._cycle_sign.dtype)
        self._counterbalance_ready = True

    def _resample_command(self, env_ids):
        super()._resample_command(env_ids)
        if not getattr(self, "_counterbalance_ready", False):
            return
        if isinstance(env_ids, slice):
            env_ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        for name in ("flat", "rough"):
            selected = env_ids[self.target_masks[name][env_ids]]
            if not len(selected):
                continue
            restart = self.rehearsal_phase[selected] == 0
            draws = (2 * torch.randint(2, (len(selected),), device=self.device) - 1).to(
                self._cycle_sign.dtype)
            self._cycle_sign[selected] = torch.where(restart, draws, self._cycle_sign[selected])
            self.vel_command_b[selected] *= self._cycle_sign[selected, None]


def env_config():
    cfg = baseline.env_config()
    if VARIANT["counterbalanced_sign_order"]:
        cfg.commands.base_velocity.class_type = CounterbalancedVelocityCommand
    cfg.seed = SPEC["stage1"]["seed"]
    return cfg


def agent_config():
    cfg = baseline.agent_config()
    stage = SPEC["stage1"]
    cfg.seed = stage["seed"]
    cfg.max_iterations = stage["updates"]
    cfg.save_interval = stage["updates"]
    cfg.experiment_name = f"b2w_micro_sweep_{ARM}_{stage['seed']}"
    cfg.run_name = os.environ.get("B2W_RESET_RUN_NAME", "micro_sweep")
    cfg.algorithm.schedule = SPEC["common"]["schedule"]
    cfg.algorithm.learning_rate = VARIANT["learning_rate"]
    cfg.algorithm.num_learning_epochs = VARIANT["num_learning_epochs"]
    cfg.algorithm.num_mini_batches = SPEC["common"]["num_mini_batches"]
    if os.environ.get("B2W_RESET_OUTPUT"):
        write_json(Path(os.environ["B2W_RESET_OUTPUT"]) / "agent_audit.json", {
            "status": "passed", "arm": ARM, "seed": cfg.seed,
            "counterbalanced_sign_order": VARIANT["counterbalanced_sign_order"],
            "learning_rate": cfg.algorithm.learning_rate,
            "num_learning_epochs": cfg.algorithm.num_learning_epochs,
            "num_mini_batches": cfg.algorithm.num_mini_batches,
            "schedule": cfg.algorithm.schedule,
        })
    return cfg
