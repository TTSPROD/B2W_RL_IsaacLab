"""Axis environment whose progress target is the additional stage-2 budget."""
from b2w_axis_specialist_env import AxisSpecialistEnv
from axis_specialists_stage2_contract import load_spec


class AxisSpecialistStage2Env(AxisSpecialistEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.micro_target_updates = load_spec()["training"]["additional_updates_per_arm"]
