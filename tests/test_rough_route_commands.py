import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import torch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rough_route_commands as route


class FakeMeasured:
    """Tensor stand-in for native sampler; no Isaac imports or GPU required."""
    def __init__(self, cfg, env):
        self.cfg, self._env = cfg, env
        self.device, self.num_envs = env.device, env.num_envs
        self.vel_command_b = torch.zeros(env.num_envs, 3)
        self.is_heading_env = torch.zeros(env.num_envs, dtype=torch.bool)
        self.is_standing_env = torch.zeros(env.num_envs, dtype=torch.bool)
        self.time_left = torch.zeros(env.num_envs)
        self.distribution_counts = torch.zeros(6, dtype=torch.float64)
        self.native_resamples = []

    def _resample_command(self, ids):
        self.native_resamples.append(ids.clone())
        self.vel_command_b[ids] = torch.tensor([.6, -.4, .8])
        self.is_heading_env[ids] = True

    def _update_command(self):
        self.vel_command_b[self.is_heading_env, 2] = .7
        self.vel_command_b[self.is_standing_env] = 0.
        self.distribution_counts += route._command_counts(self.vel_command_b)

    def distribution_snapshot(self):
        return {'env_command_steps': int(self.distribution_counts[0])}


def fake_env(n=100):
    return SimpleNamespace(num_envs=n, device='cpu', cfg=SimpleNamespace(seed=59),
        scene=SimpleNamespace(terrain=SimpleNamespace(terrain_types=torch.arange(n) % 10)),
        episode_length_buf=torch.zeros(n, dtype=torch.long), step_dt=.02)


class RoughRouteTests(unittest.TestCase):
    def make_command(self, n=100):
        module = ModuleType('b2w_yaw_commands')
        module.MeasuredYawVelocityCommand = FakeMeasured
        old = route.__dict__.pop('RouteVelocityCommand', None)
        try:
            with patch.dict(sys.modules, b2w_yaw_commands=module):
                cls = route.get_route_command_class()
                env = fake_env(n)
                return env, cls(SimpleNamespace(), env)
        finally:
            route.__dict__.pop('RouteVelocityCommand', None)
            if old is not None:
                route.RouteVelocityCommand = old

    def test_distribution_is_balanced_independent_and_reproducible(self):
        original = torch.get_rng_state().clone()
        draws = torch.rand((100000, 4), generator=torch.Generator().manual_seed(59))
        kind, speed, turn = route.sampled_routes(draws)
        for k, expected in enumerate((.6, .2, .2)):
            self.assertAlmostEqual(float((kind == k).float().mean()), expected, delta=.006)
        self.assertTrue(((speed[kind == 0] >= .20) & (speed[kind == 0] <= .24)).all())
        self.assertTrue((speed[kind != 0] == .30).all())
        self.assertTrue(((turn.abs() >= .20) & (turn.abs() <= .30)).all())
        self.assertAlmostEqual(float((turn[kind == 2] > 0).float().mean()), .5, delta=.015)
        self.assertTrue(torch.equal(torch.get_rng_state(), original))
        with self.assertRaises(ValueError):route.sampled_routes(torch.zeros(5, 3))

    def test_all_phase_boundaries_preserve_flat_commands(self):
        command = torch.tensor([[.7, -.2, -.5]] * 4)
        original_flat = command[0].clone()
        mask = torch.tensor([False, True, True, True])
        kind = torch.tensor([0, 0, 1, 2])
        speed = torch.tensor([.9, .22, .3, .3])
        turn = torch.tensor([1., .25, .25, -.25])
        for step in (0, 99, 100, 699, 700, 1099):
            route.apply_route_schedule(command, mask, kind, speed, turn, torch.full((4,), step), .02)
            self.assertTrue(torch.equal(command[0], original_flat))
            expected = [[0., 0., 0.]] * 3 if step < 100 else (
                [[.22, 0., 0.], [.3, 0., 0.], [.3, 0., 0.]] if step < 700 else
                [[.22, 0., 0.], [0., 0., 0.], [0., 0., -.25]])
            self.assertTrue(torch.allclose(command[1:], torch.tensor(expected), atol=1e-7, rtol=0.))

    def test_native_sampler_only_flat_and_counts_final_commands(self):
        env, command = self.make_command()
        command._resample_command(torch.arange(env.num_envs))
        self.assertTrue(torch.equal(command.native_resamples[0], (~command.route_mask).nonzero().flatten()))
        self.assertTrue((command.time_left[command.route_mask] > 22.).all())
        self.assertFalse(command.is_heading_env[command.route_mask].any())
        self.assertFalse(command.is_standing_env[command.route_mask].any())
        command._update_command()
        expected = route._command_counts(command.vel_command_b).double()
        self.assertTrue(torch.equal(command.distribution_counts, expected))
        self.assertEqual(int(command.distribution_counts[1]), 70)
        self.assertEqual(int(command.route_phase_steps[0]), 70)
        snapshot = command.distribution_snapshot()['rough_route']
        self.assertEqual(sum(snapshot['sampled_episode_kinds'].values()), 70)

    def test_partial_reset_starts_settle_without_touching_other_routes(self):
        env, command = self.make_command()
        command._resample_command(None)
        env.episode_length_buf[:] = 700
        command._update_command()
        before = command.vel_command_b.clone()
        old_routes = command.route_kind.clone()
        selected = torch.tensor([3, 5])
        command._resample_command(selected)
        untouched = torch.ones(env.num_envs, dtype=torch.bool)
        untouched[selected] = False
        self.assertTrue((command.vel_command_b[selected] == 0.).all())
        self.assertTrue(torch.equal(command.vel_command_b[untouched], before[untouched]))
        self.assertTrue(torch.equal(command.route_kind[untouched], old_routes[untouched]))
        env.episode_length_buf[selected] = 0
        command._update_command()
        self.assertTrue((command.vel_command_b[selected] == 0.).all())

    def test_flat20_rough22_timeout_boundaries(self):
        env = fake_env()
        mask = route.rough_mask(env)
        for step, flat, rough in ((999, False, False), (1000, True, False), (1099, True, False), (1100, True, True)):
            env.episode_length_buf[:] = step
            result = route.route_time_out(env)
            self.assertTrue((result[mask] == rough).all())
            self.assertTrue((result[~mask] == flat).all())

    def test_native_root_reset_is_split_and_original_ranges_unchanged(self):
        env = fake_env()
        pose = dict(x=(-.5, .5), y=(-.5, .5), z=(0., .2), roll=(-.1, .1), pitch=(-.1, .1), yaw=(-3.14, 3.14))
        velocity = dict(x=(-.5, .5), y=(-.5, .5))
        calls = []
        module = ModuleType('robot_lab.tasks.manager_based.locomotion.velocity')
        module.mdp = SimpleNamespace(reset_root_state_uniform=lambda env, ids, **kw: calls.append((ids, kw)))
        with patch.dict(sys.modules, {'robot_lab.tasks.manager_based.locomotion.velocity': module}):
            route.route_reset_root_state(env, torch.tensor([0, 3, 7]), pose, velocity)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0].tolist(), [0])
        self.assertIs(calls[0][1]['pose_range'], pose)
        self.assertIs(calls[0][1]['velocity_range'], velocity)
        self.assertEqual(calls[1][0].tolist(), [3, 7])
        params = calls[1][1]
        self.assertEqual(params['pose_range']['x'], (0., 0.))
        self.assertEqual(params['pose_range']['yaw'], (-.025, .025))
        self.assertEqual(params['pose_range']['roll'], pose['roll'])
        self.assertTrue(all(v == (0., 0.) for v in params['velocity_range'].values()))
        self.assertEqual(pose['x'], (-.5, .5))

    def test_exact_tracking_route_progress_is_feasible_and_leaves_spawn(self):
        kind = torch.tensor([0, 0, 1, 2])
        speed = torch.tensor([.2, .24, .3, .3])
        turn = torch.tensor([0., 0., 0., .3])
        mask = torch.ones(4, dtype=torch.bool)
        commands = torch.zeros(4, 3)
        position = torch.zeros(4, 2)
        position[:, 1] = .1
        yaw = torch.full((4,), .025)
        for step in range(1100):
            route.apply_route_schedule(commands, mask, kind, speed, turn, torch.full((4,), step), .02)
            position[:, 0] += commands[:, 0] * yaw.cos() * .02
            position[:, 1] += commands[:, 0] * yaw.sin() * .02
            yaw += commands[:, 2] * .02
        self.assertTrue((position[:, 0] >= 3.).all())
        self.assertTrue((position[:, 0] <= 4.81).all())
        self.assertTrue((position[:, 1].abs() < .23).all())


if __name__ == '__main__':unittest.main()
