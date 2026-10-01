"""Behavioral regressions in the compact screen and its evidence validation."""
import copy
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from locomotion57_protocol import DT
import locomotion_v2_protocol as protocol
import locomotion_v2_validation_protocol as validation


class LocomotionV2Tests(unittest.TestCase):
    def test_frozen_source_paths_include_configs_and_legacy_script_names(self):
        from run_core_locomotion_eval import frozen_source_path
        self.assertEqual(frozen_source_path('configs/24650_stair_comparison_1350_20260930.json'),
                         ROOT/'configs/24650_stair_comparison_1350_20260930.json')
        self.assertEqual(frozen_source_path('scripts/run_support.py'),ROOT/'scripts/run_support.py')
        self.assertEqual(frozen_source_path('run_support.py'),ROOT/'scripts/run_support.py')
        with self.assertRaises(ValueError):frozen_source_path('../outside.py')

    def assess(self, case, velocity):
        return protocol.assess(case, velocity, np.zeros((len(velocity), 3)),
                               {"unsafe_flags": []}, len(velocity) == case.steps, protocol.geometry(case.terrain))

    def test_training_bounds_and_real_sign_reversals(self):
        count = 0
        for terrain in protocol.TERRAINS:
            for case in protocol.cases_for(terrain):
                commands, _ = case.schedule()
                self.assertLessEqual(np.abs(commands).max(), 1.)
                count += protocol.SEEDS
                if case.name in {"longitudinal", "lateral", "yaw"}:
                    values = [s.command for s in case.segments]
                    self.assertTrue(any(np.dot(a, b) < 0 for a, b in zip(values, values[1:])))
        self.assertEqual(count, 160)
        self.assertTrue(set(range(protocol.SEED_START, protocol.SEED_START + protocol.SEEDS)).isdisjoint(
            range(validation.SEED_START, validation.SEED_START + validation.SEEDS)))

    def test_frozen_tracking_failure_cannot_hide_behind_transition_metric(self):
        case = protocol.cases_for("flat_mu_100")[1]
        stopped = np.zeros((case.steps, 3))
        result = self.assess(case, stopped)
        self.assertIn("tracking_failure", result["failure_flags"])
        perfect = self.assess(case, case.schedule()[0])
        self.assertEqual(perfect["outcome"], "success")
        self.assertTrue(all(s["response_time_s"] == 1 for s in perfect["segments"] if "response_time_s" in s))

    def test_stairs_final_stop_cannot_be_discarded(self):
        case = protocol.cases_for("stairs_down_06")[0]
        velocity = case.schedule()[0].copy()
        velocity[-500:, 0] = .2
        result = self.assess(case, velocity)
        coverage = {"moving_exposure_pass": True, "zero_windows": []}
        final, _ = protocol.finalize_result(case, result, coverage, True)
        self.assertEqual(final["outcome"], "standstill_failure")
        self.assertFalse(final["checks"]["stop"])

    def test_stairs_no_exposure_and_truncated_trace_fail(self):
        case = protocol.cases_for("stairs_up_18")[0]
        result = self.assess(case, case.schedule()[0][:-1])
        final, covered = protocol.finalize_result(case, result,
            {"moving_exposure_pass": False, "zero_windows": []}, True)
        self.assertFalse(covered)
        self.assertEqual(final["outcome"], "traversal_failure")

    def test_json_round_trip_preserves_frozen_plan_comparison(self):
        import json
        plan = protocol.protocol_manifest({})
        frozen = json.loads(json.dumps(plan))
        self.assertEqual(json.loads(json.dumps(protocol.protocol_manifest({}))), frozen)

    def test_unreached_stop_cannot_be_reported_as_passed(self):
        case = protocol.cases_for("flat_mu_40")[1]
        result = self.assess(case, case.schedule()[0][:300])
        final, _ = protocol.finalize_result(case, result, None, True)
        self.assertFalse(final["checks"]["stop"])

    def test_evidence_rejects_duplicate_episodes_and_changed_traces(self):
        import json
        import tempfile
        from run_support import write_json, sha256
        from summarize_locomotion import validate_terrain
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "sources/scripts").mkdir(parents=True)
            (base / "sources/scripts/example.py").write_text("pass")
            (base / "flat_mu_40.npz").write_bytes(b"immutable trace fixture")
            plan = {"schema": "b2w_locomotion_v2", "policies": [24650], "reset_seeds": [73001],
                    "variants": {"flat_mu_40": {"cases": [{"name": "stand"}]}},
                    "exports": {"24650": {"export_sha256": "abc"}},
                    "source_sha256": {"scripts/example.py": sha256(base / "sources/scripts/example.py")}}
            result = {"protocol": {k: v for k, v in plan.items() if k != "source_sha256"},
                      "declared_source_sha256": plan["source_sha256"],
                      "policy_exports": {"24650": {"sha256": "abc"}},
                      "trace_sha256": sha256(base / "flat_mu_40.npz"),
                      "observation_parity_max_abs": 0, "command_observation_max_abs": 0,
                      "records": [{"policy": 24650, "case": "stand", "seed": 73001, "terrain": "flat_mu_40"}]}
            write_json(base / "flat_mu_40.json", result)
            validate_terrain(base, "flat_mu_40", plan)
            result["records"] *= 2
            write_json(base / "flat_mu_40.json", result)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                validate_terrain(base, "flat_mu_40", plan)
            (base / "flat_mu_40.npz").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                validate_terrain(base, "flat_mu_40", plan)


if __name__ == "__main__":
    unittest.main()
