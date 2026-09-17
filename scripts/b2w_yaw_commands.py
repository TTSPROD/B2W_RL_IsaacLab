"""Project-local Flat command ablation; immutable upstream rewards/physics."""
import torch
from robot_lab.tasks.manager_based.locomotion.velocity.mdp.commands import UniformThresholdVelocityCommand
from yaw_command_sampling import apply_yaw_mix


class MeasuredYawVelocityCommand(UniformThresholdVelocityCommand):
    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        self.mix_generator = torch.Generator(device=self.device)
        self.mix_generator.manual_seed(int(env.cfg.seed) + 73001)
        self.distribution_counts = torch.zeros(6, dtype=torch.float64, device=self.device)

    def _resample_command(self, env_ids):
        super()._resample_command(env_ids)
        apply_yaw_mix(self.vel_command_b, self.is_heading_env, self.is_standing_env,
                      env_ids, self.cfg.pure_yaw_fraction, self.mix_generator)

    def _update_command(self):
        super()._update_command()
        c = self.vel_command_b
        zero_xy = (c[:, :2] == 0.).all(1)
        pure_yaw = zero_xy & (c[:, 2].abs() > .05)
        self.distribution_counts += torch.stack((
            c.new_tensor(self.num_envs), (c == 0.).all(1).sum(),
            pure_yaw.sum(), (pure_yaw & (c[:, 2] > 0.)).sum(),
            (pure_yaw & (c[:, 2] < 0.)).sum(), c[:, 2].abs().sum()))

    def distribution_snapshot(self):
        total, standing, pure, positive, negative, yaw = self.distribution_counts.tolist()
        if total == 0.:
            return {}
        return {"env_command_steps": int(total), "standing_fraction": standing / total,
                "pure_yaw_abs_gt_005_fraction": pure / total,
                "positive_pure_yaw_fraction": positive / total,
                "negative_pure_yaw_fraction": negative / total,
                "mean_abs_yaw_rad_s": yaw / total,
                "scope": "Cumulative commands after command-manager updates, including initial resets"}
