"""CPU policy checks require the isolated project torch/PyYAML runtime."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AVAILABLE = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("yaml") is not None
if AVAILABLE:
    spec = importlib.util.spec_from_file_location("contract", ROOT / "scripts/check_policy_contract.py")
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    torch = contract.torch


@unittest.skipUnless(AVAILABLE, "requires project torch and PyYAML runtime")
class PolicyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = contract.load_contract()
        cls.states = contract.fixtures(cls.cfg)

    def test_all_joint_channels_have_correct_slot_and_scale(self):
        for i, name in enumerate(self.cfg["joint_names"]):
            with self.subTest(joint=name):
                pos = contract.make_observation(self.states[f"position_{name}"], self.cfg)
                expected = torch.zeros(16)
                if i < 12:
                    expected[i] = 0.1
                torch.testing.assert_close(pos[9:25], expected, rtol=0, atol=1e-6)
                vel = contract.make_observation(self.states[f"velocity_{name}"], self.cfg)
                expected = torch.zeros(16)
                expected[i] = 0.1
                torch.testing.assert_close(vel[25:41], expected, rtol=0, atol=1e-6)

    def test_body_gravity_and_command_sign(self):
        neutral = contract.make_observation(self.states["neutral_reset"], self.cfg)
        self.assertEqual(neutral[3:6].tolist(), [0, 0, -1])
        for sign in (-1, 1):
            obs = contract.make_observation(self.states[f"yaw_command_{sign:+d}"], self.cfg)
            self.assertAlmostEqual(obs[2].item(), sign * 0.05, places=6)
            self.assertEqual(obs[8].item(), sign * 0.5)
            tilted = contract.make_observation(self.states[f"roll_{sign:+d}"], self.cfg)
            self.assertLess(sign * tilted[4].item(), 0)

    def test_reset_clears_history_but_stop_retains_it(self):
        stop = contract.make_observation(self.states["stop_with_action_history"], self.cfg)
        reset = contract.make_observation(self.states["reset_after_stop"], self.cfg)
        self.assertEqual(stop[6:9].tolist(), [0, 0, 0])
        self.assertEqual(torch.count_nonzero(stop[41:57]).item(), 16)
        self.assertEqual(torch.count_nonzero(reset[41:57]).item(), 0)

    def test_nan_infinity_stale_shape_and_quaternion_rejected(self):
        cases = [{"omega_body": [float("nan"), 0, 0]}, {"joint_pos": [float("inf")] * 16},
                 {"age_s": 0.021}, {"age_s": -1}, {"commands": [0, 0]}, {"quat_wxyz": [0, 0, 0, 0]}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                contract.make_observation(dict(self.states["neutral_reset"], **changes), self.cfg)
        with self.assertRaises(ValueError):
            contract.action_targets([float("nan")] * 16, self.cfg)

    def test_single_joint_actions_and_sdk_identity(self):
        self.assertEqual(self.cfg["joint_mapping"], list(range(16)))
        for i in range(16):
            action = [0.0] * 16
            action[i] = 1.0
            target = contract.action_targets(action, self.cfg)
            expected = torch.tensor(self.cfg["default_dof_pos"])
            expected[i] += self.cfg["action_scale"][i]
            torch.testing.assert_close(target, expected, rtol=0, atol=1e-6)

    def test_upstream_wheel_function_handles_recorded_asset_permutation(self):
        result = contract.upstream_wheel_observation_check(self.cfg, self.states)
        self.assertEqual(result["policy_to_fixture_asset_indices"], [1, 5, 9, 0, 4, 8, 3, 7, 11, 2, 6, 10, 13, 12, 15, 14])
        self.assertEqual(result["max_abs_error"], 0)

    def test_saturation_is_explicit_mismatch(self):
        state = dict(self.states["neutral_reset"], joint_vel=[200.0] * 16)
        self.assertEqual(contract.make_observation(state, self.cfg)[25].item(), 10)
        self.assertEqual(contract.make_observation(state, self.cfg, isaac_semantics=True)[25].item(), 5)
        self.assertEqual(contract.action_targets([200.0] * 16, self.cfg)[12].item(), 500)
        self.assertEqual(contract.action_targets([200.0] * 16, self.cfg, isaac_semantics=True)[12].item(), 100)

    def test_real_reference_torchscript_cpu_fixtures(self):
        report = contract.run_checks()
        self.assertEqual(report["fixture_count"], 39)
        self.assertLessEqual(report["max_eager_script_error"], 1e-5)
        self.assertLessEqual(report["max_batch_single_error"], 1e-5)
        self.assertFalse(report["stage_1_complete"])
        self.assertFalse(report["training_checkpoint_export_parity"])


if __name__ == "__main__":
    unittest.main()
