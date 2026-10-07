import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reset_diagnostics import ResetDiagnostics
from reset_pilot_contract import load_plan,preflight_decision
from b2w_core_stage3_sampling import build_banks
from evaluation_policy import policy_id,validate_export


class ResetPilotTests(unittest.TestCase):
    def test_initial_invalid_and_first_event_age_are_distinct(self):
        n=3;ids=torch.arange(n);m=ResetDiagnostics({'all':ids>=0},'cpu',.005)
        g=torch.tensor([[0.,0.,-1.],[0.,0.,1.],[0.,0.,-1.]])
        q=torch.zeros(n,16);ranges=torch.tensor([[[-1.,1.]]*12]*n)
        root=torch.zeros(n,13);force=torch.zeros(n)
        m.reset(ids,g,q,ranges,root,force)
        command=SimpleNamespace(rehearsal_case=ids*0,rehearsal_phase=ids*0)
        flags=torch.zeros(n,4,dtype=torch.bool);flags[1,1]=True
        m.tick(flags,command)
        for _ in range(25):m.tick(flags,command)
        flags[2,3]=True;m.tick(flags,command)
        d=m.snapshot()
        self.assertEqual(d['initial_invalid']['tilt'],1)
        self.assertEqual(d['first_events_by_cohort']['all'][0][1],1)
        self.assertEqual(d['first_events_by_cohort']['all'][1][3],1)
        self.assertEqual(sum(sum(r) for r in d['first_events_by_cohort']['all']),2)
        m.reset(torch.tensor([1]),g,q,ranges,root,force);m.tick(flags,command)
        self.assertEqual(m.snapshot()['first_events_by_cohort']['all'][0][1],2)

    def test_preflight_blocks_invalid_or_inaccessible_long_zero(self):
        plan=load_plan();coverage={}
        for name,bank in build_banks(plan).items():
            coverage[name]={'segment_attempts':[[1]*len(c['segments']) for c in bank],
                            'segment_completions':[[1]*len(c['segments']) for c in bank]}
        a={'reset_diagnostics':{'initial_invalid':{'tilt':20},'early_tilt_per_env_second':.2}}
        b={'reset_diagnostics':{'initial_invalid':{'tilt':0,'nonfinite':0,'hard_joint':0},
            'early_tilt_per_env_second':.01,'stale_contact_resets':0},'coverage':coverage}
        self.assertTrue(preflight_decision(a,b)['train_allowed'])
        b['reset_diagnostics']['initial_invalid']['tilt']=1
        self.assertFalse(preflight_decision(a,b)['train_allowed'])
        b['reset_diagnostics']['initial_invalid']['tilt']=0
        b['coverage']['stairs_up']['segment_completions']=[[0]*len(c['segments']) for c in build_banks(plan)['stairs_up']]
        self.assertFalse(preflight_decision(a,b)['train_allowed'])

    def test_new_actor_identity_and_managed_recipe(self):
        from job_manager import recipe
        self.assertEqual(policy_id('resetupright_24949'),'resetupright_24949')
        self.assertEqual(recipe({'entrypoint':'scripts/run_reset_pilot.py','arguments':[]}),
                         ('scripts/run_reset_pilot.py',[]))
        plan=load_plan()
        self.assertEqual(plan['final_checkpoint_iteration'],24650+plan['updates']-1)
        self.assertFalse(plan['custom_lr_cap'])

    def test_completion_after_kit_exit_requires_weights_adam_and_full_log(self):
        import yaml
        import run_reset_pilot as workflow
        from run_support import write_json,sha256
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();job=root/'job';folder=job/'training_/control'
            run=root/'logs/rsl_rl/control';folder.mkdir(parents=True);(run/'params').mkdir(parents=True)
            parent=root/'policies/local/core_24650';parent.mkdir(parents=True)
            algorithm={'num_learning_epochs':5,'num_mini_batches':4}
            agent={'algorithm':algorithm,'policy':{'test':True},'class_name':'OnPolicyRunner',
                'num_steps_per_env':24,'max_iterations':300,'seed':9910,
                'experiment_name':'b2w_24650_reset_control_9910'}
            (run/'params/agent.yaml').write_text(yaml.safe_dump(agent),encoding='utf-8')
            (parent/'agent.yaml').write_text(yaml.safe_dump(agent),encoding='utf-8')
            plan={'updates':300,'seed':9910,'num_envs':4096,'final_checkpoint_iteration':24949,
                'parent_checkpoint':'policies/local/core_24650/model_24650.pt'}
            original={'iter':24650,'model_state_dict':{'weight':torch.ones(1)},
                'optimizer_state_dict':{'state':{0:{'step':torch.tensor(100.)}}}}
            final={'iter':24949,'model_state_dict':{'weight':torch.ones(1)},
                'optimizer_state_dict':{'state':{0:{'step':torch.tensor(6100.)}}}}
            torch.save(original,parent/'model_24650.pt');torch.save(final,run/'model_24949.pt')
            write_json(job/'training_run.json',{'path':'logs/rsl_rl/control'})
            (folder/'reset_environment.yaml').write_text('test: true\n',encoding='utf-8')
            write_json(folder/'config_audit.json',{'status':'passed','arm':'control',
                'environment_sha256':sha256(folder/'reset_environment.yaml')})
            write_json(folder/'runtime_sources.json',{'standard_runner':True})
            progress={'status':'running','policy_steps':7200,'completed_updates':300,'target_updates':300}
            write_json(folder/'progress.json',progress);write_json(run/'progress.json',{**progress,'status':'failed'})
            log=''.join(f'Learning iteration {n}/24950\n' for n in range(24650,24950))
            log+='Total timesteps: 29491200\nTraining time: 1200 seconds\n'
            (job/'pilot_control_stdout.log').write_text(log,encoding='utf-8')
            with patch.object(workflow,'ROOT',root):
                checkpoint,receipt=workflow.validate_training_completion(job,'control',plan,0)
                self.assertEqual(checkpoint,run/'model_24949.pt')
                self.assertEqual(receipt['progress']['status'],'completed')
                self.assertEqual(receipt['adam_updates_per_parameter'],6000)
                self.assertEqual(workflow.read_json(folder/'progress.json')['status'],'running')
                with self.assertRaisesRegex(ValueError,'exit successfully'):
                    workflow.validate_training_completion(job,'control',plan,1)
                final['optimizer_state_dict']['state'][0]['step']=torch.tensor(6080.)
                torch.save(final,run/'model_24949.pt')
                with self.assertRaisesRegex(ValueError,'Adam update'):
                    workflow.validate_training_completion(job,'control',plan,0)
                torch.save(original,run/'model_24949.pt')
                with self.assertRaisesRegex(ValueError,'Invalid final checkpoint'):
                    workflow.validate_training_completion(job,'control',plan,0)
                (job/'pilot_control_stdout.log').write_text(log.replace('Training time:','Incomplete:'),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'runner log'):
                    workflow.validate_training_completion(job,'control',plan,0)


if __name__=='__main__':unittest.main()
