"""Schedule environment with declared micro-sweep metadata and progress only."""
from pathlib import Path
import os
import torch

from b2w_schedule_pilot_env import SchedulePilotEnv
from micro_sweep_contract import load_spec
from run_support import ROOT, read_json, write_json


class MicroSweepEnv(SchedulePilotEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        spec = load_spec()
        arm = os.environ["B2W_MICRO_ARM"]
        self.micro_target_updates = spec["stage1"]["updates"]
        self.signed_exposure = torch.zeros(3, 2, dtype=torch.long, device=self.device)
        audit_path = self.output / "config_audit.json"
        audit = read_json(audit_path)
        audit.update(status="passed", micro_sweep_arm=arm,
                     declared_variant=spec["variants"][arm],
                     gradient_audit_sha256=spec["basis"]["gradient_audit_sha256"])
        write_json(audit_path, audit)
        job = Path(os.environ["B2W_JOB_DIR"])
        write_json(job / f"training_run_{arm}.json", {
            "path": Path(self.cfg.log_dir).resolve().relative_to(ROOT).as_posix(),
            "arm": arm,
        })

    def snapshot(self):
        data = super().snapshot()
        data["signed_pure_axis_policy_steps"] = {
            axis: {"negative": int(self.signed_exposure[index, 0]),
                   "positive": int(self.signed_exposure[index, 1])}
            for index, axis in enumerate(("vx", "vy", "yaw"))
        }
        return data

    def step(self, action):
        command = self.command_manager.get_term("base_velocity").command
        active = command.abs() > 1.e-6
        pure = active.sum(dim=1) == 1
        for axis in range(3):
            selected = pure & active[:, axis]
            self.signed_exposure[axis, 0] += (selected & (command[:, axis] < 0)).sum()
            self.signed_exposure[axis, 1] += (selected & (command[:, axis] > 0)).sum()
        result = super().step(action)
        if self.policy_steps % 240 == 0 or self.policy_steps == self.micro_target_updates * 24:
            data = self.snapshot()
            data.update(status="running", completed_updates=self.policy_steps // 24,
                        target_updates=self.micro_target_updates,
                        arm=os.environ["B2W_MICRO_ARM"])
            write_json(self.output / "progress.json", data)
        return result
