"""Frozen contract for the command-gated composite probe."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_composite_probe_20261005.json"
SPEC_SHA = "28f0e9190132c2d8edf33e4d573465531b845a6f17a65975f5e0ac2c2d1fdd54"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen composite-probe specification changed")
    spec = read_json(SPEC_PATH)
    if sha256(ROOT / spec["basis"]["micro_sweep_result"]) != spec["basis"]["micro_sweep_result_sha256"]:
        raise ValueError("Frozen micro-sweep result changed")
    for section in ("parent", "specialist"):
        for key, digest_key in (("export", "export_sha256"), ("manifest", "manifest_sha256")):
            if sha256(ROOT / spec[section][key]) != spec[section][digest_key]:
                raise ValueError(f"Frozen composite input changed: {section}.{key}")
    if (spec["composite"]["command_slice"] != [6, 9] or
            spec["composite"]["command_scale"] != [1.0, 1.0, 1.0] or
            spec["evaluation"]["actors"] != ["24650", "microcomposite_24674"]):
        raise ValueError("Unexpected composite routing/evaluation contract")
    return spec
