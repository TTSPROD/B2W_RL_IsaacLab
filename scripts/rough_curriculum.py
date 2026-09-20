"""Safe per-family Rough curriculum; passive physics telemetry, unchanged rewards/terminations."""
from __future__ import annotations


def promotion(level, cap, episodes, successes):
    if level not in range(3) or cap not in range(3) or level > cap or not 0 <= successes <= episodes:
        raise ValueError('Invalid curriculum counters')
    if episodes < 100: return level
    rate = successes / episodes
    return min(cap, level+1) if rate >= .8 else max(0, level-1) if rate <= .6 else level


class SafeTraversalCurriculum:
    """Measure before auto-reset; command directions are integrated at each physics step."""
    def __init__(self, env, cap=0, state=None):
        import torch
        self.t = torch; self.env = env.unwrapped; self.robot = self.env.scene['robot']
        self.sensor = self.env.scene['contact_forces']; self.terrain = self.env.scene.terrain
        self.forbidden = [i for i,n in enumerate(self.sensor.body_names) if not n.endswith('_foot')]
        if len(self.sensor.body_names)-len(self.forbidden)!=4: raise ValueError('Invalid wheel contact map')
        self.family = torch.tensor([0,0,0,1,1,1,2,3,4,4],device=self.env.device)[self.terrain.terrain_types]
        self.names=('flat','random','slope_up','slope_down','blocks')
        self.cap=cap; self.levels=[0]*5; self.windows=[[0,0] for _ in range(5)]; self.history=[]
        self.total_episodes=[0]*5; self.total_successes=[0]*5
        if state:
            if state['cap']>cap: raise ValueError('Curriculum cap cannot regress')
            self.levels=list(state['levels']);self.windows=[list(x) for x in state['windows']]
            self.history=list(state['history']);self.total_episodes=list(state['total_episodes']);self.total_successes=list(state['total_successes'])
        n=self.env.num_envs; kwargs=dict(device=self.env.device)
        self.failed=torch.zeros(n,dtype=torch.bool,**kwargs)
        self.nonfinite=torch.zeros(n,dtype=torch.bool,**kwargs)
        self.tilt_failed=torch.zeros(n,dtype=torch.bool,**kwargs)
        self.tilt_terminal_count=0
        self.expected=torch.zeros(n,**kwargs);self.progress=torch.zeros(n,**kwargs);self.tilt_time=torch.zeros(n,**kwargs)
        self.previous=self.robot.data.root_pos_w[:,:2].clone();self.ticks=0
        self.last_counter=self.env._sim_step_counter
        self.original_update=self.env.scene.update;self.original_reset=self.env._reset_idx
        self.env.scene.update=self.update;self.env._reset_idx=self.reset
        self.env._rough_traversal_tracker=self
        # Restarts restore family levels before an explicit native reset, never from Flat critic.
        ids=torch.arange(n,device=self.env.device)
        self.assign(ids);self.original_reset(ids)
        self.previous.copy_(self.robot.data.root_pos_w[:,:2])

    def assign(self, ids):
        t=self.t
        desired=t.tensor(self.levels,device=self.env.device)[self.family[ids]]
        self.terrain.terrain_levels[ids]=desired
        self.terrain.env_origins[ids]=self.terrain.terrain_origins[desired,self.terrain.terrain_types[ids]]
        self.env.scene.env_origins[ids]=self.terrain.env_origins[ids]

    def update(self, dt):
        self.original_update(dt)
        if self.last_counter==self.env._sim_step_counter:return
        t=self.t;d=self.robot.data
        # Native command resampling occurs after the policy's physics substeps.
        cmd=self.env.command_manager.get_command('base_velocity')[:,:2]
        q=d.root_quat_w; yaw=t.atan2(2*(q[:,0]*q[:,3]+q[:,1]*q[:,2]),1-2*(q[:,2].square()+q[:,3].square()))
        world=t.stack((yaw.cos()*cmd[:,0]-yaw.sin()*cmd[:,1],yaw.sin()*cmd[:,0]+yaw.cos()*cmd[:,1]),1)
        speed=world.norm(dim=1);direction=world/speed.clamp_min(1e-8)[:,None]
        self.expected.add_(speed*dt)
        self.progress.add_(((d.root_pos_w[:,:2]-self.previous)*direction).sum(1)*(speed>.05))
        self.previous.copy_(d.root_pos_w[:,:2])
        force=self.sensor.data.net_forces_w[:,self.forbidden].norm(dim=-1).amax(1)
        self.tilt_time=t.where(-d.projected_gravity_b[:,2]<.5,self.tilt_time+dt,0.)
        relative=d.root_pos_w[:,:2]-self.env.scene.env_origins[:,:2]
        finite=t.isfinite(d.root_state_w).all(1)&t.isfinite(d.joint_pos).all(1)&t.isfinite(d.joint_vel).all(1)&t.isfinite(force)
        self.nonfinite |= ~finite
        self.tilt_failed |= self.tilt_time>.1+1e-7
        self.failed |= ~finite | (force>1.) | self.tilt_failed | (relative.abs().amax(1)>5.4)
        self.ticks+=1;self.last_counter=self.env._sim_step_counter

    def reset(self, ids):
        t=self.t
        # Ignore stand/turn-only episodes; moving episodes still require >=1m actual progress.
        moving=self.expected[ids]>.05
        success=(~self.failed[ids]) & (self.progress[ids]>=t.maximum(.5*self.expected[ids],t.ones_like(self.expected[ids])))
        for family in range(5):
            selected=(self.family[ids]==family)&moving
            n=int(selected.sum());good=int((selected&success).sum())
            self.total_episodes[family]+=n;self.total_successes[family]+=good
            if family==0:continue
            # Finish batches from the current level only; lagging environments remain reported in totals.
            selected &= self.terrain.terrain_levels[ids]==self.levels[family]
            n=int(selected.sum());good=int((selected&success).sum())
            self.windows[family][0]+=n;self.windows[family][1]+=good
            count,safe=self.windows[family]
            if count>=100:
                old=self.levels[family];new=promotion(old,self.cap,count,safe)
                self.history.append(dict(family=self.names[family],level=old,next_level=new,episodes=count,
                                         successes=safe,cap=self.cap,physics_tick=self.ticks))
                self.levels[family]=new;self.windows[family]=[0,0]
        self.tilt_terminal_count += int(self.tilt_failed[ids].sum())
        self.assign(ids)
        self.original_reset(ids)
        self.failed[ids]=False;self.expected[ids]=0;self.progress[ids]=0;self.tilt_time[ids]=0;self.tilt_failed[ids]=False
        self.previous[ids]=self.robot.data.root_pos_w[ids,:2]

    def snapshot(self):
        if bool(self.nonfinite.any()):raise ValueError('Nonfinite physics state recorded before reset')
        return dict(cap=self.cap,levels=list(self.levels),windows=[list(x) for x in self.windows],
                    history=list(self.history),total_episodes=list(self.total_episodes),total_successes=list(self.total_successes),
                    physics_ticks=self.ticks,tilt_failed_episodes_since_restart=self.tilt_terminal_count,scope='Per-family safe traversal; no reward or termination changes; partial episodes reset on restart')

    def close(self):
        self.env.scene.update=self.original_update;self.env._reset_idx=self.original_reset
        del self.env._rough_traversal_tracker
