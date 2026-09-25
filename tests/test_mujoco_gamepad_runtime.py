from pathlib import Path
import sys
import tempfile
import unittest

import mujoco
import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_policy_contract import load_contract
from play_mujoco_b2w_gamepad import B2WMujocoRuntime, run_headless_smoke
from mujoco_safety_recorder import CommandTraceWriter, load_command_trace, validate_trace_context
from sim2sim_mujoco_b2w import DEFAULT_POLICY, DEFAULT_XML, build_model, validate_model_contract


class MujocoGamepadRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_contract()
        cls.model, cls.terrain = build_model(DEFAULT_XML, "flat")
        validate_model_contract(cls.model, cls.cfg)
        cls.policy = torch.jit.load(str(DEFAULT_POLICY), map_location="cpu").eval()

    def test_policy_and_mixed_actuator_steps_are_finite(self):
        runtime = B2WMujocoRuntime(self.model, self.policy, self.cfg, self.terrain)
        action = runtime.policy_step((0.2, 0.0, 0.1))
        self.assertEqual(action.shape, (16,))
        efforts = [runtime.physics_step() for _ in range(runtime.substeps)]
        self.assertTrue(np.isfinite(np.asarray(efforts)).all())
        self.assertEqual(runtime.state.physics_steps, runtime.substeps)
        self.assertLessEqual(runtime.state.peak_wheel_torque_utilization, 1.0)

    def test_reset_clears_action_history(self):
        runtime = B2WMujocoRuntime(self.model, self.policy, self.cfg, self.terrain)
        runtime.policy_step((0.2, 0.0, 0.0))
        self.assertGreater(float(np.max(np.abs(runtime.state.previous_action))), 0.0)
        runtime.reset()
        np.testing.assert_array_equal(runtime.state.previous_action, np.zeros(16, dtype=np.float32))

    def test_headless_smoke_returns_contract_telemetry(self):
        runtime = B2WMujocoRuntime(self.model, self.policy, self.cfg, self.terrain)
        telemetry = run_headless_smoke(runtime, 5)
        self.assertEqual(telemetry["policy_steps"], 5)
        self.assertEqual(telemetry["physics_steps"], 5 * runtime.substeps)
        self.assertTrue(np.isfinite(telemetry["tilt_deg"]))
        self.assertEqual(telemetry["safety"]["physics_steps"], 5 * runtime.substeps)
        self.assertFalse(telemetry["safety"]["unsafe_pending"])

    def test_full_rate_recorder_preserves_terminal_state_and_failure_window(self):
        runtime = B2WMujocoRuntime(self.model, self.policy, self.cfg, self.terrain)
        runtime.data.time = 1.0
        runtime.data.qpos[3:7] = (2**-0.5, 2**-0.5, 0.0, 0.0)
        mujoco.mj_forward(runtime.model, runtime.data)
        event = runtime.safety.record_physics_step(runtime.data, np.zeros(16))
        self.assertIsNotNone(event)
        self.assertIn("excessive_tilt", event["reasons"])
        summary = runtime.safety.finalize(runtime.data, "unsafe")
        self.assertEqual(summary["outcome"], "unsafe")
        self.assertEqual(summary["failure_reason"], "excessive_tilt")
        self.assertEqual(len(summary["terminal_state"]["observation"]), 57)
        self.assertEqual(len(summary["failure_window"]["samples"]), 1)
        self.assertIn("torque_at_or_above_95pct_fraction", summary["wheels"])
        self.assertIn("rolling_residual_rms_m_s", summary["wheels"])

    def test_command_trace_round_trip_and_context_guard(self):
        context = {
            "policy_sha256": "policy",
            "xml_sha256": "xml",
            "terrain": {"kind": "flat"},
            "policy_dt_s": 0.02,
            "policy_abi": "57 observations -> 16 actions",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "commands.jsonl"
            writer = CommandTraceWriter(path, context)
            writer.record((0.1, 0.0, -0.2))
            writer.record((0.0, 0.0, 0.0), reset_before_step=True)
            writer.close("completed")
            header, commands = load_command_trace(path)
        self.assertEqual([item.step for item in commands], [0, 1])
        self.assertTrue(commands[1].reset_before_step)
        validate_trace_context(
            header, policy_sha256="policy", xml_sha256="xml",
            terrain={"kind": "flat"}, policy_dt_s=0.02,
        )
        with self.assertRaises(ValueError):
            validate_trace_context(
                header, policy_sha256="different", xml_sha256="xml",
                terrain={"kind": "flat"}, policy_dt_s=0.02,
            )

    def test_scene_mode_loads_supplied_xml_without_overlay(self):
        model, terrain = build_model(DEFAULT_XML, "scene")
        validate_model_contract(model, self.cfg)
        self.assertEqual(terrain, {"kind": "scene"})


if __name__ == "__main__":
    unittest.main()
