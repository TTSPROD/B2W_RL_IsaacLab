import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import torch
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import schedule_pilot_contract
from schedule_pilot_contract import load_plan,audit_agent,preflight_decision
from plan_fixtures import plan as fixture_plan
from run_support import ROOT,read_json,write_json,sha256


class SchedulePilotTests(unittest.TestCase):
    def setUp(self):
        self.spec=fixture_plan('24650_upright_schedule_ab_20261001.json')
        reset=fixture_plan('24650_reset_ab_20261001.json')
        for name,value in (('load_spec',self.spec),('reset_plan',reset)):
            patcher=patch.object(schedule_pilot_contract,name,return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_schedule_gain_cannot_override_parent_retention_floor(self):
        from schedule_pilot_contract import decision
        floors=self.spec['retention']['per_cell_success_minimum'];rows=[]
        for policy in ('24650','scheduleadaptive_24949','schedulefixed_24949'):
            for cell,floor in floors.items():
                terrain,case=cell.split('/')
                for seed in range(5):
                    segments=[]
                    if case in ('lateral','yaw'):
                        for sign in (1,-1):
                            command=[0.,0.,0.];command[1 if case=='lateral' else 2]=sign*.3
                            segments.append({'command':command,
                                ('linear_response_ratio' if case=='lateral' else 'angular_response_ratio'):.7})
                    rows.append({'policy':policy,'terrain':terrain,'case':case,'seed':seed,
                        'covered_scenario_success':seed<floor,'segments':segments,
                        'safety':{'unsafe_flags':[],'torque_saturation_fraction':[0.]*16},
                        'terrain_exposure':{'progress_ratio':.95 if policy=='schedulefixed_24949' else .85}})
        self.assertTrue(decision(rows)['retention_pass'])
        self.assertTrue(decision(rows)['hypothesis_supported'])
        next(r for r in rows if r['policy']=='schedulefixed_24949' and
             r['terrain']=='stairs_down_18' and r['case']=='traverse_0.7')['covered_scenario_success']=False
        out=decision(rows)
        self.assertFalse(out['retention_pass'])
        self.assertFalse(out['hypothesis_supported'])

    def test_only_native_schedule_diff_is_allowed(self):
        agent=yaml.safe_load((ROOT/'policies/local/core_24650/agent.yaml').read_text())
        agent.update(seed=9911,max_iterations=300)
        agent['algorithm']['schedule']='fixed'
        audit_agent(agent,'fixed')
        agent['algorithm']['entropy_coef']*=2
        with self.assertRaisesRegex(ValueError,'Undeclared'):audit_agent(agent,'fixed')
        from evaluation_policy import policy_id
        from job_manager import recipe
        self.assertEqual(policy_id('schedulefixed_24949'),'schedulefixed_24949')
        self.assertEqual(recipe({'entrypoint':'scripts/run_schedule_pilot.py','arguments':[]}),
                         ('scripts/run_schedule_pilot.py',[]))
        plan=load_plan()
        self.assertEqual(set(plan['arms']),{'adaptive','fixed'})
        self.assertFalse(plan['arms']['adaptive']['adaptive'])
        self.assertFalse(plan['arms']['fixed']['adaptive'])

    def test_preflight_rejects_invalid_reset_and_missing_zero(self):
        from b2w_core_stage3_sampling import build_banks
        coverage={n:{'segment_attempts':[[1]*len(c['segments']) for c in bank],
                     'segment_completions':[[1]*len(c['segments']) for c in bank]}
                  for n,bank in build_banks(load_plan()).items()}
        item={'status':'completed','updates':0,'policy_steps':3600,'parent_state_exact':True,
              'adam_state_exact':True,'terminal_overrides_timeout':True,'runtime':{'gpu':'same'},
              'runner_source_sha256':'same','coverage':coverage,
              'reset_diagnostics':{'initial_invalid':{'tilt':0,'nonfinite':0,'hard_joint':0},'stale_contact_resets':0}}
        rows={a:deepcopy(item) for a in ('adaptive','fixed')}
        self.assertTrue(preflight_decision(rows)['train_allowed'])
        rows['fixed']['reset_diagnostics']['initial_invalid']['tilt']=1
        self.assertFalse(preflight_decision(rows)['train_allowed'])
        rows['fixed']['reset_diagnostics']['initial_invalid']['tilt']=0
        rows['fixed']['coverage']['stairs_down']['segment_completions']=[[0]*len(r) for r in coverage['stairs_down']['segment_completions']]
        self.assertFalse(preflight_decision(rows)['train_allowed'])

    @unittest.skipUnless(importlib.util.find_spec('tensorboard'), 'tensorboard integration is optional in CPU runtime')
    def test_completion_rejects_drift_in_logged_fixed_learning_rate(self):
        import schedule_completion as completion
        from torch.utils.tensorboard import SummaryWriter
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();job=root/'job';folder=job/'training_/fixed'
            run=root/'logs/rsl_rl/fixed';folder.mkdir(parents=True);(run/'params').mkdir(parents=True)
            parent=root/'policies/local/core_24650';parent.mkdir(parents=True)
            agent=yaml.safe_load((ROOT/'policies/local/core_24650/agent.yaml').read_text())
            agent.update(seed=9911,max_iterations=300,experiment_name='b2w_24650_schedule_fixed_9911')
            agent['algorithm']['schedule']='fixed'
            (run/'params/agent.yaml').write_text(yaml.safe_dump(agent),encoding='utf-8')
            plan=load_plan()
            original={'iter':24650,'model_state_dict':{'weight':torch.ones(1)},
                'optimizer_state_dict':{'state':{0:{'step':torch.tensor(100.)}},'param_groups':[{'lr':1e-5}]}}
            final=deepcopy(original);final['iter']=24949;final['optimizer_state_dict']['state'][0]['step']=torch.tensor(6100.)
            torch.save(original,parent/'model_24650.pt');torch.save(final,run/'model_24949.pt')
            write_json(job/'training_run.json',{'path':'logs/rsl_rl/fixed'})
            (folder/'reset_environment.yaml').write_text('test: true\n',encoding='utf-8')
            write_json(folder/'config_audit.json',{'status':'passed','arm':'fixed',
                'environment_sha256':sha256(folder/'reset_environment.yaml')})
            write_json(folder/'runtime_sources.json',{})
            progress={'status':'running','policy_steps':7200,'completed_updates':300,'target_updates':300}
            write_json(folder/'progress.json',progress);write_json(run/'progress.json',progress)
            (job/'pilot_fixed_stdout.log').write_text(''.join(f'Learning iteration {n}/24950\n' for n in range(24650,24950))+
                'Total timesteps: 29491200\nTraining time: 1200 seconds\n',encoding='utf-8')
            with SummaryWriter(str(run)) as writer:
                for n in range(300):writer.add_scalar('Loss/learning_rate',1e-5 if n!=100 else 1e-3,n)
            with patch.object(completion,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'Fixed learning rate drift'):
                    completion.validate_training_completion(job,'fixed',plan,0)


if __name__=='__main__':unittest.main()
