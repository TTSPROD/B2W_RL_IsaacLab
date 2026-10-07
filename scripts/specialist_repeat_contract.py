"""Frozen contract for the independent balanced-specialist repeat."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_specialist_repeat_20261007.json"
SPEC_SHA = "1e351421fa95fba93bf3346359ccb202a858e0decb2a050294dc0cf3114f0253"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen specialist-repeat specification changed")
    spec = read_json(SPEC_PATH)
    inputs = (
        (spec["basis"]["stage2_result"], spec["basis"]["stage2_result_sha256"]),
        (spec["parent"]["checkpoint"], spec["parent"]["checkpoint_sha256"]),
        (spec["parent"]["agent"], spec["parent"]["agent_sha256"]),
        (spec["parent"]["env"], spec["parent"]["env_sha256"]),
        (spec["parent"]["export"], spec["parent"]["export_sha256"]),
        (spec["parent"]["export_manifest"], spec["parent"]["export_manifest_sha256"]),
        (spec["training"]["standard_train"], spec["training"]["standard_train_sha256"]),
    )
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen specialist-repeat input changed: " + relative)
    training = spec["training"]
    if (training["seed"], training["num_envs"], training["updates"],
            training["steps_per_update"], training["final_checkpoint_iteration"]) != (
                9913, 512, 150, 24, 24799):
        raise ValueError("Unexpected specialist-repeat budget")
    if spec["composite"]["policy_id"] != "microcompositerep150_24799":
        raise ValueError("Unexpected specialist-repeat policy ID")
    return spec
