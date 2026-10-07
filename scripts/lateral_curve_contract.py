"""Frozen contract for dense lateral checkpoint search."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_lateral_curve_20261007.json"
SPEC_SHA = "19a1ee2ff8edbe086904a89d3b9dfcfd8e0ea874117ef0e7cc26f66dcb30211d"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen lateral-curve specification changed")
    spec = read_json(SPEC_PATH)
    inputs = [
        (spec["basis"]["axis_stage1_result"], spec["basis"]["axis_stage1_result_sha256"]),
        (spec["basis"]["axis_stage2_result"], spec["basis"]["axis_stage2_result_sha256"]),
        (spec["core"]["agent"], spec["core"]["agent_sha256"]),
        (spec["core"]["export"], spec["core"]["export_sha256"]),
        (spec["core"]["export_manifest"], spec["core"]["export_manifest_sha256"]),
        (spec["parent"]["checkpoint"], spec["parent"]["checkpoint_sha256"]),
        (spec["training"]["standard_train"], spec["training"]["standard_train_sha256"]),
    ]
    inputs.extend((row["checkpoint"], row["checkpoint_sha256"])
                  for row in spec["existing"].values())
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen lateral-curve input changed: " + relative)
    if (spec["training"]["additional_updates"], spec["training"]["save_interval"],
            spec["training"]["checkpoints"]) != (76, 25, {"24800": 152, "24825": 177,
                                                         "24850": 202, "24874": 226}):
        raise ValueError("Unexpected lateral-curve budget")
    return spec
