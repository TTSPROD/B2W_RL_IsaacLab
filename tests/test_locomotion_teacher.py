"""CPU actor lifting and safe curriculum contracts; no simulator imports."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import b2w_locomotion_teacher as teacher

AVAILABLE = importlib.util.find_spec("torch") is not None
if AVAILABLE:
    import torch
    from torch import nn

    def actor(width):
        return nn.Sequential(nn.Linear(width, 512), nn.ELU(), nn.Linear(512, 256), nn.ELU(),
                             nn.Linear(256, 128), nn.ELU(), nn.Linear(128, 16))

    class Scene(dict):
        def __init__(self, positions):
            super().__init__(robot=SimpleNamespace(data=SimpleNamespace(root_pos_w=positions)))
            self.env_origins = torch.zeros_like(positions)
            self.terrain = SimpleNamespace(
                cfg=SimpleNamespace(terrain_generator=SimpleNamespace(size=(12., 12.))),
                terrain_levels=torch.ones(len(positions), dtype=torch.long),
                update_env_origins=self.update,
            )
            self.last_update = None

        def update(self, ids, up, down):
            self.last_update = (ids.clone(), up.clone(), down.clone())
            self.terrain.terrain_levels[ids] += up.long() - down.long()

    def environment(positions, failed=None):
        count = len(positions)
        return SimpleNamespace(
            scene=Scene(torch.tensor(positions, dtype=torch.float32)), device="cpu",
            common_step_counter=500, max_episode_length_s=20.,
            command_manager=SimpleNamespace(get_command=lambda name: torch.tensor([[.6, 0., 0.]] * count)),
            termination_manager=SimpleNamespace(terminated=torch.tensor(failed or [False] * count)),
        )


class LayoutTests(unittest.TestCase):
    def test_blind_prefix_remains_57_and_privileged_suffix_is_appended(self):
        layout = teacher.observation_layout()
        self.assertEqual([item["name"] for item in layout[:6]], [
            "base_ang_vel", "projected_gravity", "velocity_commands", "joint_pos", "joint_vel", "actions"])
        self.assertEqual(layout[5]["stop"], 57)
        self.assertEqual(layout[6], {"name": "base_lin_vel", "start": 57, "stop": 60})
        self.assertEqual(layout[7], {"name": "height_scan", "start": 60, "stop": 247})
        self.assertEqual([item["start"] for item in layout[1:]], [item["stop"] for item in layout[:-1]])
        self.assertAlmostEqual(sum(teacher.MIXED_PROPORTIONS.values()), 1.)

    def test_rejects_profiles_and_diagnostic_curriculum_before_isaac_import(self):
        for profile, curriculum in (("stairs_only", False), ("diagnostic", True)):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                teacher.make_teacher_env_cfg(num_envs=64, device="cpu", seed=67,
                                             terrain_profile=profile, curriculum=curriculum)


@unittest.skipUnless(AVAILABLE, "requires project torch runtime")
class ActorLiftTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        torch.manual_seed(247)
        self.source = actor(57)
        self.target = actor(247)

    def test_exact_weights_and_parity_with_nonzero_privileged_inputs(self):
        before = {key: value.clone() for key, value in self.source.state_dict().items()}
        result = teacher.lift_flat_actor(self.target, self.source)
        self.assertTrue(result["first_layer_prefix_exact"])
        self.assertTrue(result["new_columns_zero"])
        self.assertEqual(result["parity_probe_count"], 295)
        self.assertFalse(result["policy_quality_evaluated"])
        self.assertLessEqual(result["cpu_max_abs_error"], result["tolerance"])
        for name, value in before.items():
            torch.testing.assert_close(self.source.state_dict()[name], value, rtol=0, atol=0)
            lifted = self.target.state_dict()[name]
            torch.testing.assert_close(lifted[:, :57] if name == "0.weight" else lifted,
                                       value, rtol=0, atol=0)
        inputs = torch.randn(37, 247)
        with torch.no_grad():
            torch.testing.assert_close(self.target(inputs), self.source(inputs[:, :57]), rtol=0, atol=1e-6)

    def test_new_velocity_and_scan_columns_receive_gradients_and_learn(self):
        teacher.lift_flat_actor(self.target, self.source)
        inputs = torch.randn(32, 247)
        desired = inputs[:, 57:73]
        optimizer = torch.optim.SGD(self.target.parameters(), lr=.05)
        loss = (self.target(inputs) - desired).square().mean()
        loss.backward()
        gradient = self.target[0].weight.grad
        self.assertGreater(float(gradient[:, 57:60].abs().sum()), 0.)
        self.assertGreater(float(gradient[:, 60:].abs().sum()), 0.)
        optimizer.step()
        self.assertGreater(float(self.target[0].weight[:, 57:].detach().abs().sum()), 0.)
        changed = inputs.clone()
        changed[:, 57:] = 0.
        with torch.no_grad():
            self.assertGreater(float((self.target(inputs) - self.target(changed)).abs().max()), 1e-6)

    def test_trainability_flags_are_preserved(self):
        for parameter in self.target.parameters():
            parameter.requires_grad_(False)
        teacher.lift_flat_actor(self.target, self.source)
        self.assertTrue(all(not parameter.requires_grad for parameter in self.target.parameters()))
        self.assertTrue(all(parameter.requires_grad for parameter in self.source.parameters()))

    def test_pinned_reference_torchscript_can_be_lifted(self):
        from reference_transfer import load_reference_teacher
        reference = load_reference_teacher(ROOT / "vendor/rl_sar/policy/b2w/robot_lab/policy.pt")
        result = teacher.lift_flat_actor(self.target, reference.actor)
        self.assertLessEqual(result["cpu_max_abs_error"], result["tolerance"])

    def test_invalid_actor_fails_before_mutating_target(self):
        for variant in ("shape", "activation", "nonfinite"):
            with self.subTest(variant=variant):
                source = actor(56 if variant == "shape" else 57)
                if variant == "activation":
                    source[1] = nn.ReLU()
                elif variant == "nonfinite":
                    with torch.no_grad():
                        source[6].bias[0] = float("nan")
                before = {key: value.clone() for key, value in self.target.state_dict().items()}
                with self.assertRaises(ValueError):
                    teacher.lift_flat_actor(self.target, source)
                for key, value in self.target.state_dict().items():
                    torch.testing.assert_close(value, before[key], atol=0, rtol=0)


@unittest.skipUnless(AVAILABLE, "requires project torch runtime")
class TerrainCurriculumTests(unittest.TestCase):
    def test_contacts_cannot_promote_after_traversing_tile(self):
        env = environment([[6.1, 0., 0.], [6.1, 0., 0.], [1., 0., 0.]], [False, True, False])
        teacher.failure_aware_terrain_levels_vel(env, [0, 1, 2])
        _, up, down = env.scene.last_update
        self.assertEqual(up.tolist(), [True, False, False])
        self.assertEqual(down.tolist(), [False, True, True])
        self.assertEqual(env.scene.terrain.terrain_levels.tolist(), [2, 0, 0])

    def test_boundary_timeout_does_not_prevent_native_distance_promotion(self):
        env = environment([[5.9, 0., 0.], [6., 0., 0.], [6.01, 0., 0.], [0., -6.01, 0.]])
        timed_out = teacher.tile_boundary_timeout(env)
        self.assertEqual(timed_out.tolist(), [False, False, True, True])
        teacher.failure_aware_terrain_levels_vel(env, [0, 1, 2, 3])
        self.assertTrue(torch.all(env.scene.last_update[1][timed_out]))

    def test_native_contact_catches_first_of_four_substeps_and_reset_clears(self):
        # Compile the actual pinned native function without importing the simulator.
        import ast
        path = ROOT / ".runtime/IsaacLab/source/isaaclab/isaaclab/envs/mdp/terminations.py"
        if not path.exists():
            self.skipTest("pinned Isaac Lab source not installed")
        tree = ast.parse(path.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "illegal_contact")
        module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), function], type_ignores=[])
        scope = {"torch": torch}
        exec(compile(ast.fix_missing_locations(module), str(path), "exec"), scope)
        history = torch.zeros(1, 4, 2, 3)
        history[0, 3, 0, 2] = 2.  # First substep is oldest when policy-step check runs.
        sensor = SimpleNamespace(data=SimpleNamespace(net_forces_w_history=history))
        env = SimpleNamespace(scene=SimpleNamespace(sensors={"contact_forces": sensor}))
        selection = SimpleNamespace(name="contact_forces", body_ids=[0])
        self.assertTrue(scope["illegal_contact"](env, 1., selection).item())
        sensor.data.net_forces_w_history = history[:, :3]
        self.assertFalse(scope["illegal_contact"](env, 1., selection).item())
        sensor.data.net_forces_w_history = history
        # Native ContactSensor.reset clears this exact history buffer.
        history.zero_()
        self.assertFalse(scope["illegal_contact"](env, 1., selection).item())

    def test_curriculum_only_reset_subset_and_no_initial_reset_update(self):
        env = environment([[6.1, 0., 0.], [6.1, 0., 0.], [6.1, 0., 0.]], [True, False, True])
        env.common_step_counter = 0
        teacher.failure_aware_terrain_levels_vel(env, [0, 1])
        self.assertIsNone(env.scene.last_update)
        env.common_step_counter = 1
        teacher.failure_aware_terrain_levels_vel(env, [1])
        self.assertEqual(env.scene.last_update[0].tolist(), [1])
        self.assertEqual(env.scene.terrain.terrain_levels.tolist(), [1, 2, 1])


if __name__ == "__main__":
    unittest.main()
