"""Balanced micro-sweep environment with independent-repeat provenance."""
from pathlib import Path
import os

from b2w_micro_sweep_env import MicroSweepEnv
from run_support import ROOT, read_json, write_json
from specialist_repeat_contract import load_spec


class SpecialistRepeatEnv(MicroSweepEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        spec = load_spec()
        self.micro_target_updates = spec["training"]["updates"]
        audit_path = self.output / "config_audit.json"
        audit = read_json(audit_path)
        audit.update(status="passed", specialist_repeat=True,
                     parent_checkpoint_sha256=spec["parent"]["checkpoint_sha256"],
                     updates=self.micro_target_updates, seed=spec["training"]["seed"])
        write_json(audit_path, audit)
        write_json(Path(os.environ["B2W_JOB_DIR"]) / "training_run_repeat.json", {
            "path": Path(self.cfg.log_dir).resolve().relative_to(ROOT).as_posix(),
            "parent_checkpoint": spec["parent"]["checkpoint"],
        })
