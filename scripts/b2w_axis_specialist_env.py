"""Micro-sweep environment with axis-specialist evidence and progress."""
from pathlib import Path
import os

from b2w_micro_sweep_env import MicroSweepEnv
from axis_specialists_contract import load_spec
from run_support import ROOT, read_json, write_json


class AxisSpecialistEnv(MicroSweepEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        spec = load_spec()
        arm = os.environ["B2W_AXIS_ARM"]
        self.micro_target_updates = spec["training"]["updates_per_arm"]
        audit_path = self.output / "config_audit.json"
        audit = read_json(audit_path)
        audit.update(status="passed", axis_specialist=True, axis_arm=arm,
                     axis_sampling=spec["axis_sampling"][arm],
                     updates=self.micro_target_updates, seed=spec["training"]["seed"])
        write_json(audit_path, audit)
        write_json(Path(os.environ["B2W_JOB_DIR"]) / f"training_run_{arm}.json", {
            "path": Path(self.cfg.log_dir).resolve().relative_to(ROOT).as_posix(), "arm": arm})
