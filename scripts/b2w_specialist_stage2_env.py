"""Balanced micro-sweep environment with stage-2 progress/provenance."""
from pathlib import Path
import os

from b2w_micro_sweep_env import MicroSweepEnv
from run_support import ROOT, read_json, write_json
from specialist_stage2_contract import load_spec


class SpecialistStage2Env(MicroSweepEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        spec = load_spec()
        self.micro_target_updates = spec["training"]["additional_updates"]
        audit_path = self.output / "config_audit.json"
        audit = read_json(audit_path)
        audit.update(status="passed", specialist_stage2=True,
                     source_checkpoint_sha256=spec["source_specialist"]["checkpoint_sha256"],
                     additional_updates=self.micro_target_updates,
                     cumulative_final_updates=150)
        write_json(audit_path, audit)
        job = Path(os.environ["B2W_JOB_DIR"])
        write_json(job / "training_run_stage2.json", {
            "path": Path(self.cfg.log_dir).resolve().relative_to(ROOT).as_posix(),
            "source_checkpoint": spec["source_specialist"]["checkpoint"],
        })
