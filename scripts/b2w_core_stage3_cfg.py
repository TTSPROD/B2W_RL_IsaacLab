"""24650 stage 3: pure-axis exposure correction without reward changes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import torch
from isaaclab.managers import TerminationTermCfg
from isaaclab.terrains import MeshPlaneTerrainCfg
from robot_lab.tasks.manager_based.locomotion.velocity.mdp.commands import UniformThresholdVelocityCommand

from b2w_core_stage3_sampling import build_banks
from b2w_recovery_cfg import RecoveryVelocityCommand, env_config as parent_env, agent_config as parent_agent
from b2w_regression500_sampling import RehearsalBank

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "configs/24650_core_stage3_20260929.json"
PLAN_SHA = "13edfb0bb406ddcf254bc0f031894903e8625c6af70b6faeeef57df030dbc91c"
if hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() != PLAN_SHA:
    raise RuntimeError("Core stage-3 plan checksum mismatch")
PLAN = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
for key, sha_key in (("parent_checkpoint", "parent_sha256"),
                     ("parent_provenance", "parent_provenance_sha256"),
                     ("basis_report", "basis_report_sha256"),
                     ("basis_summary", "basis_summary_sha256")):
    if hashlib.sha256((ROOT / PLAN[key]).read_bytes()).hexdigest() != PLAN[sha_key]:
        raise RuntimeError(f"Core stage-3 evidence checksum mismatch: {key}")
PARENT_DIR = ROOT / "policies/local/core_24650"
for name, expected in (("env.yaml", PLAN["parent_env_sha256"]),
                       ("agent.yaml", PLAN["parent_agent_sha256"])):
    if hashlib.sha256((PARENT_DIR / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"Core stage-3 parent artifact mismatch: {name}")
BANKS = build_banks(PLAN)
TASK = "B2W-24650-Core-Stage3-v0"


class CoreStage3VelocityCommand(RecoveryVelocityCommand):
    plan = PLAN
    banks = BANKS
    probabilities = ()
    command_distribution_note = (
        "Terrain cohorts unchanged from selected 24650; only Flat/Rough within-cohort "
        "weights emphasize pure lateral and yaw commands."
    )
    retention_measures = (
        "35 percent retain the unchanged vendor terrain, command sampler and 20 s horizon",
        "terrain proportions, geometry and stair command banks are unchanged from selected 24650",
        "Flat/Rough pure lateral and yaw weights are the only behavioral sampling change",
        "all rewards, PPO terms, physics, robot and domain randomization remain unchanged",
    )
    training_profile = {
        **PLAN,
        "plan_sha256": PLAN_SHA,
        "sampling_probability_note": "Bank weights apply within fixed terrain-column cohorts.",
    }

    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        terrain_type = env.scene.terrain.terrain_types
        ranges = self.plan["terrain_columns"]

        def mask(name):
            low, high = ranges[name]
            return (terrain_type >= low) & (terrain_type < high)

        self.original_cohort = mask("retention")
        self.target_masks = {name: mask("target_" + name) for name in
                             ("flat", "rough", "stairs_up", "stairs_down")}
        target = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        for value in self.target_masks.values():
            target |= value
        if not torch.all(self.original_cohort ^ target):
            raise RuntimeError("Core stage-3 cohorts do not partition environments")
        self.rehearsal_cohort = target
        self.stairs = ((terrain_type < 6) | self.target_masks["stairs_up"]
                       | self.target_masks["stairs_down"])
        self.stop_cohort = self.target_masks["stairs_up"] | self.target_masks["stairs_down"]
        self.rehearsal_case = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)
        self.rehearsal_phase = torch.full_like(self.rehearsal_case, -1)
        self.rehearsal_banks = {name: RehearsalBank(cases, self.device)
                                for name, cases in self.banks.items()}

        direct_ids = target.nonzero(as_tuple=False).flatten()
        terrain = env.scene.terrain
        terrain.terrain_levels[direct_ids] = torch.randint(
            terrain.max_terrain_level, (len(direct_ids),), device=self.device)
        zeros = torch.zeros_like(direct_ids)
        terrain.update_env_origins(direct_ids, zeros, zeros)
        counts = {"retention": int(self.original_cohort.sum())}
        counts.update({name: int(value.sum()) for name, value in self.target_masks.items()})
        if any(value == 0 for value in counts.values()):
            raise RuntimeError(f"Empty core stage-3 cohort: {counts}")
        self.training_profile = {**self.training_profile, "cohort_envs": counts}

    def _resample_command(self, env_ids):
        if isinstance(env_ids, slice):
            env_ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        retained = env_ids[self.original_cohort[env_ids]]
        if len(retained):
            UniformThresholdVelocityCommand._resample_command(self, retained)
            self.time_left[retained] = 10.0
            self.mode[retained] = len(self.mode_names) - 1
            self.zero_elapsed[retained] = 0.0
            self.zero_good[retained] = True
            self.resample_counts[-1] += len(retained)
            self.original_resamples += len(retained)
        for name, cohort in self.target_masks.items():
            selected = env_ids[cohort[env_ids]]
            if not len(selected):
                continue
            command, mode, duration, case, phase = self.rehearsal_banks[name].sample(
                self.rehearsal_case[selected], self.rehearsal_phase[selected],
                self.command_counter[selected] == 0)
            self.rehearsal_case[selected], self.rehearsal_phase[selected] = case, phase
            self.vel_command_b[selected] = command
            self.is_standing_env[selected] = mode == 0
            self.is_heading_env[selected] = False
            self.mode[selected], self.time_left[selected] = mode, duration
            self.zero_elapsed[selected], self.zero_good[selected] = 0.0, True
            self.resample_counts += torch.bincount(mode, minlength=len(self.mode_names))
            if name.startswith("stairs"):
                self.stair_stop_starts += ((mode == 0) & (phase > 0)).sum()


def core_stage3_timeout(env):
    command = env.command_manager.get_term("base_velocity")
    horizon = torch.where(command.original_cohort, 20.0, 70.0) / env.step_dt
    return env.episode_length_buf >= horizon


def _configure_terrains(cfg):
    generator = cfg.scene.terrain.terrain_generator
    source = generator.sub_terrains
    proportions = PLAN["terrain_proportions"]
    target = PLAN["target_geometry"]
    names = {
        "retention_pyramid_stairs": "pyramid_stairs",
        "retention_pyramid_stairs_inv": "pyramid_stairs_inv",
        "retention_boxes": "boxes",
        "retention_random_rough": "random_rough",
        "retention_slope_up": "hf_pyramid_slope",
        "retention_slope_down": "hf_pyramid_slope_inv",
    }
    terrains = {}
    for destination, origin in names.items():
        terrains[destination] = deepcopy(source[origin])
        terrains[destination].proportion = proportions[destination]
    terrains["target_flat"] = MeshPlaneTerrainCfg(proportion=proportions["target_flat"])
    terrains["target_rough"] = deepcopy(source["random_rough"])
    terrains["target_rough"].proportion = proportions["target_rough"]
    terrains["target_rough"].noise_range = tuple(target["rough_noise_m"])
    terrains["target_rough"].noise_step = target["rough_noise_step_m"]
    terrains["target_stairs_up"] = deepcopy(source["pyramid_stairs_inv"])
    terrains["target_stairs_down"] = deepcopy(source["pyramid_stairs"])
    for name in ("target_stairs_up", "target_stairs_down"):
        terrains[name].proportion = proportions[name]
        terrains[name].step_height_range = tuple(target["stair_height_m"])
        terrains[name].step_width = target["stair_tread_m"]
        terrains[name].platform_width = target["stair_platform_m"]
    generator.sub_terrains = terrains
    generator.num_rows, generator.num_cols = 10, 40
    generator.curriculum = True


def env_config():
    cfg = parent_env()
    _configure_terrains(cfg)
    cfg.episode_length_s = 70.0
    cfg.commands.base_velocity.class_type = CoreStage3VelocityCommand
    cfg.terminations.time_out = TerminationTermCfg(func=core_stage3_timeout, time_out=True)
    return cfg


def agent_config():
    cfg = parent_agent()
    cfg.seed = PLAN["seed"]
    cfg.max_iterations = PLAN["additional_updates"]
    cfg.save_interval = PLAN["selection"]["checkpoint_interval"]
    cfg.experiment_name = "b2w_24650_core_stage3_local"
    cfg.algorithm.learning_rate = PLAN["lr_cap"]
    return cfg
