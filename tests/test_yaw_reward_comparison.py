import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location("compare_yaw_reward",Path(__file__).resolve().parents[1]/"scripts/compare_yaw_reward.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(control_yaw=.3, candidate_yaw=.2, control_survival=99, candidate_survival=99):
    result={}
    for arm,yaw,survival in (("control",control_yaw,control_survival),("yaw2x",candidate_yaw,candidate_survival)):
        summary={"episodes":100,"no_fall_count":survival,"by_scenario":{
            s:{"pooled_rms_vx_vy_yaw":[.05,.05,yaw if s in m.YAW else .05]} for s in m.SCENARIOS}}
        result[arm]={"suites":{seed:{"summary":copy.deepcopy(summary)} for seed in m.EVALUATION_SEEDS}}
    return result


class RewardComparisonTests(unittest.TestCase):
    def test_requires_all_seeds_both_directions_and_gate(self):
        r=fixture()
        self.assertEqual(m.compare(r)["decision"],"candidate_promising_pending_three_training_seeds")
        r["yaw2x"]["suites"]["20260919"]["summary"]["by_scenario"]["yaw_negative"]["pooled_rms_vx_vy_yaw"][2]=.29
        self.assertFalse(m.compare(r)["predeclared_effect_met"])
        self.assertFalse(m.compare(r)["candidate_passes_all_suites"])
        self.assertFalse(m.compare(r)["release_accepted"])

    def test_contacts_and_non_yaw_regressions_cannot_be_hidden(self):
        r=fixture(candidate_survival=98)
        self.assertFalse(m.compare(r)["predeclared_effect_met"])
        self.assertFalse(m.compare(r)["candidate_passes_all_suites"])
        r=fixture()
        r["yaw2x"]["suites"]["20260917"]["summary"]["by_scenario"]["lateral"]["pooled_rms_vx_vy_yaw"][1]=.21
        self.assertFalse(m.compare(r)["predeclared_effect_met"])
        self.assertFalse(m.compare(r)["candidate_passes_all_suites"])

    def test_prefer_unchanged_when_both_pass(self):
        self.assertEqual(m.compare(fixture(control_yaw=.24))["decision"],"both_pass_prefer_unchanged_control_pending_replication")

    def test_only_control_passes_is_reported(self):
        self.assertEqual(m.compare(fixture(control_yaw=.24,candidate_yaw=.3))["decision"],
                         "control_promising_pending_three_training_seeds")

    def test_improvement_is_not_acceptance(self):
        r=m.compare(fixture(control_yaw=.4,candidate_yaw=.3))
        self.assertEqual(r["decision"],"tracking_improvement_without_flat_gate")
        self.assertFalse(r["release_accepted"])

    def test_missing_or_nonfinite_measurements_are_rejected(self):
        r=fixture()
        del r["yaw2x"]["suites"]["20260919"]
        with self.assertRaises(KeyError):m.compare(r)
        r=fixture()
        r["yaw2x"]["suites"]["20260919"]["summary"]["by_scenario"]["stand"]["pooled_rms_vx_vy_yaw"][0]=float("nan")
        with self.assertRaises(ValueError):m.compare(r)
        r=fixture()
        del r["yaw2x"]["suites"]["20260919"]["summary"]["by_scenario"]["stand"]
        with self.assertRaises(ValueError):m.compare(r)

if __name__=="__main__":
    unittest.main()
