"""Same safety MDP with read-only reset diagnostics; no PPO/runner replacement."""
from pathlib import Path
import os
import torch
from b2w_curriculum_env import CurriculumEnv
from reset_diagnostics import ResetDiagnostics
from run_support import ROOT, write_json


class ResetPilotEnv(CurriculumEnv):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.reset_diagnostics=ResetDiagnostics(self.monitor.masks,self.device,self.physics_dt)
        self.policy_steps=0
        from b2w_reset_pilot_cfg import audit_environment
        self.output=Path(os.environ['B2W_RESET_OUTPUT'])
        audit_environment(self.cfg,self.output)
        if os.environ.get('B2W_RESET_MODE')=='train':
            write_json(Path(os.environ['B2W_JOB_DIR'])/'training_run.json',
                {'path':Path(self.cfg.log_dir).resolve().relative_to(ROOT).as_posix()})

    def _record_initial(self,ids):
        d=self.robot.data
        # Reading .data here would force an outdated sensor to recompute from
        # pre-reset PhysX contacts before the next physics tick. Inspect the
        # reset buffer directly; do not change sensor update timing for logging.
        force=self.contact._data.net_forces_w[:,self.protected].norm(dim=-1).amax(dim=1)
        self.reset_diagnostics.reset(ids,d.projected_gravity_b,d.joint_pos[:,self.joint_ids],
            d.joint_pos_limits[:,self.joint_ids[:12]],d.root_state_w,force)

    def _reset_idx(self,ids):
        super()._reset_idx(ids)
        if hasattr(self,'reset_diagnostics'):self._record_initial(ids)

    def _physics_safety(self):
        super()._physics_safety()
        before=len(self.reset_diagnostics.first_samples)
        self.reset_diagnostics.tick(self.monitor.flags,self.monitor.command)
        added=self.reset_diagnostics.first_samples[before:]
        if added:
            ids=torch.tensor([r['env'] for r in added],device=self.device)
            d=self.robot.data
            q=d.joint_pos[ids][:,self.joint_ids[:12]]
            limits=d.joint_pos_limits[ids][:,self.joint_ids[:12]]
            margin=torch.minimum(q-limits[:,:,0],limits[:,:,1]-q)
            joint=margin.argmin(dim=1)
            contact=self.contact.data.net_forces_w[ids][:,self.protected].norm(dim=-1)
            values=torch.cat((d.projected_gravity_b[ids,2:3],margin.amin(dim=1,keepdim=True),
                contact.amax(dim=1,keepdim=True),self.scene.terrain.terrain_levels[ids,None].float(),
                self.monitor.command.command[ids],d.root_pos_w[ids,2:3]-self.scene.env_origins[ids,2:3]),dim=1)
            for row,v,j in zip(added,values.cpu().tolist(),joint.cpu().tolist()):
                row.update(gravity_z=v[0],joint_margin_rad=v[1],protected_force_n=v[2],
                    level=int(v[3]),command=v[4:7],root_origin_clearance_m=v[7],
                    limiting_joint=self.contract['joint_names'][j])

    def snapshot(self):
        return {'policy_steps':self.policy_steps,'coverage':self.monitor.snapshot(),
                'reset_diagnostics':self.reset_diagnostics.snapshot()}

    def step(self,action):
        result=super().step(action)
        self.policy_steps+=1
        if self.policy_steps%240==0:
            data=self.snapshot();data.update(status='running',completed_updates=(self.policy_steps//24
                if os.environ.get('B2W_RESET_MODE')=='train' else 0),
                target_updates=300 if os.environ.get('B2W_RESET_MODE')=='train' else 0)
            write_json(self.output/'progress.json',data)
            if os.environ.get('B2W_RESET_MODE')=='train':
                write_json(Path(self.cfg.log_dir)/'progress.json',data)
                print('RESET_PROGRESS',self.policy_steps//24,'/300',flush=True)
        return result
