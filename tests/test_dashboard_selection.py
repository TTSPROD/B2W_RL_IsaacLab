"""Partial independent evaluation evidence must not look like a final ranking."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
import server


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'dashboard/jobs/fixture/evaluation'
        self.policies = ['24650', 'stairfixed_26000', 'stairadaptive_26000']
        self.terrains = ['flat_mu_100', 'rough_10', 'stairs_up_18', 'stairs_down_18']
        self.job = {'id': 'fixture', 'status': 'running', 'created': '2026-09-30T20:00:00+00:00'}
        self.write('comparison_plan.json', {'policies': self.policies, 'episodes_per_actor': 60})
        self.write('24650/declared_plan.json', {'variants': self.terrains, 'reset_seeds': [1, 2, 3, 4, 5]})
        self.write('evaluation_progress.json', {'status': 'running',
                   'completed': ['24650/flat_mu_100'], 'active': ['24650/rough_10'],
                   'updated': '2026-09-30T20:01:00+00:00'})
        self.write('24650/flat_mu_100.json', {'records': [
            {'policy': '24650', 'terrain': 'flat_mu_100', 'outcome': 'success'},
            {'policy': '24650', 'terrain': 'flat_mu_100', 'outcome': 'unsafe',
             'safety': {'unsafe_flags': ['fall']}}]})
        # A file exists, but its batch is not committed in progress yet.
        self.write('24650/rough_10.json', {'records': [
            {'policy': '24650', 'terrain': 'rough_10', 'outcome': 'success'}]})
        for context in (patch.object(server, 'SELECTION_ROOT', self.root),
                        patch.object(server, 'list_jobs', return_value=[self.job])):
            context.start()
            self.addCleanup(context.stop)

    def write(self, name, value):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_partial_batches_and_waiting_actors(self):
        result = server.selection_data('current')
        self.assertEqual(result['episodes_recorded'], 2)
        self.assertEqual(result['episodes_total'], 180)
        self.assertEqual(result['variants_total'], 12)
        self.assertEqual(result['overall']['24650']['unsafe'], 1)
        self.assertEqual(result['overall']['24650']['success'], 1)
        self.assertEqual(result['overall']['stairadaptive_26000']['episodes'], 0)
        self.assertEqual(result['conditions']['rough']['24650']['episodes'], 0)
        self.assertEqual(result['active'][0]['terrain'], '24650/rough_10')
        self.assertEqual(result['ranking'], self.policies)
        self.assertTrue(result['ranking_is_order'])
        self.assertTrue(result['partial'])

    def test_interrupted_supervisor_overrides_stale_running_progress(self):
        self.job['status'] = 'interrupted'
        result = server.selection_data('current')
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(result['active'], [])
        self.assertEqual(result['episodes_recorded'], 2)

    def test_default_source_still_reads_saved_registry(self):
        with patch.object(server, 'registry_selection_data', return_value={'episodes_total': 480}):
            result = server.selection_data()
        self.assertEqual(result['source'], 'registry')
        self.assertEqual(result['episodes_total'], 480)


if __name__ == '__main__':
    unittest.main()
