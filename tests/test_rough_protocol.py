import copy,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rough_curriculum import promotion,SafeTraversalCurriculum
from rough_evaluation import make_cases,digest,summarize


class Scene(dict):
    def update(self,dt):pass


def fake_env(n=100):
    state=torch.zeros(n,13);state[:,3]=1
    data=SimpleNamespace(root_state_w=state,root_pos_w=state[:,:3],root_quat_w=state[:,3:7],
                         projected_gravity_b=torch.tensor([[0.,0.,-1.]]).expand(n,-1),joint_pos=torch.zeros(n,16),joint_vel=torch.zeros(n,16))
    forces=torch.zeros(n,5,3)
    sensor=SimpleNamespace(body_names=['base_link','FR_foot','FL_foot','RR_foot','RL_foot'],data=SimpleNamespace(net_forces_w=forces))
    origins=torch.zeros(3,10,3);origins[1,:,0]=12;origins[2,:,0]=24
    terrain=SimpleNamespace(terrain_types=torch.full((n,),3,dtype=torch.long),terrain_levels=torch.zeros(n,dtype=torch.long),
                            terrain_origins=origins,env_origins=torch.zeros(n,3))
    scene=Scene(robot=SimpleNamespace(data=data),contact_forces=sensor);scene.terrain=terrain;scene.env_origins=terrain.env_origins
    command=torch.zeros(n,3)
    env=SimpleNamespace(scene=scene,device='cpu',num_envs=n,_sim_step_counter=0,command_manager=SimpleNamespace(get_command=lambda _:command))
    env.unwrapped=env
    def reset(ids):data.root_pos_w[ids]=scene.env_origins[ids]
    env._reset_idx=reset
    return env,command,data,forces


class RoughProtocolTests(unittest.TestCase):
    def test_thresholds_caps_and_minimum_evidence(self):
        self.assertEqual(promotion(0,2,99,99),0)
        self.assertEqual(promotion(0,2,100,80),1)
        self.assertEqual(promotion(1,2,100,60),0)
        self.assertEqual(promotion(1,2,100,79),1)
        self.assertEqual(promotion(0,0,100,100),0)
        self.assertEqual(promotion(2,2,100,100),2)

    def test_safe_promotion_and_resume_restore(self):
        env,command,data,force=fake_env();c=SafeTraversalCurriculum(env,cap=1)
        command[:,0]=1;data.root_pos_w[:,0]+=1;env._sim_step_counter+=1;c.update(1.)
        env._reset_idx(torch.arange(100))
        self.assertEqual(c.levels[1],1);self.assertTrue((env.scene.terrain.terrain_levels==1).all())
        snap=c.snapshot();c.close()
        restored=SafeTraversalCurriculum(env,cap=2,state=snap)
        self.assertEqual(restored.levels[1],1);self.assertEqual(restored.total_successes[1],100)

    def test_sticky_contact_prevents_promotion(self):
        env,command,data,force=fake_env();c=SafeTraversalCurriculum(env,cap=1)
        command[:,0]=1;data.root_pos_w[:,0]+=1;force[:,0,2]=1.01;env._sim_step_counter+=1;c.update(1.)
        force.zero_();env._reset_idx(torch.arange(100))
        self.assertEqual(c.levels[1],0);self.assertEqual(c.total_successes[1],0)

    def test_lateral_escape_and_pure_yaw_cannot_promote(self):
        env,command,data,force=fake_env();c=SafeTraversalCurriculum(env,cap=1)
        command[:,0]=1;data.root_pos_w[:,1]+=1;env._sim_step_counter+=1;c.update(1.)
        env._reset_idx(torch.arange(100));self.assertEqual(c.total_successes[1],0)
        command.zero_();command[:,2]=1;env._sim_step_counter+=1;c.update(1.)
        env._reset_idx(torch.arange(100));self.assertEqual(c.total_episodes[1],100)

    def test_command_segments_integrate_separately(self):
        env,command,data,force=fake_env(1);c=SafeTraversalCurriculum(env,cap=1)
        command[:,0]=1;data.root_pos_w[:,0]+=1;env._sim_step_counter+=1;c.update(1.)
        command[:,0]=0;command[:,1]=1;data.root_pos_w[:,1]+=1;env._sim_step_counter+=1;c.update(1.)
        self.assertEqual(float(c.progress[0]),2.);self.assertEqual(float(c.expected[0]),2.)

    def test_frozen_cases_balance_and_per_kind_gate(self):
        cases=make_cases('random',0,'nominal')
        self.assertEqual(digest(cases),digest(make_cases('random',0,'nominal')))
        self.assertEqual(cases,json.loads(json.dumps(cases)))
        self.assertNotEqual(digest(cases),digest(make_cases('random',0,'bounded_v1')))
        self.assertEqual([sum(c['kind']==k for c in cases) for k in ('traverse','stand','turn')],[60,20,20])
        rows=[dict(index=i,success=True,squared_error_sum=[1.,1.,1.],measurement_steps=100) for i in range(100)]
        self.assertTrue(summarize(cases,rows)['passed'])
        with self.assertRaises(ValueError):summarize(cases,rows[::-1])
        invalid=copy.deepcopy(rows);invalid[0]['squared_error_sum'][0]=float('nan')
        with self.assertRaises(ValueError):summarize(cases,invalid)
        rows[80]['success']=rows[81]['success']=False
        result=summarize(cases,rows)
        self.assertEqual(result['success'],98);self.assertFalse(result['passed'])


if __name__=='__main__':unittest.main()
