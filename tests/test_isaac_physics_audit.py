import sys
from pathlib import Path
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import sim2sim_isaac_protocol as protocol
from isaac_physics_snapshot import target_guard_events
from run_support import local_command


class AuditTests(unittest.TestCase):
    def test_complete_v2_prefix_and_single_seed_only(self):
        import locomotion_v2_protocol as reference
        self.assertEqual(protocol.cases_for("flat_mu_100"),reference.cases_for("flat_mu_100"))
        self.assertEqual(protocol.SEEDS,1)
        self.assertEqual(protocol.POLICIES,(24650,))
        self.assertFalse(protocol.protocol_manifest()["qualification"])

    def test_target_monitor_does_not_clip_inputs_or_confuse_actual_and_desired_position(self):
        case=protocol.cases_for("flat_mu_100")[1]
        targets=np.array([[0,.8,-1.5]*4+[0]*4],dtype=float)
        positions=targets.copy();velocities=np.zeros_like(targets)
        targets[0,5]=-.3;targets[0,12]=-51
        original=targets.copy()
        ranges=np.array([[-.87,.87],[-.94,4.69],[-2.82,-.43]]*4)
        events=target_guard_events(targets,positions,velocities,1000,[(24650,case,73001)],ranges)
        np.testing.assert_array_equal(targets,original)
        self.assertEqual([v["slot"] for v in events[0]["violations"]],[5,12])
        self.assertEqual(events[0]["violations"][0]["measured_q"],-1.5)

    def test_runtime_is_selected_only_for_live_audit_child(self):
        if sys.platform=="win32":self.skipTest("native Ubuntu")
        self.assertEqual(local_command("scripts/run_sim2sim_physics.py")[0],str(ROOT/".venv/bin/python"))
        self.assertEqual(local_command("scripts/run_isaac_audit_child.py")[0],str(ROOT/".runtime/isaaclab-ubuntu-venv/bin/python"))

    def test_recipe_runs_audit_without_training(self):
        from job_manager import recipe
        self.assertEqual(recipe({"kind":"sim2sim_isaac"}),("scripts/run_sim2sim_isaac_audit.py",[]))


if __name__=="__main__":unittest.main()
