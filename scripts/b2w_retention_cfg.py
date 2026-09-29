"""Mixed original-distribution and direct-command continuation from upstream 19999."""
import torch

from isaaclab.managers import CurriculumTermCfg, TerminationTermCfg
from robot_lab.tasks.manager_based.locomotion.velocity.mdp.commands import UniformThresholdVelocityCommand

from b2w_finetune_cfg import FocusVelocityCommand, env_config as focus_env, agent_config

TASK = "B2W-19999-Retention-Fullcycle-v0"


class RetentionVelocityCommand(FocusVelocityCommand, UniformThresholdVelocityCommand):
    """Half of envs use the unchanged vendor command sampler and heading update."""

    mode_names = FocusVelocityCommand.mode_names + ("original_vendor",)
    probabilities = tuple(p * 0.5 for p in FocusVelocityCommand.probabilities) + (0.5,)

    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        ids = torch.arange(self.num_envs, device=self.device)
        self.original_cohort = ids % 2 == 0
        self.stop_cohort = self.stairs & (ids % 4 == 1)
        self.original_resamples = torch.zeros((), device=self.device)
        # Original cohort starts at upstream levels 0..5 and uses its curriculum.
        # Direct-command cohort covers every difficulty without demotion for stops.
        direct_ids = ids[~self.original_cohort]
        terrain = env.scene.terrain
        terrain.terrain_levels[direct_ids] = torch.randint(
            terrain.max_terrain_level, (len(direct_ids),), device=self.device)
        zeros = torch.zeros_like(direct_ids)
        terrain.update_env_origins(direct_ids, zeros, zeros)

    def _resample_command(self, env_ids):
        if isinstance(env_ids, slice):
            env_ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        original_ids = env_ids[self.original_cohort[env_ids]]
        direct_ids = env_ids[~self.original_cohort[env_ids]]
        if len(direct_ids):
            FocusVelocityCommand._resample_command(self, direct_ids)
        if len(original_ids):
            UniformThresholdVelocityCommand._resample_command(self, original_ids)
            self.time_left[original_ids] = 10.0
            self.mode[original_ids] = 6
            self.zero_elapsed[original_ids] = 0.0
            self.zero_good[original_ids] = True
            self.resample_counts[6] += len(original_ids)
            self.original_resamples += len(original_ids)

    def _update_command(self):
        # Original heading acts only on original_ids. Direct commands explicitly
        # set is_heading_env=False, including all long-zero / stair-stop samples.
        UniformThresholdVelocityCommand._update_command(self)


def cohort_timeout(env):
    command = env.command_manager.get_term("base_velocity")
    horizon_steps = torch.where(command.original_cohort, 20.0, 60.0) / env.step_dt
    return env.episode_length_buf >= horizon_steps


def retained_terrain_curriculum(env, env_ids):
    command = env.command_manager.get_term("base_velocity")
    ids = env_ids[command.original_cohort[env_ids]]
    terrain = env.scene.terrain
    robot = env.scene["robot"]
    distance = (robot.data.root_pos_w[ids, :2] - env.scene.env_origins[ids, :2]).norm(dim=1)
    move_up = distance > terrain.cfg.terrain_generator.size[0] / 2
    move_down = distance < command.command[ids, :2].norm(dim=1) * 20.0 * 0.5
    terrain.update_env_origins(ids, move_up, move_down & ~move_up)
    return terrain.terrain_levels.float().mean()


def env_config():
    from b2w_finetune_cfg import UnitreeB2WRoughEnvCfg, UnitreeB2WRoughPPORunnerCfg
    from b2w_training_audit import audit_upstream
    audit_upstream(UnitreeB2WRoughEnvCfg(), UnitreeB2WRoughPPORunnerCfg())
    cfg = focus_env()
    cmd = cfg.commands.base_velocity
    cmd.class_type = RetentionVelocityCommand
    cmd.heading_command = True
    cmd.ranges.heading = (-torch.pi, torch.pi)
    cmd.rel_heading_envs = 1.0
    cmd.rel_standing_envs = 0.02
    cmd.resampling_time_range = (10.0, 10.0)
    cfg.scene.terrain.max_init_terrain_level = 5
    cfg.curriculum.terrain_levels = CurriculumTermCfg(func=retained_terrain_curriculum)
    cfg.terminations.time_out = TerminationTermCfg(func=cohort_timeout, time_out=True)
    return cfg

