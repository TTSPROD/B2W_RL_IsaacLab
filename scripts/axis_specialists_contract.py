"""Frozen contract for independent lateral/yaw specialists."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_axis_specialists_20261007.json"
SPEC_SHA = "ae397ac1762969cbfa8220c51b1143549b486f529658a43b2d9e2d4765bd28ca"
ARMS = ("lateral", "yaw")


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen axis-specialists specification changed")
    spec = read_json(SPEC_PATH)
    inputs = (
        (spec["basis"]["repeat_result"], spec["basis"]["repeat_result_sha256"]),
        (spec["parent"]["checkpoint"], spec["parent"]["checkpoint_sha256"]),
        (spec["parent"]["agent"], spec["parent"]["agent_sha256"]),
        (spec["parent"]["env"], spec["parent"]["env_sha256"]),
        (spec["parent"]["export"], spec["parent"]["export_sha256"]),
        (spec["parent"]["export_manifest"], spec["parent"]["export_manifest_sha256"]),
        (spec["training"]["standard_train"], spec["training"]["standard_train_sha256"]),
    )
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen axis-specialists input changed: " + relative)
    training = spec["training"]
    if (tuple(training["arms"]), training["seed"], training["num_envs"],
            training["updates_per_arm"], training["final_checkpoint_iteration"]) != (
                ARMS, 9914, 512, 150, 24799):
        raise ValueError("Unexpected axis-specialists budget")
    if spec["axis_sampling"]["lateral"] != {"axis": 1, "case": "lateral"} or \
            spec["axis_sampling"]["yaw"] != {"axis": 2, "case": "yaw"}:
        raise ValueError("Unexpected axis-specialists sampling")
    return spec
