"""One bounded 100-update correction from measured checkpoint 20500."""
from b2w_finetune_cfg import FocusVelocityCommand, agent_config as original_agent, env_config as original_env
from b2w_finetune_sampling import CORRECTION_MODE_NAMES, CORRECTION_PROBABILITIES, focused_yaw_tracking

TASK = "B2W-20500-Yaw-Response-Correction-v0"


class CorrectedVelocityCommand(FocusVelocityCommand):
    mode_names = CORRECTION_MODE_NAMES
    probabilities = CORRECTION_PROBABILITIES
    correction = True


def track_moderate_yaw(env, std, command_name, focused_std=0.25):
    robot = env.scene["robot"]
    return focused_yaw_tracking(env.command_manager.get_command(command_name)[:, 2],
                                robot.data.root_ang_vel_b[:, 2], robot.data.projected_gravity_b[:, 2],
                                std=std, focused_std=focused_std)


def env_config():
    cfg = original_env()
    cfg.commands.base_velocity.class_type = CorrectedVelocityCommand
    cfg.commands.base_velocity.rel_standing_envs = CORRECTION_PROBABILITIES[0]
    # Same reward weight/range and upright modulation. Only the error kernel
    # for abs(nonzero yaw) in [0.2, 0.6] narrows from 0.5 to 0.25 rad/s.
    cfg.rewards.track_ang_vel_z_exp.func = track_moderate_yaw
    cfg.rewards.track_ang_vel_z_exp.params["focused_std"] = 0.25
    return cfg


def agent_config():
    cfg = original_agent()
    cfg.seed = 9602
    cfg.max_iterations = 100
    cfg.save_interval = 25
    cfg.experiment_name = "b2w_20500_yaw_response_correction100"
    cfg.algorithm.learning_rate = 2.5e-5
    return cfg
