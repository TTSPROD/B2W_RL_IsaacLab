"""Verify timed rehearsal, interrupted-episode reset and measured-case coverage."""
import json
from pathlib import Path
import sys
import unittest

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from b2w_regression500_sampling import RehearsalBank


class Rehearsal500Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((ROOT/'configs/23999_rehearsal500_20260927.json').read_text())

    def test_every_measured_regression_has_a_schedule(self):
        for row in self.plan['target_rows']:
            name = 'stairs' if row['terrain'].startswith('stairs_') else 'nonstairs'
            self.assertIn(row['case'], {c['case'] for c in self.plan['banks'][name]})
        self.assertEqual(len(self.plan['target_rows']), 43)
        for cases in self.plan['banks'].values():
            for case in cases:
                self.assertGreater(case['weight'], 0)
                self.assertLessEqual(sum(s['seconds'] for s in case['segments']), 60)
                self.assertEqual(case['segments'][-1]['command'], [0, 0, 0])
                self.assertGreaterEqual(case['segments'][-1]['seconds'], 14)
                self.assertTrue(all(abs(v) <= 1 for s in case['segments'] for v in s['command']))

    def test_schedules_advance_and_finish_without_changing_case_early(self):
        for cases in self.plan['banks'].values():
            bank = RehearsalBank(cases, 'cpu')
            for case_id, case in enumerate(cases):
                ids = torch.tensor([case_id])
                phase = torch.tensor([-1])
                for expected_phase, segment in enumerate(case['segments']):
                    cmd, mode, duration, ids, phase = bank.sample(ids, phase, torch.tensor([False]))
                    self.assertEqual(ids.item(), case_id)
                    self.assertEqual(phase.item(), expected_phase)
                    torch.testing.assert_close(cmd[0], torch.tensor(segment['command']))
                    self.assertEqual(mode.item(), segment['mode'])
                    self.assertEqual(duration.item(), segment['seconds'])
                _, _, _, _, phase = bank.sample(ids, phase, torch.tensor([False]))
                self.assertEqual(phase.item(), 0)

    def test_reset_discards_interrupted_phase_and_all_targets_are_sampled(self):
        torch.manual_seed(9704)
        for cases in self.plan['banks'].values():
            bank = RehearsalBank(cases, 'cpu')
            n = 10000
            ids = torch.zeros(n, dtype=torch.long)
            cmd, mode, duration, ids, phase = bank.sample(ids, torch.ones_like(ids), torch.ones(n, dtype=torch.bool))
            self.assertEqual(set(ids.tolist()), set(range(len(cases))))
            self.assertTrue((phase == 0).all())
            self.assertTrue((cmd == 0).all())
            self.assertTrue((mode == 0).all())
            self.assertTrue((duration == 2).all())


if __name__ == '__main__':
    unittest.main()
