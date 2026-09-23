import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import run_rough_corridor_preflight as pre
import run_rough_corridor_training as training
import test_rough_precision_tracking as precision_tests


class CorridorProtocolTests(unittest.TestCase):
    def verify(self, terminal=None, manifest_change=None, unrelated=False):
        manifest = dict(status='completed', rough_transfer=True, rough_precision_tracking=True,
            rough_wheel_corridor=True, rough_route_commands=True, rough_tilt_termination=True,
            init_at_random_ep_len=False, num_envs=64, rough_stage=0,
            rough_curriculum={'wheel_corridor_enabled':True},
            reference_transfer=dict(drift_limit=.25, fixed_action_std=.1, critic_warmup_updates=1,
                latest_drift={'raw_action_rms':.02}), flat_bank_drift={'raw_action_rms':.02},
            **{key:{'passed':True} for key in ('precision_tracking_fixture','route_command_fixture',
                'tilt_termination_fixture','wheel_corridor_fixture')})
        if manifest_change: manifest.update(manifest_change)
        before = dict(seed=1, log_dir='old', rewards={name:dict(func='native:'+name,weight=weight,
            params={'std':.5}) for name,weight in (('track_lin_vel_xy_exp',3.),('track_ang_vel_z_exp',1.5))},
            terminations={'tilt':{'func':'preserved'}}, observations={'actor':57},sim={'dt':.005})
        after = copy.deepcopy(before)
        for term in after['rewards'].values(): term['params']['std']=.25
        after['terminations']['rough_wheel_corridor'] = terminal or dict(
            func='rough_wheel_corridor:wheel_corridor_terminal',params={},time_out=False)
        if unrelated: after['sim']['dt']=.01
        agent = dict(algorithm={'lr':.0001},policy={'std':.1},obs_groups={'actor':['policy']},
                     num_steps_per_env=24,clip_actions=None)
        def text(path, *args, **kwargs):
            return yaml.safe_dump(agent if path.name=='agent.yaml' else
                                  before if 'baseline' in path.parts else after)
        path = pre.ROOT/'logs/new/manifest.json'
        with patch.object(pre,'read',return_value=manifest), patch.object(pre,'sha256',return_value='a'*64), \
             patch.object(pre,'historical_route_manifest',return_value=pre.ROOT/'logs/baseline/manifest.json'), \
             patch.object(Path,'read_text',text):
            return pre.verify_corridor_run(path,smoke=True)

    def test_only_declared_true_terminal_passes(self):
        self.assertTrue(self.verify()['wheel_corridor_terminal'])
        for change in ({'time_out':True},{'params':{'limit':2.}}, {'func':'wrong:terminal'}):
            term=dict(func='rough_wheel_corridor:wheel_corridor_terminal',params={},time_out=False,**{})
            term.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): self.verify(terminal=term)
        with self.assertRaises(ValueError): self.verify(unrelated=True)

    def test_missing_constraint_state_or_native_fixture_fails(self):
        for change in ({'rough_wheel_corridor':False},{'rough_curriculum':{}},
                       {'wheel_corridor_fixture':{'passed':False}}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.verify(manifest_change=change)

    def test_resume_cannot_add_or_remove_constraint(self):
        helper = precision_tests.RoughPrecisionParserTests()
        for enabled in (False,True):
            for requested in (False,True):
                parent = helper.parent(True); parent['rough_wheel_corridor']=enabled
                argv=helper.rough()+['--rough_precision_tracking','--resume','logs/fake/model_1.pt']
                if requested: argv+=['--rough_wheel_corridor']
                if enabled==requested: self.assertEqual(helper.parse(argv,parent).rough_wheel_corridor,requested)
                else:
                    with self.assertRaises(SystemExit): helper.parse(argv,parent)

    def test_new_pair_has_exact_budget_and_constraint_every_stage(self):
        self.assertEqual(training.SEEDS,(63,64)); self.assertEqual(training.BUDGET,(50,100,200))
        for seed in training.SEEDS:
            for stage,updates in enumerate(training.BUDGET):
                previous=None if stage==0 else dict(seed=seed,checkpoint=f'logs/s{seed}/model_{(49,149)[stage-1]}.pt',checkpoint_sha256='a'*64)
                with patch.object(training,'sha256',return_value='a'*64):
                    _,command=training.training_command(seed,stage,previous)
                self.assertIn('--rough_wheel_corridor',command)
                self.assertEqual(command[command.index('--max_iterations')+1],str(updates))
        with self.assertRaises(ValueError): training.training_command(61,0)


if __name__=='__main__': unittest.main()
