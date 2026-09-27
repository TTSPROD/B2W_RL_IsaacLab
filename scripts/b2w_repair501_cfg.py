"""24499 -> 25000: full command coverage, precise zero and joint-limit repair."""
import hashlib
import json
from pathlib import Path

import torch

from b2w_recovery_cfg import RecoveryVelocityCommand, env_config as parent_env, agent_config as parent_agent
from b2w_regression500_sampling import RehearsalBank
from b2w_repair501_rewards import track_linear, track_angular

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT/'configs/24499_repair501_20260927.json'
PLAN_SHA = 'b528ada916c06f5979bbf7cf78e6cc5df47d155b29549e46ede43141ca748c9c'
if hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() != PLAN_SHA:
    raise RuntimeError('Repair plan checksum mismatch')
PLAN = json.loads(PLAN_PATH.read_text())
for key in ('basis_report','basis_summary'):
    if hashlib.sha256((ROOT/PLAN[key]).read_bytes()).hexdigest() != PLAN[key+'_sha256']:
        raise RuntimeError(f'Repair evidence checksum mismatch: {key}')
TASK = 'B2W-24499-Repair501-v0'


class RepairVelocityCommand(RecoveryVelocityCommand):
    probabilities = ()
    training_profile = {**PLAN,'plan_sha256':PLAN_SHA,
        'stair_exposure_limit':'Assigned stair tile only; physical coverage requires evaluation.',
        'sampling_probability_note':'Weights apply within banks; cohort fractions are environment counts.'}

    def __init__(self,cfg,env):
        super().__init__(cfg,env)
        ids = torch.arange(self.num_envs,device=self.device)
        self.rehearsal_cohort = (~self.original_cohort) & (self.stairs | (ids%8==1) | (ids%8==3))
        self.stop_cohort |= self.stairs & self.rehearsal_cohort
        self.rehearsal_case = torch.zeros(self.num_envs,dtype=torch.long,device=self.device)
        self.rehearsal_phase = torch.full_like(self.rehearsal_case,-1)
        self.rehearsal_banks = {name:RehearsalBank(cases,self.device) for name,cases in PLAN['banks'].items()}
        self.training_profile = {**self.training_profile,'cohort_envs':{
            'original_vendor':int(self.original_cohort.sum()),
            'parent_recovery':int((~self.original_cohort & ~self.rehearsal_cohort).sum()),
            'repair_rehearsal':int(self.rehearsal_cohort.sum()),
            'repair_stairs':int((self.rehearsal_cohort & self.stairs).sum())}}

    def _resample_command(self,env_ids):
        if isinstance(env_ids,slice):
            env_ids = torch.arange(self.num_envs,device=self.device)[env_ids]
        regular = env_ids[~self.rehearsal_cohort[env_ids]]
        if len(regular): super()._resample_command(regular)
        focused = env_ids[self.rehearsal_cohort[env_ids]]
        for name,stairs in (('nonstairs',False),('stairs',True)):
            selected = focused[self.stairs[focused]==stairs]
            if not len(selected): continue
            command,mode,duration,case,phase = self.rehearsal_banks[name].sample(
                self.rehearsal_case[selected],self.rehearsal_phase[selected],self.command_counter[selected]==0)
            self.rehearsal_case[selected],self.rehearsal_phase[selected] = case,phase
            self.vel_command_b[selected] = command
            self.is_standing_env[selected],self.is_heading_env[selected] = mode==0,False
            self.mode[selected],self.time_left[selected] = mode,duration
            self.zero_elapsed[selected],self.zero_good[selected] = 0.,True
            self.resample_counts += torch.bincount(mode,minlength=len(self.mode_names))
            self.stair_stop_starts += ((mode==0)&(phase>0)&stairs).sum()


def env_config():
    cfg = parent_env()
    cfg.commands.base_velocity.class_type = RepairVelocityCommand
    cfg.rewards.track_lin_vel_xy_exp.func = track_linear
    cfg.rewards.track_lin_vel_xy_exp.params['zero_std'] = .15
    cfg.rewards.track_ang_vel_z_exp.func = track_angular
    cfg.rewards.track_ang_vel_z_exp.params['zero_std'] = .15
    # Keep all 12 leg joints and their original soft-limit definition. This is a
    # cost increase, not a change to mass, actuator capacity or action clipping.
    cfg.rewards.joint_pos_limits.weight = -7.5
    return cfg


def agent_config():
    cfg = parent_agent()
    cfg.seed = PLAN['seed']
    cfg.max_iterations = PLAN['additional_updates']
    cfg.save_interval = 100
    cfg.experiment_name = 'b2w_24499_repair501_local'
    cfg.algorithm.learning_rate = PLAN['lr_cap']
    return cfg
