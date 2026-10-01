"""The replay must preserve the pilot's cases/reset pairing, not soften its gates."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
import locomotion_v2_pilot_protocol as pilot
import locomotion_v2_stair_replay_protocol as replay
import locomotion_v2_stair_isolation_protocol as isolation
import jobs
from analyze_stair_replay import compare_records


class StairReplayTests(unittest.TestCase):
    def test_isolation_refuses_multiple_actors_and_preserves_slots(self):
        root = Path(__file__).resolve().parents[1]
        export = root / 'policies/local/core_24650/export'
        with self.assertRaises(ValueError):
            isolation.protocol_manifest({24650: export, 'control_24675': export})
        plan = isolation.protocol_manifest({24650: export})
        self.assertEqual(plan['episodes_per_policy'], 10)
        self.assertEqual(plan['conditions'], ['stairs_up'])
        self.assertEqual(isolation.cases_for('stairs_up_18'), pilot.cases_for('stairs_up_18'))
        self.assertEqual(jobs.recipe({'kind': 'stair_isolation'}), ('scripts/run_stair_isolation.py', []))

    def test_pair_by_identity_not_position_and_reject_missing(self):
        records = [{'policy': p, 'case': 'traverse_0.7', 'seed': 73001,
                    'covered_scenario_success': True, 'failure_flags': []}
                   for p in (24650, 'control_24700')]
        self.assertEqual(compare_records(records, list(reversed(records))), [])
        changed = [dict(r) for r in reversed(records)]
        changed[0].update(covered_scenario_success=False, failure_flags=['unsafe'])
        delta = compare_records(records, changed)
        self.assertEqual(len(delta), 1)
        self.assertEqual(delta[0]['policy'], 'control_24700')
        with self.assertRaises(ValueError):
            compare_records(records, records[:1])
        with self.assertRaises(ValueError):
            compare_records(records, [records[0], records[0]])

    def test_identical_cases_seeds_and_scoring(self):
        self.assertEqual((replay.SEEDS, replay.SEED_START), (pilot.SEEDS, pilot.SEED_START))
        for name in replay.TERRAINS:
            self.assertEqual(replay.cases_for(name), pilot.cases_for(name))
            self.assertEqual(replay.geometry(name), pilot.geometry(name))
        self.assertIs(replay.assess, pilot.assess)
        self.assertIs(replay.finalize_result, pilot.finalize_result)
        plan = replay.protocol_manifest({24650: Path(__file__).resolve().parents[1] / 'policies/local/core_24650/export'})
        self.assertEqual(plan['episodes_per_policy'], 20)
        self.assertEqual(set(plan['conditions']), {'stairs_up', 'stairs_down'})
        self.assertTrue(plan['diagnostic_only'])
        self.assertFalse(plan['selection_only'])

    def test_dashboard_replay_is_bounded(self):
        for order in ('same', 'reverse'):
            self.assertEqual(jobs.recipe({'kind': 'stair_replay', 'order': order}),
                             ('scripts/run_stair_replay.py', ['--order', order]))
        with self.assertRaises(ValueError):
            jobs.recipe({'kind': 'stair_replay', 'order': 'random'})
