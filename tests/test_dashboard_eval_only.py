"""Dashboard progress for managed comparisons without a training phase."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
import server


class EvaluationOnlyProgressTests(unittest.TestCase):
    def test_nested_evaluation_and_reused_baseline_are_counted(self):
        job_id = "a" * 32
        with tempfile.TemporaryDirectory() as folder, patch.object(server, "ROOT", Path(folder)):
            output = Path(folder) / "logs/dashboard/jobs" / job_id / "velocity_compare"
            output.mkdir(parents=True)
            (output / "preflight_manifest.json").write_text(json.dumps({"plan": {
                "actors": ["parent", "candidate"], "ppo_updates": 0}}))
            evaluation = output / "runtime/child/evaluation"
            declared = evaluation / "parent/declared_plan.json"
            declared.parent.mkdir(parents=True)
            declared.write_text(json.dumps({"variants": {"flat": {}, "rough": {}}}))
            reused = output / "reused_parent"
            reused.mkdir()
            (reused / "flat.json").write_text("{}")
            candidate = evaluation / "candidate"
            candidate.mkdir()
            (candidate / "flat.json").write_text("{}")
            progress = server.managed_recipe_progress({
                "id": job_id, "pilot_progress": {"phase": "evaluate_candidate_rough", "ppo_updates": 0}})
            self.assertEqual(progress["completed_evaluations"], 2)
            self.assertEqual(progress["total_evaluations"], 4)
            self.assertNotIn("target_updates", progress)


if __name__ == "__main__":
    unittest.main()
