"""Frozen contract for continued balanced-specialist training."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_specialist_stage2_20261005.json"
SPEC_SHA = "120345c37d06d3db1bcdedf0d1fae9b8be50c5cd147f160f94eb00e3709e89d4"
CANDIDATES = ("77", "102", "150")


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen specialist stage-2 specification changed")
    spec = read_json(SPEC_PATH)
    inputs = (
        (spec["basis"]["stage1_spec"], spec["basis"]["stage1_spec_sha256"]),
        (spec["basis"]["composite_result"], spec["basis"]["composite_result_sha256"]),
        (spec["source_specialist"]["checkpoint"], spec["source_specialist"]["checkpoint_sha256"]),
        (spec["source_specialist"]["agent"], spec["source_specialist"]["agent_sha256"]),
        (spec["training"]["standard_train"], spec["training"]["standard_train_sha256"]),
        (spec["composite"]["parent_export"], spec["composite"]["parent_export_sha256"]),
        (spec["composite"]["parent_manifest"], spec["composite"]["parent_manifest_sha256"]),
    )
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen specialist stage-2 input changed: " + relative)
    if tuple(spec["candidates"]) != CANDIDATES:
        raise ValueError("Unexpected stage-2 candidate order")
    training = spec["training"]
    if (training["seed"], training["num_envs"], training["additional_updates"],
            training["steps_per_update"]) != (9912, 512, 125, 24):
        raise ValueError("Unexpected stage-2 training budget")
    return spec
