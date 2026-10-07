"""Frozen contract for the lateral-177/yaw-150 composite probe."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_axis_mixed_probe_20261007.json"
SPEC_SHA = "11562cdb61b737ad992cdad1cdd656b51a1b566d50544882e78f49371906d546"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen axis-mixed probe specification changed")
    spec = read_json(SPEC_PATH)
    inputs = [
        (spec["basis"]["axis_stage1_result"], spec["basis"]["axis_stage1_result_sha256"]),
        (spec["basis"]["lateral_curve_result"], spec["basis"]["lateral_curve_result_sha256"]),
        (spec["core"]["export"], spec["core"]["export_sha256"]),
        (spec["core"]["export_manifest"], spec["core"]["export_manifest_sha256"]),
    ]
    inputs.extend((row["checkpoint"], row["checkpoint_sha256"])
                  for row in spec["specialists"].values())
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen axis-mixed input changed: " + relative)
    if (spec["specialists"]["lateral"]["cumulative_updates"],
            spec["specialists"]["yaw"]["cumulative_updates"]) != (177, 150):
        raise ValueError("Unexpected axis-mixed endpoints")
    return spec
