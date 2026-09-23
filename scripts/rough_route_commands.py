"""Opt-in feasible Rough command/reset distribution; no actor or evaluator changes.

Rough routes use time and sampled commands only. There is no position, heading,
terrain-height, or goal feedback to the actor. Flat tiles keep native commands,
reset ranges and 20-second timeouts. Importing this module requires no Isaac app.
"""
from __future__ import annotations

import math
import torch

VERSION = 'rough_route_v1'
KINDS = ('traverse', 'stand', 'turn')


def route_specification():
    return dict(version=VERSION, rough_terrain_columns=list(range(3, 10)),
                probabilities=dict(zip(KINDS, (.6, .2, .2))),
                settle_seconds=2., approach_seconds=12., episode_seconds=22.,
                traverse_vx=[.20, .24], approach_vx=.30, turn_abs_yaw=[.20, .30],
                rough_vy=0., heading_feedback=False, flat_episode_seconds=20.,
                flat_command_sampler='MeasuredYawVelocityCommand, unchanged ranges and pure-yaw mix',
                rough_reset=dict(x=[0., 0.], y=[-.1, .1], z=[0., 0.],
                                 yaw=[-.025, .025], roll_pitch='preserve configured upright ranges',
                                 all_root_velocities=0.),
                scope='Training task-distribution bundle; frozen evaluation cases/gates unchanged')


def rough_mask(env):
    columns = env.scene.terrain.terrain_types
    if bool(((columns < 0) | (columns > 9)).any()):
        raise ValueError('Route commands require the frozen ten-column training terrain')
    return columns >= 3


def _ids(env, env_ids):
    all_ids = torch.arange(env.num_envs, device=env.device)
    return all_ids if env_ids is None else all_ids[env_ids]


def sampled_routes(draws):
    """Independent U[0,1) draws: kind, speed, turn magnitude, turn sign."""
    if draws.ndim != 2 or draws.shape[1] != 4:
        raise ValueError('Expected four independent route draws per environment')
    kind = (draws[:, 0] >= .6).long() + (draws[:, 0] >= .8).long()
    speed = torch.where(kind == 0, .20 + .04 * draws[:, 1], .30)
    turn = torch.where(draws[:, 3] < .5, -1., 1.) * (.20 + .10 * draws[:, 2])
    return kind, speed, turn


def apply_route_schedule(commands, mask, kind, speed, turn, episode_steps, step_dt):
    """Write only Rough commands; integer boundaries avoid floating-point phase drift."""
    settle_steps = round(2. / step_dt)
    approach_end = round(14. / step_dt)
    active = episode_steps >= settle_steps
    approach = episode_steps < approach_end
    commands[mask] = 0.
    forward = mask & active & ((kind == 0) | approach)
    turning = mask & active & ~approach & (kind == 2)
    commands[forward, 0] = speed[forward]
    commands[turning, 2] = turn[turning]


def _command_counts(commands):
    pure = (commands[:, :2] == 0.).all(1) & (commands[:, 2].abs() > .05)
    return torch.stack((commands.new_tensor(len(commands)), (commands == 0.).all(1).sum(),
                        pure.sum(), (pure & (commands[:, 2] > 0.)).sum(),
                        (pure & (commands[:, 2] < 0.)).sum(), commands[:, 2].abs().sum()))


def get_route_command_class():
    """Delay Isaac imports until AppLauncher initialized the native runtime."""
    if 'RouteVelocityCommand' in globals():
        return globals()['RouteVelocityCommand']
    from b2w_yaw_commands import MeasuredYawVelocityCommand

    class RouteVelocityCommand(MeasuredYawVelocityCommand):
        def __init__(self, cfg, env):
            super().__init__(cfg, env)
            self.route_mask = rough_mask(env)
            self.route_generator = torch.Generator(device=self.device)
            self.route_generator.manual_seed(int(env.cfg.seed) + 93001)
            self.route_kind = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)
            self.route_speed = torch.zeros(self.num_envs, device=self.device)
            self.route_turn = torch.zeros(self.num_envs, device=self.device)
            self.route_resamples = torch.zeros(3, dtype=torch.long, device=self.device)
            self.route_phase_steps = torch.zeros(5, dtype=torch.long, device=self.device)

        def _resample_command(self, env_ids):
            ids = _ids(self._env, env_ids)
            flat = ids[~self.route_mask[ids]]
            route = ids[self.route_mask[ids]]
            if len(flat):
                super()._resample_command(flat)
            if len(route):
                draws = torch.rand((len(route), 4), device=self.device, generator=self.route_generator)
                kind, speed, turn = sampled_routes(draws)
                self.route_kind[route], self.route_speed[route], self.route_turn[route] = kind, speed, turn
                self.route_resamples += torch.bincount(kind, minlength=3)
                self.is_heading_env[route] = False
                self.is_standing_env[route] = False
                # Native reset calls this before zeroing episode_length_buf. Always settle.
                self.vel_command_b[route] = 0.
                # Keep one route per episode; native Flat still resamples every ten seconds.
                self.time_left[route] = 22. + self._env.step_dt

        def _update_command(self):
            before = self.distribution_counts.clone()
            super()._update_command()
            steps = self._env.episode_length_buf
            apply_route_schedule(self.vel_command_b, self.route_mask, self.route_kind,
                                 self.route_speed, self.route_turn, steps, self._env.step_dt)
            # The inherited implementation counts before our override. Replace that
            # increment with the final command actually returned to the actor.
            self.distribution_counts.copy_(before + _command_counts(self.vel_command_b))
            active = steps >= round(2. / self._env.step_dt)
            approach = steps < round(14. / self._env.step_dt)
            phases = (~active, active & (self.route_kind == 0),
                      active & approach & (self.route_kind != 0),
                      active & ~approach & (self.route_kind == 1),
                      active & ~approach & (self.route_kind == 2))
            self.route_phase_steps += torch.stack([(self.route_mask & p).sum() for p in phases])

        def distribution_snapshot(self):
            result = super().distribution_snapshot()
            result['rough_route'] = dict(specification=route_specification(),
                sampled_episode_kinds=dict(zip(KINDS, self.route_resamples.tolist())),
                actual_command_phase_steps=dict(zip(('settle', 'traverse', 'approach', 'stand', 'turn'),
                                                     self.route_phase_steps.tolist())))
            return result

    # Keep the native class importable by config serializers once configured.
    RouteVelocityCommand.__qualname__ = 'RouteVelocityCommand'
    globals()['RouteVelocityCommand'] = RouteVelocityCommand
    return RouteVelocityCommand


def route_reset_root_state(env, env_ids, pose_range, velocity_range, asset_cfg=None):
    """Native reset split by terrain family, retaining all original Flat ranges."""
    from robot_lab.tasks.manager_based.locomotion.velocity import mdp
    ids = _ids(env, env_ids)
    kwargs = {} if asset_cfg is None else dict(asset_cfg=asset_cfg)
    mask = rough_mask(env)
    flat, route = ids[~mask[ids]], ids[mask[ids]]
    if len(flat):
        mdp.reset_root_state_uniform(env, flat, pose_range=pose_range, velocity_range=velocity_range, **kwargs)
    if len(route):
        route_pose = dict(pose_range, x=(0., 0.), y=(-.1, .1), z=(0., 0.), yaw=(-.025, .025))
        zero_velocity = {name: (0., 0.) for name in ('x', 'y', 'z', 'roll', 'pitch', 'yaw')}
        mdp.reset_root_state_uniform(env, route, pose_range=route_pose, velocity_range=zero_velocity, **kwargs)


def route_time_out(env):
    """Rough22/Flat20 seconds; preserve the native >= timeout convention."""
    limits = torch.where(rough_mask(env), math.ceil(22. / env.step_dt), math.ceil(20. / env.step_dt))
    return env.episode_length_buf >= limits


def configure_route_commands(cfg):
    if getattr(cfg.commands.base_velocity, 'route_distribution_version', None):
        raise ValueError('Route distribution already configured')
    generator = cfg.scene.terrain.terrain_generator
    if generator.num_cols != 10 or tuple(generator.sub_terrains) != ('flat', 'random', 'slope_up', 'slope_down', 'blocks'):
        raise ValueError('Route distribution is only valid for the frozen mixed training terrain')
    cfg.commands.base_velocity.class_type = get_route_command_class()
    cfg.commands.base_velocity.route_distribution_version = VERSION
    cfg.events.randomize_reset_base.func = route_reset_root_state
    cfg.episode_length_s = 22.
    cfg.terminations.time_out.func = route_time_out


def validate_route_fixture(env):
    """64-env native manager/reset fixture; no claim of route/policy acceptance.

    Uses actual native reset and command-manager compute at every phase boundary,
    plus a partial reset. Physics remains covered by the separate train/resume smoke.
    All injected counters and route kinds are discarded by a final native reset.
    """
    base = env.unwrapped
    if base.num_envs != 64:
        raise ValueError('Route fixture is restricted to discarded 64-env smoke')
    term = base.command_manager.get_term('base_velocity')
    if not isinstance(term, get_route_command_class()):
        raise ValueError('Route fixture requires the opt-in command class')
    records = []
    with torch.inference_mode():
        env.reset()
        mask = term.route_mask
        route_ids = mask.nonzero().flatten()
        flat_ids = (~mask).nonzero().flatten()
        if len(route_ids) < 3 or not len(flat_ids):
            raise ValueError('Fixture needs both Flat and three Rough routes')
        robot = base.scene['robot']
        state = robot.data.root_state_w
        relative = state[:, :3] - base.scene.env_origins - robot.data.default_root_state[:, :3]
        q = state[:, 3:7]
        yaw = torch.atan2(2 * (q[:, 0] * q[:, 3] + q[:, 1] * q[:, 2]),
                          1 - 2 * (q[:, 2].square() + q[:, 3].square()))
        if (float(relative[mask, 0].abs().max()) > 1e-5 or float(relative[mask, 1].abs().max()) > .10001
                or float(relative[mask, 2].abs().max()) > 1e-5 or float(yaw[mask].abs().max()) > .02501
                or float(state[mask, 7:].abs().max()) > 1e-7):
            raise ValueError('Realized native Rough reset is outside registered bounds')
        reset_evidence = dict(rough_envs=len(route_ids), flat_envs=len(flat_ids),
            rough_max_abs_x_m=float(relative[mask, 0].abs().max()),
            rough_max_abs_y_m=float(relative[mask, 1].abs().max()),
            rough_max_abs_yaw_rad=float(yaw[mask].abs().max()),
            rough_max_abs_root_velocity=float(state[mask, 7:].abs().max()))
        base.command_manager.compute(dt=base.step_dt)
        chosen = route_ids[:3]
        term.route_kind[chosen] = torch.arange(3, device=base.device)
        term.route_speed[chosen] = term.route_speed.new_tensor([.22, .30, .30])
        term.route_turn[chosen] = term.route_turn.new_tensor([.25, .25, -.25])
        for step in (0, 99, 100, 699, 700, 1099):
            base.episode_length_buf[:] = step
            flat_before = term.vel_command_b[flat_ids].clone()
            base.command_manager.compute(dt=base.step_dt)
            expected = term.vel_command_b.new_tensor(
                [[0., 0., 0.]] * 3 if step < 100 else
                [[.22, 0., 0.], [.30, 0., 0.], [.30, 0., 0.]] if step < 700 else
                [[.22, 0., 0.], [0., 0., 0.], [0., 0., -.25]])
            if not torch.allclose(term.vel_command_b[chosen], expected, atol=1e-7, rtol=0.):
                raise ValueError('Native command manager produced incorrect route phase')
            if not torch.equal(term.vel_command_b[flat_ids], flat_before):
                raise ValueError('Route override changed stable native Flat commands')
            records.append(dict(episode_step=step, commands=term.vel_command_b[chosen].tolist()))
        for step, expected_flat, expected_rough in ((999, False, False), (1000, True, False), (1099, True, False), (1100, True, True)):
            base.episode_length_buf[:] = step
            actual = route_time_out(base)
            if bool(actual[flat_ids].all()) != expected_flat or bool(actual[route_ids].all()) != expected_rough:
                raise ValueError('Native mixed episode timeout boundary mismatch')
        base.episode_length_buf[:] = 700
        before = term.vel_command_b.clone()
        untouched = torch.ones(base.num_envs, dtype=torch.bool, device=base.device)
        untouched[chosen[:1]] = False
        base._reset_idx(chosen[:1])
        if (int(base.episode_length_buf[chosen[0]]) != 0 or not bool((term.vel_command_b[chosen[:1]] == 0.).all())
                or not torch.equal(term.vel_command_b[untouched], before[untouched])):
            raise ValueError('Partial native reset did not isolate and restart route settling')
        env.reset()
        if bool(base.episode_length_buf.any()) or not bool((term.vel_command_b[mask] == 0.).all()):
            raise ValueError('Fixture cleanup failed to restore fresh settling episodes')
    return dict(passed=True, reset=reset_evidence, phase_boundaries=records, partial_reset_passed=True,
                rough_timeout_seconds=22., flat_timeout_seconds=20.,
                scope='Native command/reset manager fixture; no physics traversal or policy-quality claim')
