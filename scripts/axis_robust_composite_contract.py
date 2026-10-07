"""Frozen contract for the lateral-152/yaw-252 robust composite screen."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_axis_robust_composite_20261007.json"
SPEC_SHA = "5131c7f651969809a2d412500f2a64ff1692287696f9fcc78b79bde44089de9d"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen robust composite specification changed")
    spec = read_json(SPEC_PATH)
    inputs = [
        (spec["basis"]["endpoint_result"], spec["basis"]["endpoint_result_sha256"]),
        (spec["basis"]["parent_summary"], spec["basis"]["parent_summary_sha256"]),
        (spec["core"]["export"], spec["core"]["export_sha256"]),
        (spec["core"]["export_manifest"], spec["core"]["export_manifest_sha256"]),
    ]
    for row in spec["specialists"].values():
        inputs.extend(((row["export"], row["export_sha256"]),
                       (row["manifest"], row["manifest_sha256"])))
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen robust composite input changed: " + relative)
    endpoint = read_json(ROOT / spec["basis"]["endpoint_result"])
    if (endpoint["selections"]["lateral"]["selected"] != "microlateralcurve152_24800" or
            endpoint["selections"]["yaw"]["selected"] != "microyaw252_24900"):
        raise ValueError("Endpoint decision drift")
    return spec
