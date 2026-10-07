"""Frozen contract for cumulative-300 independent axis specialists."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_axis_specialists_stage2_retry_20261007.json"
SPEC_SHA = "99e20e06d96bbcbc5daba2aadda5de51c8436d5163482fce9b63a1e6adcd8eb5"
ARMS = ("lateral", "yaw")


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen axis-specialists stage-2 specification changed")
    spec = read_json(SPEC_PATH)
    inputs = [
        (spec["basis"]["stage1_result"], spec["basis"]["stage1_result_sha256"]),
        (spec["basis"]["failed_stage2_state"], spec["basis"]["failed_stage2_state_sha256"]),
        (spec["basis"]["completed_lateral_checkpoint"],
         spec["basis"]["completed_lateral_checkpoint_sha256"]),
        (spec["core"]["agent"], spec["core"]["agent_sha256"]),
        (spec["core"]["export"], spec["core"]["export_sha256"]),
        (spec["core"]["export_manifest"], spec["core"]["export_manifest_sha256"]),
        (spec["training"]["standard_train"], spec["training"]["standard_train_sha256"]),
    ]
    inputs.extend((row["checkpoint"], row["checkpoint_sha256"])
                  for row in spec["parents"].values())
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen axis stage-2 input changed: " + relative)
    training = spec["training"]
    expected = (ARMS, 9914, 512, 150, 300, 24799, 24948)
    actual = (tuple(training["arms"]), training["seed"], training["num_envs"],
              training["additional_updates_per_arm"], training["cumulative_updates_per_arm"],
              training["parent_checkpoint_iteration"], training["final_checkpoint_iteration"])
    if actual != expected:
        raise ValueError("Unexpected axis-specialists stage-2 budget")
    return spec
