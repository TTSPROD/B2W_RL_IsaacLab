"""Tensor-only safety, segment coverage and stair learning diagnostics."""
import torch
from training_coverage import TrainingCoverage


def safety_flags(q, dq, tau, gravity, force, root, actions, ranges):
    finite = torch.isfinite(torch.cat((q, dq, tau, gravity, force[:, None], root, actions), dim=1)).all(dim=1)
    margin = torch.minimum(q[:, :12]-ranges[..., 0], ranges[..., 1]-q[:, :12]).amin(dim=1)
    return torch.stack((~finite, gravity[:, 2] > -.5, force > 5., margin < -.001), dim=1)


def exclusive_timeout(timeout, unsafe):
    return timeout & ~unsafe


def level_changes(history, filled):
    ready = filled >= history.shape[1]
    return ready & history.all(dim=1), ready & ~history.all(dim=1)


class StairMonitor(TrainingCoverage):
    def __init__(self, env, plan):
        self.env, self.plan = env, plan
        self.command = env.command_manager.get_term('base_velocity')
        command=self.command
        super().__init__({'retention':command.original_cohort, **command.target_masks},
                         command.rehearsal_banks, env.device, env.step_dt)
        n, device=env.num_envs,env.device
        self.flags=torch.zeros(n,4,device=device,dtype=torch.bool)
        self.all_flags=torch.zeros(4,device=device,dtype=torch.long)
        self.episode_flags=torch.zeros_like(self.flags)
        self.old_case=torch.zeros(n,device=device,dtype=torch.long)
        self.old_phase=torch.full_like(self.old_case,-1)
        self.segment_steps=torch.zeros_like(self.old_case)
        self.segment_exposure=torch.zeros(n,device=device)
        self.segment_zero_good=torch.ones(n,device=device,dtype=torch.bool)
        self.expected=torch.zeros(n,device=device)
        self.actual=torch.zeros_like(self.expected)
        self.moving_exposure=torch.zeros_like(self.expected)
        self.crossed=torch.zeros(n,device=device,dtype=torch.bool)
        self.zero_good=torch.ones_like(self.crossed)
        self.exposed_stop=torch.zeros_like(self.crossed)
        self.requires_stop=torch.zeros_like(self.crossed)
        self.history=torch.zeros(n,plan['curriculum']['window_episodes'],device=device,dtype=torch.bool)
        self.filled=torch.zeros_like(self.old_case)
        self.episodes=torch.zeros_like(self.old_case)
        self.promotions=torch.zeros((),device=device,dtype=torch.long)
        self.demotions=torch.zeros_like(self.promotions)
        self.segment_stats={k:torch.zeros((*v.shape,2),device=device,dtype=torch.long) for k,v in self.phases.items()}
        self.reset_counts={k:torch.zeros(3,device=device,dtype=torch.long) for k in self.masks}
        self.level_attempts={k:torch.zeros(10,device=device,dtype=torch.long) for k in ('stairs_up','stairs_down')}
        self.reset_level_counts={k:torch.zeros(10,device=device,dtype=torch.long) for k in self.level_attempts}

    def begin(self):
        self.flags.zero_()
        c,p=self.command.rehearsal_case,self.command.rehearsal_phase
        changed=(c!=self.old_case)|(p!=self.old_phase)
        self.finish_segments(changed)
        self.old_case.copy_(c);self.old_phase.copy_(p)
        for name,mask in self.command.target_masks.items():
            selected=changed & mask & (p>=0)
            self._add(name,selected,0)
            if name.startswith('stairs'):
                stop_ids=torch.tensor([case['case'].startswith('stop_restart') for case in self.plan['banks'][name]],device=self.env.device)
                ids=selected.nonzero(as_tuple=False).flatten()
                self.requires_stop[ids] |= stop_ids[c[ids]]

    def _add(self,name,mask,field):
        stat=self.segment_stats[name]
        ids=self.old_case[mask]*stat.shape[1]+self.old_phase[mask]
        stat[:,:,field]+=torch.bincount(ids,minlength=stat.shape[0]*stat.shape[1]).reshape(stat.shape[:2])

    def finish_segments(self,mask):
        for name,cohort in self.command.target_masks.items():
            valid=mask & cohort & (self.old_phase>=0)
            bank=self.banks[name]
            # Case ids are local to each cohort bank.  Index only members of the
            # current cohort: other cohorts can legitimately have larger case ids
            # (for example a one-case axis bank next to multi-case stair banks).
            ids=valid.nonzero(as_tuple=False).flatten()
            durations=torch.zeros_like(self.segment_exposure)
            zero_command=torch.zeros_like(valid)
            if len(ids):
                phase=self.old_phase[ids].clamp(0,bank.durations.shape[1]-1)
                case=self.old_case[ids]
                durations[ids]=bank.durations[case,phase]
                zero_command[ids]=bank.commands[case,phase].norm(dim=1)==0
            complete=valid & (self.segment_steps*self.dt >= durations-self.dt/2) & ~self.episode_flags.any(dim=1)
            self._add(name,complete,1)
            zero=complete & zero_command & (durations>=12)
            checked=valid & (durations>=12) & zero_command
            self.zero_good[checked] &= self.segment_zero_good[checked]
            self.exposed_stop |= zero & self.segment_zero_good & (self.segment_exposure >= .9*(durations-2))
        self.segment_steps[mask]=0
        self.segment_exposure[mask]=0
        self.segment_zero_good[mask]=True

    def record(self,reward,velocity,exposure,crossed):
        self.episode_flags |= self.flags
        self.all_flags += self.flags.sum(dim=0)
        self.observe(reward,self.command.rehearsal_case,self.command.rehearsal_phase)
        self.segment_steps += 1
        cmd=self.command.command
        speed=cmd[:,:2].norm(dim=1)
        moving=speed>.01
        self.expected+=speed*self.dt
        self.actual+=(velocity[:,:2]*cmd[:,:2]).sum(dim=1)/speed.clamp_min(.01)*self.dt
        self.moving_exposure+=(moving & exposure)*self.dt
        zero=cmd.norm(dim=1)==0
        measured_zero=zero & (self.segment_steps*self.dt>2)
        self.segment_exposure+=(measured_zero & exposure)*self.dt
        good=(velocity[:,:2].norm(dim=1)<=.1)&(velocity[:,2].abs()<=.1)
        self.segment_zero_good &= ~measured_zero | good
        self.crossed |= crossed & moving

    def reset(self,ids):
        active=self.lengths[ids]>0
        actual_ids=ids[active]
        flush=torch.zeros_like(self.crossed);flush[actual_ids]=True
        self.finish_segments(flush)
        timeouts=self.env.reset_time_outs if hasattr(self.env,'reset_time_outs') else torch.zeros_like(self.crossed)
        for name,mask in self.masks.items():
            selected=actual_ids[mask[actual_ids]]
            self.reset_counts[name]+=torch.stack((self.episode_flags[selected].any(dim=1).sum(),
                timeouts[selected].sum(),torch.tensor(len(selected),device=self.env.device)))
        super().reset(ids)
        self.episode_flags[ids]=False
        self.old_phase[ids]=-1
        self.segment_steps[ids]=0
        self.expected[ids]=0;self.actual[ids]=0;self.moving_exposure[ids]=0
        self.crossed[ids]=False;self.zero_good[ids]=True
        self.exposed_stop[ids]=False;self.requires_stop[ids]=False
        self.flags[ids]=False

    def curriculum(self,ids):
        terrain=self.env.scene.terrain
        mask=self.command.target_masks['stairs_up']|self.command.target_masks['stairs_down']
        ids=ids[mask[ids] & (self.lengths[ids]>0) & (self.expected[ids]>.1)]
        # Include the final segment before scoring the episode; coverage reset will not double count.
        flush=torch.zeros_like(mask);flush[ids]=True
        self.finish_segments(flush)
        good=(~self.episode_flags[ids].any(dim=1) & self.crossed[ids] & self.zero_good[ids]
              & (self.moving_exposure[ids]>=1.) & (self.expected[ids]>.1)
              & (self.actual[ids]>=.8*self.expected[ids])
              & (~self.requires_stop[ids]|self.exposed_stop[ids]))
        for name in self.level_attempts:
            selected=ids[self.command.target_masks[name][ids]]
            counts=torch.bincount(terrain.terrain_levels[selected],minlength=10)
            self.level_attempts[name]+=counts
        self.episodes[ids]+=1
        self.history[ids]=torch.roll(self.history[ids],1,dims=1)
        self.history[ids,0]=good
        self.filled[ids]+=1
        if not self.command.training_profile['adaptive']:return
        up,down=level_changes(self.history[ids],self.filled[ids])
        old=terrain.terrain_levels[ids].clone()
        new=(old+up.long()-down.long()).clamp(0,9)
        # Deterministic 20% rehearsal after a successful top-level window; no extra RNG draws.
        rehearse=(old==9)&up&((ids+self.episodes[ids])%5==0)
        new[rehearse]=(ids[rehearse]+self.episodes[ids[rehearse]])%9
        self.promotions+=((new>old)&up).sum();self.demotions+=((new<old)&down).sum()
        terrain.terrain_levels[ids]=new
        terrain.update_env_origins(ids,torch.zeros_like(up),torch.zeros_like(down))
        ready=self.filled[ids]>=self.history.shape[1]
        self.filled[ids[ready]]=0;self.history[ids[ready]]=False

    def snapshot(self):
        data=super().snapshot()
        for name,row in data.items():
            row['reset_counts']={'unsafe':int(self.reset_counts[name][0]),'timeout':int(self.reset_counts[name][1]),'total':int(self.reset_counts[name][2])}
            if name in self.segment_stats:
                row['segment_attempts']=self.segment_stats[name][:,:,0].cpu().tolist()
                row['segment_completions']=self.segment_stats[name][:,:,1].cpu().tolist()
            if name in self.level_attempts:
                row['level_attempts']=self.level_attempts[name].cpu().tolist()
                row['current_levels']=torch.bincount(self.env.scene.terrain.terrain_levels[self.command.target_masks[name]],minlength=10).cpu().tolist()
        data['retention']['safety_policy_ticks_by_reason']=self.all_flags.cpu().tolist()
        data['retention']['curriculum_promotions']=int(self.promotions)
        data['retention']['curriculum_demotions']=int(self.demotions)
        return data
