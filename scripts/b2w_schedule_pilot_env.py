"""Existing reset diagnostics and physics; additional startup audit only."""
from b2w_reset_pilot_env import ResetPilotEnv


class SchedulePilotEnv(ResetPilotEnv):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from b2w_schedule_pilot_cfg import audit_environment
        audit_environment(self.cfg,self.output)
