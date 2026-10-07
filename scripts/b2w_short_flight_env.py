"""Versioned F1 training environment: straight short flight exposure/crossed.

The common safety terminals, exclusive timeouts, StairMonitor promotion-by-real-
success and exact restore are reused from b2w_curriculum_env/CoreStage3.
Only the stair exposure/crossed observer is replaced: it measures the straight
flight band (first edge .. last edge, crossing past last edge + 0.5 m) exactly as
the v2 evaluation protocol does, using wheel support/contact on the march.
"""
from __future__ import annotations

import torch
from b2w_curriculum_env import CurriculumEnv, safety_terminal, safe_timeout, safe_bounds, stair_curriculum
from b2w_short_flight_terrain import flight_geometry

WHEEL_RADIUS_M = 0.0875


def geometry_tensors(levels, plan, device):
    """Per-env flight geometry from terrain_levels: (steps, height, first, last)."""
    frac = levels.clamp(0, 9) / 9.0
    g = plan["target_geometry"]
    steps = (g["flight_min_steps"] + frac * (g["flight_max_steps"] - g["flight_min_steps"])).round().long()
    height = g["flight_height_m"][0] + frac * (g["flight_height_m"][1] - g["flight_height_m"][0])
    first = torch.full_like(frac, float(g["flight_first_edge_m"]))
    last = first + (steps - 1) * float(g["flight_tread_m"])
    return steps, height, first, last


class ShortFlightEnv(CurriculumEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.command = self.command_manager.get_term('base_velocity')
        self.plan = self.command.plan
        self.target_stairs = self.command.target_masks["stairs_up"] | self.command.target_masks["stairs_down"]
        # Replace the pyramid exposure observer with the straight-flight observer.
        base_compute = type(self.reward_manager).compute

        def observed_reward(dt):
            reward = base_compute(self.reward_manager, dt)
            exposure, crossed = self.flight_exposure_crossed()
            velocity = torch.cat((self.robot.data.root_lin_vel_b[:, :2], self.robot.data.root_ang_vel_b[:, 2:3]), dim=1)
            self.monitor.record(reward, velocity, exposure, crossed)
            return reward

        self.reward_manager.compute = observed_reward

    def flight_exposure_crossed(self):
        terrain = self.scene.terrain
        levels = terrain.terrain_levels
        steps, height, first, last = geometry_tensors(levels, self.plan, self.device)
        origin_x = self.scene.env_origins[:, 0]
        root_x = self.robot.data.root_pos_w[:, 0] - origin_x
        wheel_x = self.robot.data.body_pos_w[:, self.wheel_ids, 0] - origin_x[:, None]
        loaded = self.contact.data.net_forces_w[:, self.wheel_contact_ids, 2] > 5.0
        # Mirror core_locomotion_protocol.stair_exposure (wheel support on the march).
        start = torch.where(self.command.target_masks["stairs_down"], height * steps, torch.zeros_like(height))
        direction = torch.where(self.command.target_masks["stairs_down"], -1.0, 1.0)
        riser = ((wheel_x - first[:, None]) / self.plan["target_geometry"]["flight_tread_m"]).floor().clamp(0, steps[:, None] - 1) + 1
        surface = start[:, None] + direction[:, None] * height[:, None] * riser
        del surface  # band loaded wheels are on the march regardless of z depth; support defined below
        support = loaded & (wheel_x >= first[:, None]) & (wheel_x < last[:, None])
        on_flight = (root_x >= first) & (root_x < last)
        exposure = on_flight & (support.sum(dim=1) >= 1)
        crossed = (root_x > last + 0.5)
        return exposure, crossed


def install_coverage(env):
    return env.monitor


# Reuse the frozen CurriculumEnv preflight (physics-tick safety, exclusive
# timeouts, boundary test, safety_preflight.json) unchanged; ShortFlightEnv
# shares the same monitor/termination API.
from b2w_curriculum_env import preflight  # noqa: E402

