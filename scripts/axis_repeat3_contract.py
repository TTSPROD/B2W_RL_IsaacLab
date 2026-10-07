from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_axis_repeat3_20261007.json"
SPEC_SHA = "c71b3a5ee1035fc1a5d0ecc0b312d6fce8cac3fe51b6cf373a9ed759f8f05d2e"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen axis repeat-3 specification changed")
    spec = read_json(SPEC_PATH)
    inputs = [(spec["export"], spec["export_sha256"]), (spec["manifest"], spec["manifest_sha256"])]
    for key in ("axis_confirmation", "full_composite", "parent_summary"):
        inputs.append((spec["prior"][key], spec["prior"][key + "_sha256"]))
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen repeat-3 input changed: " + relative)
    return spec
