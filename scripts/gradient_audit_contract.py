"""Frozen input checks for the no-update gradient audit."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_gradient_audit_20261005.json"
SPEC_SHA = "eeaa660aad98d531989aa9375712ec82ce4a7ba1f75be50e901e422017aa6a70"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen gradient audit specification changed")
    spec = read_json(SPEC_PATH)
    inputs = (
        (spec["parent"]["checkpoint"], spec["parent"]["sha256"]),
        (spec["parent"]["agent"], spec["parent"]["agent_sha256"]),
        (spec["parent"]["env"], spec["parent"]["env_sha256"]),
        (spec["mdp"]["schedule_specification"], spec["mdp"]["schedule_specification_sha256"]),
    )
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen gradient audit input changed: " + relative)
    rollout = spec["rollout"]
    if (rollout["policy_steps"] % rollout["steps_per_batch"] or
            rollout["ppo_updates"] != 0 or rollout["optimizer_steps"] != 0):
        raise ValueError("Invalid no-update rollout contract")
    return spec
