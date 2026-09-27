"""A retained actor must not count as repairing its own known failures."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from report_repair501_validation import restoration_summary


class RestorationCriteriaTests(unittest.TestCase):
    def setUp(self):
        self.prior=json.loads((ROOT/'docs/results/evidence/fullcycle_24499_20260927/summary.json').read_text())
        self.training=json.loads((ROOT/'configs/24499_repair501_20260927.json').read_text())
        self.rows=copy.deepcopy(self.prior['rows'])
        for row in self.rows: row['policies']['25000']=copy.deepcopy(row['policies']['24499'])

    def test_unchanged_actor_repairs_none_of_its_known_failures(self):
        result=restoration_summary(self.rows,self.training,self.prior)
        self.assertEqual(result['target_count'],92)
        self.assertEqual(result['restored_full_zero'],0)

    def test_every_gate_is_required_even_when_full_success_recovers(self):
        for row in self.rows:
            values=row['policies']; candidate=values['25000']
            for key in ('success','complete_zero_segments_pass','exposed_zero_success'):
                candidate[key]=max(values[p][key] for p in ('21999','23999'))
            candidate['unsafe']=0
        self.assertEqual(restoration_summary(self.rows,self.training,self.prior)['restored_full_zero'],92)
        target=self.training['target_rows'][0]
        row=next(r for r in self.rows if (r['terrain'],r['case'])==(target['terrain'],target['case']))
        row['policies']['25000']['unsafe']=1
        self.assertEqual(restoration_summary(self.rows,self.training,self.prior)['restored_full_zero'],91)


if __name__=='__main__': unittest.main()
