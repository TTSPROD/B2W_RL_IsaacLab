"""Versioned training environment: physics-tick safety and exclusive true terminals."""
import torch
from isaaclab.envs import ManagerBasedRLEnv
from b2w_core_stage3_cfg import core_stage3_timeout
from b2w_retention_cfg import retained_terrain_curriculum
from isaaclab_tasks.manager_based.locomotion.velocity.mdp.terminations import terrain_out_of_bounds
from stair_curriculum_monitor import StairMonitor, safety_flags, exclusive_timeout


def safety_terminal(env):
    monitor=getattr(env,'monitor',None)
    return monitor.flags.any(dim=1) if monitor else torch.zeros(env.num_envs,device=env.device,dtype=torch.bool)


def safe_timeout(env):
    return exclusive_timeout(core_stage3_timeout(env),safety_terminal(env))


def safe_bounds(env,asset_cfg,distance_buffer):
    return exclusive_timeout(terrain_out_of_bounds(env,asset_cfg=asset_cfg,distance_buffer=distance_buffer),safety_terminal(env))


def stair_curriculum(env,env_ids):
    retained_terrain_curriculum(env,env_ids)
    if hasattr(env,'monitor'):env.monitor.curriculum(env_ids)
    return env.scene.terrain.terrain_levels.float().mean()


class CurriculumEnv(ManagerBasedRLEnv):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from check_policy_contract import load_contract
        self.contract=load_contract()
        self.robot=self.scene['robot'];self.contact=self.scene['contact_forces']
        self.joint_ids,names=self.robot.find_joints(self.contract['joint_names'],preserve_order=True)
        assert names==self.contract['joint_names']
        self.protected=self.contact.find_bodies(['base_link','.*_hip'])[0]
        wheels=['FR_foot','FL_foot','RR_foot','RL_foot']
        self.wheel_ids=self.robot.find_bodies(wheels,preserve_order=True)[0]
        self.wheel_contact_ids=self.contact.find_bodies(wheels,preserve_order=True)[0]
        assert len(self.protected)==5 and abs(self.physics_dt-.005)<1e-9
        command=self.command_manager.get_term('base_velocity')
        self.monitor=StairMonitor(self,command.plan)
        command.training_profile={**command.training_profile,'adaptive':command.plan['arms'][command.training_profile['arm']]['adaptive']}
        self.stepping=False
        update=self.scene.update
        def observed_update(dt):
            update(dt)
            if self.stepping:self._physics_safety()
        self.scene.update=observed_update
        compute=self.reward_manager.compute
        def observed_reward(dt):
            reward=compute(dt)
            velocity=torch.cat((self.robot.data.root_lin_vel_b[:,:2],self.robot.data.root_ang_vel_b[:,2:3]),dim=1)
            wheel_xy=self.robot.data.body_pos_w[:,self.wheel_ids,:2]-self.scene.env_origins[:,None,:2]
            radius=wheel_xy.abs().amax(dim=2)
            # Pinned 8 m tile, 1 m border, 0.3 m tread: innermost platform edge is 0.6 m.
            loaded=self.contact.data.net_forces_w[:,self.wheel_contact_ids,2]>5.
            exposure=(((radius>.6)&(radius<3.))&loaded).any(dim=1)
            crossed=(self.robot.data.root_pos_w[:,:2]-self.scene.env_origins[:,:2]).abs().amax(dim=1)>=3.
            self.monitor.record(reward,velocity,exposure,crossed)
            return reward
        self.reward_manager.compute=observed_reward
        self.initialized_levels=False

    def _physics_safety(self):
        d=self.robot.data
        forces=self.contact.data.net_forces_w[:,self.protected].norm(dim=-1).amax(dim=1)
        flags=safety_flags(d.joint_pos[:,self.joint_ids],d.joint_vel[:,self.joint_ids],
            d.applied_torque[:,self.joint_ids],d.projected_gravity_b,forces,d.root_state_w,
            self.action_manager.action,d.joint_pos_limits[:,self.joint_ids[:12]])
        self.monitor.flags |= flags
        if flags[:,0].any():raise FloatingPointError('Non-finite physics/state/action; abort training')

    def step(self,action):
        if not torch.isfinite(action).all():raise FloatingPointError('Non-finite policy action')
        self.monitor.begin();self.stepping=True
        try:return super().step(action)
        finally:self.stepping=False

    def _reset_idx(self,ids):
        monitor=getattr(self,'monitor',None)
        if monitor is not None and not self.initialized_levels:
            command=monitor.command
            if command.training_profile['adaptive']:
                target=command.target_masks['stairs_up']|command.target_masks['stairs_down']
                selected=target.nonzero().flatten()
                self.scene.terrain.terrain_levels[selected]%=3
                self.scene.terrain.update_env_origins(selected,torch.zeros_like(selected),torch.zeros_like(selected))
            self.initialized_levels=True
        super()._reset_idx(ids)
        if monitor is not None:monitor.reset(ids)


def install_coverage(env):
    return env.monitor


def preflight(runner,plan):
    """Exercise actual environment/wrapper and restored deterministic actor without PPO updates."""
    from run_support import write_json
    env=runner.env.unwrapped
    counts=torch.zeros(2,device=env.device,dtype=torch.long)
    with torch.inference_mode():
        obs=runner.env.get_observations()
        for step in range(3600):
            actions=runner.alg.policy.act_inference(obs)
            obs,reward,done,extra=runner.env.step(actions)
            assert torch.isfinite(obs['policy']).all() and torch.isfinite(reward).all()
            assert not (env.reset_terminated & extra['time_outs']).any()
            counts+=torch.stack((env.reset_terminated.sum(),env.reset_time_outs.sum()))
            if step%500==0:print('SAFETY_PREFLIGHT_STEP',step,'/3600',flush=True)
        # Actual simultaneous time-limit/safety boundary, without modifying robot dynamics.
        env.monitor.flags[0,3]=True
        env.episode_length_buf[0]=3500
        env.termination_manager.compute()
        assert env.termination_manager.terminated[0] and not env.termination_manager.time_outs[0]
        env.reset()
    write_json(runner.run_path/'safety_preflight.json',{'status':'passed','steps':3600,'updates':0,
        'safety_terminations':int(counts[0]),'timeouts':int(counts[1]),'terminal_wins_timeout':True,
        'coverage':env.monitor.snapshot()})
