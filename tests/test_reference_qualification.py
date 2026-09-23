"""Reject changed lineage, partial acceptance and reused evaluation seeds."""
from copy import deepcopy
from pathlib import Path
import sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_reference_qualification as m

class ReferenceQualificationTests(unittest.TestCase):
    def test_three_fresh_lineages_and_exact_restart_schedule(self):
        total = 0
        for seed in m.SEEDS:
            parent = None
            for segment, (start, count) in enumerate(((0, 50), (50, 100), (150, 200))):
                spec = m.training_spec(seed, segment, parent)
                self.assertEqual((spec['starting_runner_iteration'], spec['iterations']), (start, count))
                self.assertEqual('--flat_upright_resets' in spec['extra_args'], segment == 2)
                self.assertEqual('--reference_update_probe' in spec['extra_args'], segment == 2)
                self.assertEqual(spec.get('checkpoint'), None if parent is None else parent['final_checkpoint'])
                total += spec['iterations'] * spec['num_envs'] * 24
                parent = {'seed': seed, 'ending_runner_iteration': start + count - 1,
                          'final_checkpoint': f'seed{seed}/model_{start + count - 1}.pt', 'final_checkpoint_sha256': 'hash'}
        self.assertEqual(total, 103219200)
        self.assertEqual(tuple(s for batch in m.BATCHES for s in batch), m.SEEDS)
        self.assertTrue(set(m.SEEDS).isdisjoint(m.base.SEEDS))
        self.assertTrue(set(m.EVALUATIONS.values()).isdisjoint(m.base.EVALUATIONS.values()))

    def test_reject_foreign_parent_and_wrong_restart(self):
        parent = {'seed': 54, 'ending_runner_iteration': 149, 'final_checkpoint': 'model_149.pt', 'final_checkpoint_sha256': 'hash'}
        for seed, segment, value in [(52, 0, None), (54, 0, parent), (54, 2, None), (55, 2, parent),
                                     (54, 1, parent), (54, 2, {**parent, 'ending_runner_iteration': 150})]:
            with self.subTest(seed=seed, segment=segment), self.assertRaises(ValueError):
                m.training_spec(seed, segment, value)

    def test_resume_paths_are_semantic_and_other_recipe_changes_still_fail(self):
        import json, tempfile
        from unittest.mock import patch
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = []
            agents = []
            for seed in (52, 54):
                parent = root / f'parent{seed}'
                current = root / f'current{seed}'
                parent.mkdir(); (current / 'params').mkdir(parents=True)
                checkpoint = parent / 'model_49.pt'; checkpoint.write_bytes(f'weights{seed}'.encode())
                digest = m.sha256(checkpoint)
                (parent / 'manifest.json').write_text(json.dumps({'seed': seed}))
                manifest = current / 'manifest.json'
                manifest.write_text(json.dumps({'seed': seed, 'resume': {'path': str(checkpoint),
                    'sha256': digest, 'load_optimizer': True}}))
                agent = {'seed': seed, 'run_name': str(seed), 'resume': True,
                         'load_run': str(parent), 'load_checkpoint': 'model_49.pt',
                         'algorithm': {'learning_rate': .0001}, 'max_iterations': 100}
                (current / 'params/agent.yaml').write_text(yaml.safe_dump(agent))
                (current / 'params/env.yaml').write_text(yaml.safe_dump({'seed': seed, 'log_dir': str(current), 'dt': .005}))
                runs.append({'seed': seed, 'checkpoint': str(checkpoint), 'checkpoint_sha256': digest,
                             'training_manifest': str(manifest)})
                agents.append(agent)
            def save_agent():
                (Path(runs[1]['training_manifest']).parent / 'params/agent.yaml').write_text(yaml.safe_dump(agents[1]))
            with patch.object(m.base, 'project_file', side_effect=lambda p: Path(p).resolve()):
                self.assertTrue(m.verify_recipe(runs[1], runs[0])['environment_and_agent_match_development'])
                agents[1]['load_run'] = agents[0]['load_run']; save_agent()
                with self.assertRaisesRegex(ValueError, 'own-seed parent'):
                    m.verify_recipe(runs[1], runs[0])
                agents[1]['load_run'] = str(Path(runs[1]['checkpoint']).parent)
                agents[1]['algorithm']['learning_rate'] = .001; save_agent()
                with self.assertRaisesRegex(ValueError, 'algorithm'):
                    m.verify_recipe(runs[1], runs[0])
                agents[1]['algorithm']['learning_rate'] = .0001; save_agent()
                runs[1]['seed'] = 55
                with self.assertRaisesRegex(ValueError, 'own-seed parent'):
                    m.verify_recipe(runs[1], runs[0])

    def test_resume_rejects_quality_failure_or_started_final(self):
        from unittest.mock import patch
        value = {'status': 'failed', 'error': "Recipe differs from successful development agent.yaml: ['load_run']",
                 'evaluations': {}, 'exports': {}}
        for variant in ({**value, 'status': 'stopped_quality_gate'}, {**value, 'batch54_to_350': {}},
                        {**value, 'evaluations': {'seed54_nominal': {}}}, {**value, 'batch56_to_50': {}}):
            with patch.object(m, 'read', return_value=variant), self.assertRaisesRegex(RuntimeError, 'documented'):
                m.validate_completed_prefix([])

    def test_new_evaluation_seed_is_enforced(self):
        from unittest.mock import patch
        summary = {'episodes': 100, 'no_fall_count': 100, 'by_scenario': {
            name: {'pooled_rms_vx_vy_yaw': [.1, .1, .1]} for name, _ in m.base.SCENARIOS}}
        result = {'physical_evidence': {'applied_properties_verified': True,
                  'persistent_through_replay': True, 'variation_applied_verified': True,
                  'properties_sha256': 'physical'}, 'status': 'completed',
                  'physics_steps_completed': 4400, 'policy_sha256': 'policy',
                  'evaluation_seed': m.EVALUATIONS['bounded_v1'], 'num_envs': 100,
                  'physical_profile': {'profile': 'bounded_v1'}, 'cases': [], 'results': [None] * 100,
                  'live_observation_max_error': 0., 'live_action_target_max_error': 0.,
                  'isaac_vs_reference_observation_max_error': 0.,
                  'observation_saturation_mismatch_steps': 0, 'raw_action_saturation_steps': 0}
        with patch.object(m.base, 'summarize', return_value=summary):
            with self.assertRaises(ValueError):
                m.base.verify_evaluation(result, 'policy', 'bounded_v1', [], {})
            self.assertEqual(m.base.verify_evaluation(result, 'policy', 'bounded_v1', [], {},
                             evaluation_seed=m.EVALUATIONS['bounded_v1']), summary)
            result['evaluation_seed'] = m.base.EVALUATIONS['bounded_v1']
            with self.assertRaises(ValueError):
                m.base.verify_evaluation(result, 'policy', 'bounded_v1', [], {},
                                        evaluation_seed=m.EVALUATIONS['bounded_v1'])

    def test_every_seed_profile_and_reference_required(self):
        summary = {'episodes': 100, 'no_fall_count': 100, 'by_scenario': {
            name: {'pooled_rms_vx_vy_yaw': [.1, .1, .1]} for name, _ in m.base.SCENARIOS}}
        results = {name: {p: deepcopy(summary) for p in m.EVALUATIONS}
                   for name in ['reference', 'seed54', 'seed55', 'seed56']}
        self.assertTrue(m.qualification_decision(results)['flat_transfer_gate_passed'])
        for label in results:
            for profile in m.EVALUATIONS:
                bad = deepcopy(results)
                bad[label][profile]['no_fall_count'] = 98
                self.assertFalse(m.qualification_decision(bad)['flat_transfer_gate_passed'])
        for label in results:
            bad = deepcopy(results); del bad[label]
            with self.assertRaises(ValueError): m.qualification_decision(bad)
        bad = deepcopy(results); del bad['seed56']['bounded_v1']
        with self.assertRaises(ValueError): m.qualification_decision(bad)

if __name__ == '__main__':
    unittest.main()
