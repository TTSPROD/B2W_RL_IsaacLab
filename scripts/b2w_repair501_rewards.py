"""Bounded velocity rewards for exact zero; no pose or heading objective."""
import torch

from b2w_finetune_sampling import focused_yaw_tracking


def linear_tracking(command, velocity, gravity_z, std=.5, zero_std=.15):
    error = (command[:, :2]-velocity[:, :2]).square().sum(dim=1)
    original = torch.exp(-error/std**2)
    precise = torch.exp(-error/zero_std**2)
    zero = command.abs().amax(dim=1) < 1e-6
    return torch.where(zero, .5*(original+precise), original) * ((-gravity_z).clamp(0,.7)/.7)


def angular_tracking(command, velocity_z, gravity_z, std=.5, focused_std=.25, zero_std=.15):
    original = focused_yaw_tracking(command[:,2],velocity_z,gravity_z,std,focused_std)
    precise = torch.exp(-(command[:,2]-velocity_z).square()/zero_std**2) * ((-gravity_z).clamp(0,.7)/.7)
    return torch.where(command.abs().amax(dim=1)<1e-6,.5*(original+precise),original)


def track_linear(env, std, command_name, zero_std=.15):
    robot = env.scene['robot']
    return linear_tracking(env.command_manager.get_command(command_name),robot.data.root_lin_vel_b,
                           robot.data.projected_gravity_b[:,2],std,zero_std)


def track_angular(env, std, command_name, focused_std=.25, zero_std=.15):
    robot = env.scene['robot']
    return angular_tracking(env.command_manager.get_command(command_name),robot.data.root_ang_vel_b[:,2],
                            robot.data.projected_gravity_b[:,2],std,focused_std,zero_std)
