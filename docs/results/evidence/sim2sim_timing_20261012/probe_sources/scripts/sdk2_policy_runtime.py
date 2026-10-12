"""Shared 57->16 offline/DDS actor and B2W LowCmd mapper; simulator only."""
from __future__ import annotations

import math
from pathlib import Path

import torch

from check_policy_contract import action_targets, make_observation, checked_vector
from evaluation_policy import validate_export
from run_support import read_json

POS_STOP = float(torch.tensor(2.146e9, dtype=torch.float32))
VEL_STOP = 16000.0


def disabled_motors():
    return [[0, POS_STOP, VEL_STOP, 0.0, 0.0, 0.0] for _ in range(20)]


def lowcmd_motors(targets, cfg):
    targets = checked_vector(targets, 16, "physical targets")
    result = disabled_motors()
    for i in range(16):
        result[i] = [1, float(targets[i]) if i < 12 else 0.0,
                     0.0 if i < 12 else float(targets[i]),
                     cfg["rl_kp"][i] if i < 12 else 0.0, cfg["rl_kd"][i], 0.0]
    return result


class PolicyRuntime:
    """Isaac training semantics: raw history and clipping of physical targets.

    Timing limits below are diagnostic simulator budgets, not hardware limits.
    The independent publisher must call guard between inference ticks.
    """
    def __init__(self, policy_path: Path, *, state_budget=.04, command_budget=.1,
                 target_budget=.06, inference_budget=.02):
        manifest = read_json(policy_path.with_name("manifest.json"))
        validate_export(24650, policy_path, manifest)
        self.cfg = manifest["contract"]
        if self.cfg["num_observations"] != 57 or self.cfg["num_of_dofs"] != 16:
            raise ValueError("ABI must remain 57->16")
        self.policy = torch.jit.load(str(policy_path), map_location="cpu").eval()
        self.state_budget = state_budget
        self.command_budget = command_budget
        self.target_budget = target_budget
        self.inference_budget = inference_budget
        self.reset()

    def reset(self):
        self.previous_action = torch.zeros(16)
        self.fault = None

    def latch(self, reason):
        if self.fault is None:
            self.fault = str(reason)

    def guard(self, state_age, command_age, target_age):
        for name, age, budget in (("stale_state", state_age, self.state_budget),
                                  ("stale_command", command_age, self.command_budget),
                                  ("expired_target", target_age, self.target_budget)):
            if not math.isfinite(age) or age < 0 or age > budget:
                self.latch(name)
        return self.fault is None

    def step(self, state, command, command_age=0.0):
        if not self.guard(state["age_s"], command_age, 0.0):
            raise ValueError(self.fault)
        try:
            if not state.get("crc_valid", True):
                raise ValueError("invalid_state_crc")
            checked_vector(command, 3, "commands")
            observation = make_observation(dict(state, commands=command,
                previous_action=self.previous_action), self.cfg,
                isaac_semantics=True, max_age_s=self.state_budget)
            with torch.inference_mode():
                raw = self.policy(observation[None]).squeeze(0)
            raw = checked_vector(raw, 16, "raw action")
            targets = action_targets(raw, self.cfg, isaac_semantics=True)
            motors = lowcmd_motors(targets, self.cfg)
        except (ValueError, RuntimeError) as error:
            self.latch(error)
            raise
        self.previous_action = raw.clone()
        return {"observation": observation.tolist(), "raw_action": raw.tolist(),
                "targets": targets.tolist(), "motors": motors}
