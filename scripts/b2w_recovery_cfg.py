"""21999 -> 23999: measured yaw/stair regressions, original command rehearsal."""
import torch

from robot_lab.tasks.manager_based.locomotion.velocity.mdp.commands import UniformThresholdVelocityCommand
from b2w_correction_cfg import track_moderate_yaw
from b2w_finetune_sampling import CORRECTION_MODE_NAMES, CORRECTION_PROBABILITIES
from b2w_recovery_sampling import sample_recovery_commands
from b2w_retention_cfg import RetentionVelocityCommand, env_config as retention_env
from b2w_finetune_cfg import agent_config as previous_agent

TASK = "B2W-21999-Yaw-Stair-Recovery-v0"


class RecoveryVelocityCommand(RetentionVelocityCommand):
    mode_names = CORRECTION_MODE_NAMES + ("original_vendor",)
    probabilities = tuple(p * 0.5 for p in CORRECTION_PROBABILITIES) + (0.5,)
    training_profile = {
        "basis_report": "docs/results/2026-09-27-fullcycle-21999-vs-19999.md",
        "original_cohort_fraction": 0.5,
        "direct_nonstair_probabilities": dict(zip(CORRECTION_MODE_NAMES, CORRECTION_PROBABILITIES)),
        "direct_stair_split": "half sustained traverse, half timed move/zero",
        "stair_traverse_seconds": [16, 24], "stair_before_zero_move_seconds": [8, 12],
        "stair_zero_seconds": [14, 18], "stair_vx_abs_range": [0.3, 0.7],
        "stair_direction": "independent balanced forward/backward draws",
        "terrain_geometry_and_difficulty": "unchanged from 21999 training",
        "stair_exposure_limit": "assigned tile only; physical step coverage is not established",
    }

    def _resample_command(self, env_ids):
        if isinstance(env_ids, slice):
            env_ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        original_ids = env_ids[self.original_cohort[env_ids]]
        direct_ids = env_ids[~self.original_cohort[env_ids]]
        if len(direct_ids):
            command, mode, duration, next_stop, stop = sample_recovery_commands(
                self.stairs[direct_ids], self.stop_cohort[direct_ids],
                self.next_stop[direct_ids], self.command_counter[direct_ids] == 0)
            self.vel_command_b[direct_ids] = command
            self.is_standing_env[direct_ids] = mode == 0
            self.is_heading_env[direct_ids] = False
            self.mode[direct_ids] = mode
            self.time_left[direct_ids] = duration
            self.next_stop[direct_ids] = next_stop
            self.zero_elapsed[direct_ids] = 0.0
            self.zero_good[direct_ids] = True
            self.resample_counts += torch.bincount(mode, minlength=len(self.mode_names))
            self.stair_stop_starts += stop.sum()
        if len(original_ids):
            UniformThresholdVelocityCommand._resample_command(self, original_ids)
            self.time_left[original_ids] = 10.0
            self.mode[original_ids] = len(self.mode_names) - 1
            self.zero_elapsed[original_ids] = 0.0
            self.zero_good[original_ids] = True
            self.resample_counts[-1] += len(original_ids)
            self.original_resamples += len(original_ids)


def env_config():
    cfg = retention_env()
    cfg.commands.base_velocity.class_type = RecoveryVelocityCommand
    # Reuse the bounded response correction measured in the 20500 -> 20600 run.
    # Reward weights, upright modulation, zero and large-yaw kernels are retained.
    cfg.rewards.track_ang_vel_z_exp.func = track_moderate_yaw
    cfg.rewards.track_ang_vel_z_exp.params["focused_std"] = 0.25
    return cfg


def agent_config():
    cfg = previous_agent()
    cfg.seed = 9703
    cfg.experiment_name = "b2w_21999_recovery2000_local"
    cfg.algorithm.learning_rate = 2.5e-5
    return cfg
