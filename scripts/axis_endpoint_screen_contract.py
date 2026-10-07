"""Frozen inputs for the full-flat/rough saved axis endpoint screen."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_axis_endpoint_screen_20261007.json"
SPEC_SHA = "aa7ebe5cf3bf14a7a697ecd0d16d37f0bdbf6d1fb9c28fe3ea70f53b8504c145"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen axis endpoint specification changed")
    spec = read_json(SPEC_PATH)
    inputs = [
        (spec["basis"]["full_screen_summary"], spec["basis"]["full_screen_summary_sha256"]),
        (spec["core"]["export"], spec["core"]["export_sha256"]),
        (spec["core"]["export_manifest"], spec["core"]["export_manifest_sha256"]),
    ]
    for endpoints in spec["endpoints"].values():
        inputs.extend((row["checkpoint"], row["checkpoint_sha256"])
                      for row in endpoints.values())
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen axis endpoint input changed: " + relative)
    if (set(spec["endpoints"]["lateral"]), set(spec["endpoints"]["yaw"])) != (
            {"150", "152", "177", "202", "226", "252", "300"},
            {"150", "252", "300"}):
        raise ValueError("Unexpected endpoint set")
    return spec
