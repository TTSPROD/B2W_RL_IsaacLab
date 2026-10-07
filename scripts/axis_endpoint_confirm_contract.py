from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_axis_endpoint_confirm_20261007.json"
SPEC_SHA = "097721a8536dfe6938efd1e89efb6259ef3fbff4d98758c456e1809fd560e5ca"


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen sequential endpoint confirmation changed")
    spec = read_json(SPEC_PATH)
    inputs = [(spec["basis"]["parallel_screen_result"], spec["basis"]["parallel_screen_result_sha256"]),
              (spec["basis"]["parent_summary"], spec["basis"]["parent_summary_sha256"])]
    for actors in spec["actors"].values():
        for row in actors.values():
            inputs.extend(((row["export"], row["export_sha256"]),
                           (row["manifest"], row["manifest_sha256"])))
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen sequential confirmation input changed: " + relative)
    return spec
