import copy, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from run_rough_requested_continuation import ROOT, PRIOR, select_parents, training_command


class RequestedRoughContinuationTests(unittest.TestCase):
    def setUp(self):
        self.prior = json.loads(PRIOR.read_text(encoding='utf-8'))

    def test_only_both_own_completed150_parents_are_selected(self):
        parents = select_parents(self.prior)
        self.assertEqual(set(parents), {57, 58})
        for seed in parents:
            self.assertEqual(parents[seed]['seed'], seed)
            self.assertEqual(Path(parents[seed]['checkpoint']).name, 'model_149.pt')

    def test_technical_stop_missing_cases_and_flat_failure_are_not_covered(self):
        variants = []
        changed = copy.deepcopy(self.prior); changed['status'] = 'failed'; variants.append(changed)
        changed = copy.deepcopy(self.prior); changed['stopped_at'] = 350; variants.append(changed)
        changed = copy.deepcopy(self.prior); changed['milestones'][0]['flat']['57']['nominal']['passed'] = False; variants.append(changed)
        changed = copy.deepcopy(self.prior); changed['milestones'][0]['rough']['58'].pop('blocks/0/nominal'); variants.append(changed)
        changed = copy.deepcopy(self.prior); changed['milestones'][0]['training']['57']['seed'] = 58; variants.append(changed)
        changed = copy.deepcopy(self.prior); changed['milestones'][0]['training']['58']['checkpoint'] = 'logs/model_100.pt'; variants.append(changed)
        for index, value in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                select_parents(value)

    def test_command_has_exact_remaining_budget_and_preserves_own_optimizer_resume(self):
        for seed, parent in select_parents(self.prior).items():
            label, cmd = training_command(seed, parent)
            self.assertIn('--rough_tilt_termination', cmd)
            self.assertIn(f's{seed}_stage2', label)
            for flag, expected in [('--seed', str(seed)), ('--max_iterations', '200'),
                                   ('--num_envs', '4096'), ('--rough_stage', '2'),
                                   ('--reference_drift_limit', '.25'), ('--critic_warmup_updates', '50'),
                                   ('--resume', str(ROOT/parent['checkpoint']))]:
                self.assertEqual(cmd[cmd.index(flag)+1], expected)
            with self.assertRaises(ValueError):
                training_command(58 if seed == 57 else 57, parent)


if __name__ == '__main__':
    unittest.main()
