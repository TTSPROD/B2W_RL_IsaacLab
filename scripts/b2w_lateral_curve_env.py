"""Axis environment with the short lateral-curve progress target."""
from b2w_axis_specialist_env import AxisSpecialistEnv
from lateral_curve_contract import load_spec


class LateralCurveEnv(AxisSpecialistEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.micro_target_updates = load_spec()["training"]["additional_updates"]
