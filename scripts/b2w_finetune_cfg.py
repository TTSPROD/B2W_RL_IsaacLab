"""19999 continuation settings; imported only after SimulationApp starts."""
import torch
from isaaclab.envs.mdp.commands import UniformVelocityCommand
from isaaclab.terrains import MeshPlaneTerrainCfg
from robot_lab.tasks.manager_based.locomotion.velocity.config.wheeled.unitree_b2w.rough_env_cfg import UnitreeB2WRoughEnvCfg
from robot_lab.tasks.manager_based.locomotion.velocity.config.wheeled.unitree_b2w.agents.rsl_rl_ppo_cfg import UnitreeB2WRoughPPORunnerCfg

from b2w_finetune_sampling import MODE_NAMES, PROBABILITIES, sample_commands
from local_b2w_assets import configure_b2w_env

TASK = "B2W-19999-Commands-Stairs-Finetune-v0"


class FocusVelocityCommand(UniformVelocityCommand):
    """Direct body-frame commands, including timed move/stop pairs on stairs."""

    mode_names = MODE_NAMES
    probabilities = PROBABILITIES
    correction = False

    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        self.mode = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)
        self.zero_elapsed = torch.zeros(self.num_envs, device=self.device)
        self.zero_good = torch.ones(self.num_envs, dtype=torch.bool, device=self.device)
        self.zero_windows = torch.zeros((), device=self.device)
        self.zero_passes = torch.zeros((), device=self.device)
        self.stair_zero_windows = torch.zeros((), device=self.device)
        self.stair_zero_passes = torch.zeros((), device=self.device)
        self.stair_stop_starts = torch.zeros((), device=self.device)
        self.resample_counts = torch.zeros(len(self.mode_names), device=self.device)
        # The first six of twenty columns are the two original stair families.
        self.stairs = env.scene.terrain.terrain_types < 6
        # Half the stair environments rehearse short traverse -> long zero.
        self.stop_cohort = self.stairs & (torch.arange(self.num_envs, device=self.device) % 2 == 0)
        self.next_stop = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)

    def _resample_command(self, env_ids):
        if isinstance(env_ids, slice):
            env_ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        command, mode, duration = sample_commands(len(env_ids), self.device,
                                                 correction=self.correction)
        fresh = self.command_counter[env_ids] == 0
        cohort = self.stop_cohort[env_ids]
        stop = cohort & self.next_stop[env_ids] & ~fresh
        move = cohort & ~stop
        speed = torch.empty(len(env_ids), device=self.device).uniform_(0.3, 0.7)
        speed *= 2 * torch.randint(2, (len(env_ids),), device=self.device) - 1
        command[cohort] = 0.0
        command[:, 0] = torch.where(move, speed, command[:, 0])
        mode = torch.where(stop, 0, torch.where(move, 2, mode))
        duration = torch.where(move, torch.empty_like(duration).uniform_(3.0, 6.0), duration)
        duration = torch.where(stop, torch.empty_like(duration).uniform_(14.0, 18.0), duration)
        self.next_stop[env_ids] = move
        self.vel_command_b[env_ids] = command
        self.is_standing_env[env_ids] = mode == 0
        self.is_heading_env[env_ids] = False
        self.mode[env_ids] = mode
        self.time_left[env_ids] = duration
        self.zero_elapsed[env_ids] = 0.0
        self.zero_good[env_ids] = True
        self.resample_counts += torch.bincount(mode, minlength=len(self.mode_names))
        self.stair_stop_starts += (stop & ~fresh).sum()

    def _update_metrics(self):
        super()._update_metrics()
        # Training diagnostics, with exploration/noise/DR; not an acceptance test.
        zero = self.is_standing_env
        before = self.zero_elapsed.clone()
        self.zero_elapsed += zero * self._env.step_dt
        settled = zero & (self.zero_elapsed > 2.0)
        good = ((self.robot.data.root_lin_vel_b[:, :2].norm(dim=1) <= 0.1)
                & (self.robot.data.root_ang_vel_b[:, 2].abs() <= 0.1))
        self.zero_good &= ~settled | good
        complete = zero & (before < 12.0) & (self.zero_elapsed >= 12.0)
        self.zero_windows += complete.sum()
        self.zero_passes += (complete & self.zero_good).sum()
        self.stair_zero_windows += (complete & self.stairs).sum()
        self.stair_zero_passes += (complete & self.stairs & self.zero_good).sum()


def env_config():
    cfg = UnitreeB2WRoughEnvCfg()
    configure_b2w_env(cfg)
    cfg.episode_length_s = 60.0
    cmd = cfg.commands.base_velocity
    cmd.class_type = FocusVelocityCommand
    cmd.heading_command = False
    cmd.ranges.heading = None
    cmd.rel_heading_envs = 0.0
    cmd.rel_standing_envs = 0.2
    cmd.resampling_time_range = (8.0, 30.0)
    terrain = cfg.scene.terrain.terrain_generator
    # Keep every upstream family and its relative share, add 25% flat rehearsal.
    for sub in terrain.sub_terrains.values():
        sub.proportion *= 0.75
    terrain.sub_terrains["flat_rehearsal"] = MeshPlaneTerrainCfg(proportion=0.25)
    terrain.num_rows, terrain.num_cols = 10, 20
    terrain.curriculum = True  # stratified generation, all original difficulty rows
    cfg.scene.terrain.max_init_terrain_level = 9
    # Distance-based promotion/demotion would punish deliberate long stops.
    cfg.curriculum.terrain_levels = None
    return cfg


def agent_config():
    cfg = UnitreeB2WRoughPPORunnerCfg()
    cfg.device = "cuda:0"
    cfg.seed = 9701
    cfg.max_iterations = 2000
    cfg.save_interval = 100
    cfg.experiment_name = "b2w_19999_fullcycle2000_local"
    cfg.algorithm.learning_rate = 5e-5
    cfg.algorithm.desired_kl = 0.005
    cfg.algorithm.clip_param = 0.1
    cfg.algorithm.entropy_coef = 0.005
    return cfg

