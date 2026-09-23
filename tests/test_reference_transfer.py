"""CPU transfer contracts and real pinned-reference import; no simulator."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
AVAILABLE = importlib.util.find_spec("torch") is not None
if AVAILABLE:
    import torch
    from torch import nn
    import reference_transfer as transfer

    def actor():
        return nn.Sequential(nn.Linear(57, 512), nn.ELU(), nn.Linear(512, 256), nn.ELU(),
                             nn.Linear(256, 128), nn.ELU(), nn.Linear(128, 16))

    class Policy(nn.Module):
        def __init__(self):
            super().__init__()
            self.actor = actor()
            self.critic = nn.Linear(60, 1)
            self.actor_obs_normalizer = nn.Identity()
            self.actor_obs_normalization = False
            self.obs_groups = {"policy": ["policy"], "critic": ["critic"]}
            self.std = nn.Parameter(torch.full((16,), .1))
            self.noise_std_type = "scalar"
            self.state_dependent_std = False

        def get_actor_obs(self, observations):
            return observations["policy"]

        def act_inference(self, observations):
            return self.actor(self.actor_obs_normalizer(self.get_actor_obs(observations)))

    class Teacher(nn.Module):
        def __init__(self, normalizer=None):
            super().__init__()
            self.actor = actor()
            self.normalizer = normalizer if normalizer is not None else nn.Identity()

        def forward(self, inputs):
            return self.actor(self.normalizer(inputs))


@unittest.skipUnless(AVAILABLE, "requires project torch runtime")
class ReferenceTransferTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.policy = Policy()
        self.observations = {"policy": transfer.reference_probes(), "critic": torch.zeros(295, 60)}

    def test_actual_reference_import_preserves_critic_and_matches_295_probes(self):
        critic_before = {key: value.clone() for key, value in self.policy.critic.state_dict().items()}
        teacher, metadata = transfer.initialize_reference(
            self.policy, ROOT / "vendor/rl_sar/policy/b2w/robot_lab/policy.pt", self.observations)
        self.assertEqual(metadata["parity_probe_count"], 295)
        self.assertLessEqual(metadata["cpu_max_abs_error"], 1e-5)
        self.assertFalse(metadata["policy_quality_evaluated"])
        self.assertEqual(len(metadata["reference_sha256"]), 64)
        for key, value in self.policy.critic.state_dict().items():
            torch.testing.assert_close(value, critic_before[key], rtol=0, atol=0)
        self.assertTrue(all(p.requires_grad for p in self.policy.critic.parameters()))
        self.assertTrue(all(not p.requires_grad for p in self.policy.actor.parameters()))
        self.assertTrue(all(not p.requires_grad for p in teacher.parameters()))
        self.assertFalse(self.policy.std.requires_grad)
        torch.testing.assert_close(self.policy.std, torch.full((16,), .1))

    @unittest.skipUnless(importlib.util.find_spec("rsl_rl"), "requires native RSL-RL runtime")
    def test_native_rsl_actor_critic_accepts_tensordict_and_preserves_value_gradients(self):
        import contextlib
        import io
        from rsl_rl.modules import ActorCritic
        from tensordict import TensorDict
        observations = TensorDict(self.observations, batch_size=[295])
        with contextlib.redirect_stdout(io.StringIO()):
            policy = ActorCritic(observations, {"policy": ["policy"], "critic": ["critic"]}, 16,
                                 actor_hidden_dims=[512, 256, 128], critic_hidden_dims=[512, 256, 128],
                                 activation="elu", init_noise_std=.1)
        teacher, metadata = transfer.initialize_reference(
            policy, ROOT / "vendor/rl_sar/policy/b2w/robot_lab/policy.pt", observations)
        policy.evaluate(observations).square().mean().backward()
        self.assertTrue(all(parameter.grad is None for parameter in policy.actor.parameters()))
        self.assertTrue(any(parameter.grad is not None for parameter in policy.critic.parameters()))
        self.assertLessEqual(transfer.measure_reference_drift(policy, teacher, observations)["raw_action_max_abs"], 1e-5)
        self.assertFalse(policy.std.requires_grad)

    def test_frozen_actor_critic_update_then_actor_unfreeze_keep_std_fixed(self):
        transfer.set_actor_trainable(self.policy, False)
        optimizer = torch.optim.Adam(self.policy.parameters(), lr=1e-3)
        actor_before = {k: v.clone() for k, v in self.policy.actor.state_dict().items()}
        critic_before = self.policy.critic.weight.clone()
        loss = self.policy.critic(torch.ones(8, 60)).square().mean()
        optimizer.zero_grad(); loss.backward(); optimizer.step()
        self.assertFalse(torch.equal(critic_before, self.policy.critic.weight))
        for key, value in self.policy.actor.state_dict().items():
            torch.testing.assert_close(value, actor_before[key], rtol=0, atol=0)
        transfer.set_actor_trainable(self.policy, True)
        self.assertTrue(all(p.requires_grad for p in self.policy.actor.parameters()))
        self.assertFalse(self.policy.std.requires_grad)

    def test_drift_uses_identical_inputs_and_action_scales(self):
        teacher = Teacher()
        self.policy.actor.load_state_dict(teacher.actor.state_dict())
        transfer.set_actor_trainable(self.policy, True)
        with torch.no_grad():
            self.policy.actor[6].bias.add_(.2)
        drift = transfer.measure_reference_drift(self.policy, teacher, self.observations)
        self.assertAlmostEqual(drift["raw_action_rms"], .2, places=5)
        self.assertAlmostEqual(drift["mean_gaussian_kl"], 32., places=4)
        self.assertAlmostEqual(drift["wheel_target_rms_rad_s"], 1., places=5)
        expected = torch.tensor([.025, .05, .05] * 4).square().mean().sqrt().item()
        self.assertAlmostEqual(drift["leg_target_rms_rad"], expected, places=5)

    def test_rejects_nonidentity_teacher_nonfinite_weights_and_extra_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in ("normalizer", "nan", "extra", "shape", "activation"):
                with self.subTest(kind=kind):
                    teacher = Teacher(nn.Linear(57, 57) if kind == "normalizer" else None)
                    if kind == "nan":
                        with torch.no_grad():
                            teacher.actor[0].weight[0, 0] = float("nan")
                    if kind == "extra":
                        teacher.register_buffer("extra", torch.zeros(1))
                    if kind == "shape":
                        teacher.actor[6] = nn.Linear(128, 17)
                    if kind == "activation":
                        teacher.actor[1] = nn.ReLU()
                    path = Path(directory) / (kind + ".pt")
                    torch.jit.script(teacher).save(str(path))
                    with self.assertRaises(ValueError):
                        transfer.load_reference_teacher(path)

    def test_rejects_bad_student_observations_and_fixed_std(self):
        reference = ROOT / "vendor/rl_sar/policy/b2w/robot_lab/policy.pt"
        for inputs in (torch.zeros(2, 56), torch.full((2, 57), float("nan")), torch.zeros(0, 57)):
            with self.subTest(shape=inputs.shape), self.assertRaises(ValueError):
                transfer.initialize_reference(self.policy, reference, {"policy": inputs})
        for std in (0., -1., float("nan"), float("inf")):
            with self.subTest(std=std), self.assertRaises(ValueError):
                transfer.set_actor_trainable(self.policy, True, std)
        with torch.no_grad():
            self.policy.std[0] = .2
        with self.assertRaises(ValueError):
            transfer.set_actor_trainable(self.policy, True)
        self.policy.actor_obs_normalizer = nn.Linear(57, 57)
        with self.assertRaises(ValueError):
            transfer.initialize_reference(self.policy, reference, self.observations)

    def test_upright_curriculum_changes_only_reset_roll_and_pitch(self):
        from types import SimpleNamespace
        import copy
        params = {"pose_range": {"x": (-.5, .5), "z": (0., .2), "yaw": (-3.14, 3.14),
                                "roll": (-3.14, 3.14), "pitch": (-3.14, 3.14)},
                  "velocity_range": {"roll": (-.5, .5), "x": (-.5, .5)}}
        before = copy.deepcopy(params)
        cfg = SimpleNamespace(events=SimpleNamespace(randomize_reset_base=SimpleNamespace(params=params)))
        change = transfer.apply_flat_upright_reset(cfg)
        self.assertEqual(params["pose_range"]["roll"], (-.1, .1))
        self.assertEqual(params["pose_range"]["pitch"], (-.1, .1))
        self.assertEqual(len(change["changed_fields"]), 2)
        normalized = copy.deepcopy(params)
        for key in ("roll", "pitch"):
            normalized["pose_range"][key] = before["pose_range"][key]
        self.assertEqual(normalized, before)
        with self.assertRaises(ValueError):
            transfer.apply_flat_upright_reset(cfg)


if __name__ == "__main__":
    unittest.main()
