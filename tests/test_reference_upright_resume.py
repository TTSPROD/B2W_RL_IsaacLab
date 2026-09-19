"""Continuation preserves budget, guard and all MDP fields except reset orientation."""
from pathlib import Path
from copy import deepcopy
import sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_reference_upright_resume as m

class UprightResumeTests(unittest.TestCase):
    def test_original_parent_and_remaining_budget(self):
        parent = {'seed': 53, 'ending_runner_iteration': 149,
                  'final_checkpoint': 'model_149.pt', 'final_checkpoint_sha256': 'digest'}
        spec = m.training_spec(parent)
        self.assertEqual((spec['starting_runner_iteration'], spec['iterations']), (150, 200))
        self.assertEqual(spec['num_envs'], 4096)
        self.assertTrue(spec['expected_manifest']['flat_upright_resets'])
        flags = spec['extra_args']
        self.assertIn('--flat_upright_resets', flags)
        self.assertIn('--reference_update_probe', flags)
        self.assertEqual(flags[flags.index('--reference_drift_limit') + 1], '0.25')
        self.assertNotIn('--undesired_contact_weight', flags)
        for bad in ({**parent, 'seed': 49}, {**parent, 'ending_runner_iteration': 150}):
            with self.assertRaises(ValueError):
                m.training_spec(bad)

    def test_config_comparison_rejects_extra_physics_or_ppo_change(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before_dir, after_dir = root / 'before', root / 'after'
            for directory in (before_dir, after_dir):
                (directory / 'params').mkdir(parents=True)
            cfg = {'events': {'randomize_reset_base': {'params': {
                'pose_range': {'roll': [-3.14, 3.14], 'pitch': [-3.14, 3.14], 'yaw': [-3.14, 3.14]},
                'velocity_range': {'x': [-.5, .5]}}}}, 'physics': {'dt': .005}, 'log_dir': 'old'}
            variant = deepcopy(cfg)
            variant['events']['randomize_reset_base']['params']['pose_range'].update(roll=[-.1, .1], pitch=[-.1, .1])
            variant['log_dir'] = 'new'
            agent = {'algorithm': {'learning_rate': .0001}, 'policy': {'init_noise_std': .1},
                     'obs_groups': {'policy': ['policy']}, 'num_steps_per_env': 24, 'clip_actions': None}
            for directory, env in ((before_dir, cfg), (after_dir, variant)):
                (directory / 'params/env.yaml').write_text(yaml.safe_dump(env), encoding='utf-8')
                (directory / 'params/agent.yaml').write_text(yaml.safe_dump(agent), encoding='utf-8')
            run = {'training_manifest': str(after_dir / 'manifest.json'), 'checkpoint': str(before_dir / 'model_149.pt')}
            with patch.object(m.original, 'project_file', side_effect=Path):
                self.assertTrue(m.verify_reset_only(run)['ppo_preserved'])
                variant['physics']['dt'] = .01
                (after_dir / 'params/env.yaml').write_text(yaml.safe_dump(variant), encoding='utf-8')
                with self.assertRaises(ValueError):
                    m.verify_reset_only(run)
                variant['physics']['dt'] = .005
                (after_dir / 'params/env.yaml').write_text(yaml.safe_dump(variant), encoding='utf-8')
                agent['algorithm']['learning_rate'] = .001
                (after_dir / 'params/agent.yaml').write_text(yaml.safe_dump(agent), encoding='utf-8')
                with self.assertRaises(ValueError):
                    m.verify_reset_only(run)

if __name__ == '__main__':
    unittest.main()

