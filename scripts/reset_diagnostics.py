"""Read-only, tensor-only accounting of initial states and first safety events."""
import torch


class ResetDiagnostics:
    reasons = ('nonfinite', 'tilt', 'protected_contact', 'hard_joint')

    def __init__(self, masks, device, physics_dt):
        self.masks, self.device, self.dt = masks, device, physics_dt
        n = len(next(iter(masks.values())))
        self.age = torch.zeros(n, device=device, dtype=torch.long)
        self.seen = torch.zeros(n, device=device, dtype=torch.bool)
        self.initial = torch.zeros(4, device=device, dtype=torch.long)
        self.stale = torch.zeros((), device=device, dtype=torch.long)
        self.events = {k:torch.zeros((3,4), device=device, dtype=torch.long) for k in masks}
        self.phase_events = {k:torch.zeros((16,4), device=device, dtype=torch.long) for k in masks}
        self.first_samples = []
        self.initial_samples = []
        self.physics_ticks = 0

    def reset(self, ids, gravity, q, limits, root, force):
        self.age[ids] = 0
        self.seen[ids] = False
        finite = torch.isfinite(torch.cat((gravity[ids], q[ids], root[ids]),dim=1)).all(dim=1)
        margin = torch.minimum(q[ids,:12]-limits[ids,:,0],limits[ids,:,1]-q[ids,:12]).amin(dim=1)
        self.initial += torch.stack((torch.tensor(len(ids),device=self.device),
            (~finite).sum(),(gravity[ids,2]>-.5).sum(),(margin<-.001).sum()))
        self.stale += (force[ids]>0).sum()
        if len(self.initial_samples)<32:
            selected=ids[:32-len(self.initial_samples)]
            for i,g,r,m in zip(selected.cpu().tolist(),gravity[selected].cpu().tolist(),
                root[selected].cpu().tolist(),margin[:len(selected)].cpu().tolist()):
                self.initial_samples.append({'env':i,'gravity':g,'root_state':r,'joint_margin_rad':m})

    def tick(self, flags, command):
        self.physics_ticks += 1
        self.age += 1
        first = flags.any(dim=1)&~self.seen
        bins=torch.where(self.age<=round(.1/self.dt),0,
            torch.where(self.age<=round(2/self.dt),1,2))
        phase=command.rehearsal_phase.clamp(-1,14)+1
        reason_ids=torch.arange(4,device=self.device)
        for name,mask in self.masks.items():
            active=(first&mask)[:,None]&flags
            self.events[name]+=torch.bincount((bins[:,None]*4+reason_ids)[active],minlength=12).reshape(3,4)
            self.phase_events[name]+=torch.bincount((phase[:,None]*4+reason_ids)[active],minlength=64).reshape(16,4)
        if len(self.first_samples)<64:
            ids=first.nonzero().flatten()[:64-len(self.first_samples)]
            for i,f,a,c,p in zip(ids.cpu().tolist(),flags[ids].cpu().tolist(),
                    self.age[ids].cpu().tolist(),command.rehearsal_case[ids].cpu().tolist(),
                    command.rehearsal_phase[ids].cpu().tolist()):
                self.first_samples.append({'env':i,'age_s':a*self.dt,'case':c,'phase':p,
                                           'reasons':[n for n,v in zip(self.reasons,f) if v]})
        self.seen |= first

    def snapshot(self):
        initial=self.initial.cpu().tolist()
        events={k:v.cpu().tolist() for k,v in self.events.items()}
        seconds=self.physics_ticks*self.dt*len(self.age)
        early=sum(rows[0][1]+rows[1][1] for rows in events.values())
        return {'initial_resets':initial[0],
            'initial_invalid':dict(zip(('nonfinite','tilt','hard_joint'),initial[1:])),
            'stale_contact_resets':int(self.stale),
            'first_event_bins_s':['0-0.1','0.1-2','>2'],
            'reason_order':list(self.reasons),'first_events_by_cohort':events,
            'first_events_by_cohort_phase':{k:v.cpu().tolist() for k,v in self.phase_events.items()},
            'env_seconds':seconds,'early_tilt_per_env_second':early/seconds if seconds else 0.,
            'initial_samples':self.initial_samples,'first_event_samples':self.first_samples}
