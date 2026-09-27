"""23999 -> 24499: bounded rehearsal of the 43 measured regression rows."""
import hashlib
import json
from pathlib import Path

import torch

from b2w_recovery_cfg import RecoveryVelocityCommand, env_config as parent_env, agent_config as parent_agent
from b2w_regression500_sampling import RehearsalBank

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT/'configs/23999_rehearsal500_20260927.json'
PLAN_SHA = '1ea513deef4f9690e0d38d6c0e25c2dacc54b7437bdca535e6fdcbcb403f976c'
if hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() != PLAN_SHA:
    raise RuntimeError('Rehearsal plan checksum mismatch')
PLAN = json.loads(PLAN_PATH.read_text())
for key in ('basis_report', 'basis_summary'):
    if hashlib.sha256((ROOT/PLAN[key]).read_bytes()).hexdigest() != PLAN[key+'_sha256']:
        raise RuntimeError(f'Rehearsal evidence checksum mismatch: {key}')
TASK = 'B2W-23999-Regression-Rehearsal500-v0'


class RegressionVelocityCommand(RecoveryVelocityCommand):
    # Timed bank sampling does not have one global categorical mode probability.
    probabilities = ()
    training_profile = {**PLAN, 'plan_sha256': PLAN_SHA,
                        'sampling_probability_note': 'Use bank weights and cohort fractions; actual resamples are logged.',
                        'stair_exposure_limit': 'Assigned stair tile only; step coverage requires evaluation.'}

    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        ids = torch.arange(self.num_envs, device=self.device)
        self.rehearsal_cohort = (ids % 8 == 1) | (ids % 8 == 3)
        self.stop_cohort |= self.stairs & self.rehearsal_cohort
        self.rehearsal_case = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)
        self.rehearsal_phase = torch.full_like(self.rehearsal_case, -1)
        self.rehearsal_banks = {name: RehearsalBank(cases, self.device) for name, cases in PLAN['banks'].items()}
        self.training_profile = {**self.training_profile, 'cohort_envs': {
            'original_vendor': int(self.original_cohort.sum()),
            'parent_recovery': int((~self.original_cohort & ~self.rehearsal_cohort).sum()),
            'regression_rehearsal': int(self.rehearsal_cohort.sum()),
            'regression_stairs': int((self.rehearsal_cohort & self.stairs).sum())}}

    def _resample_command(self, env_ids):
        if isinstance(env_ids, slice):
            env_ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        regular_ids = env_ids[~self.rehearsal_cohort[env_ids]]
        if len(regular_ids):
            super()._resample_command(regular_ids)
        focused_ids = env_ids[self.rehearsal_cohort[env_ids]]
        for name, stairs in (('nonstairs', False), ('stairs', True)):
            selected = focused_ids[self.stairs[focused_ids] == stairs]
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
            self.zero_elapsed[selected], self.zero_good[selected] = 0., True
            self.resample_counts += torch.bincount(mode, minlength=len(self.mode_names))
            self.stair_stop_starts += ((mode == 0) & (phase > 0) & stairs).sum()


def env_config():
    cfg = parent_env()
    cfg.commands.base_velocity.class_type = RegressionVelocityCommand
    return cfg


def agent_config():
    cfg = parent_agent()
    cfg.seed = PLAN['seed']
    cfg.max_iterations = PLAN['additional_updates']
    cfg.save_interval = 100
    cfg.experiment_name = 'b2w_23999_rehearsal500_local'
    cfg.algorithm.learning_rate = PLAN['lr_cap']
    return cfg
