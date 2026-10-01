"""Independent reset set, used only after freezing the selected candidate."""
from locomotion_v2_protocol import (
    POLICIES, EXPORT_DIRS, TERRAINS, cases_for, condition, geometry, meshes_for,
    stair_exposure, coverage, assess, finalize_result,
)
from locomotion_v2_protocol import protocol_manifest as _manifest

SEED_START = 74001
SEEDS = 20


def protocol_manifest(export_dirs=None):
    result = _manifest(export_dirs)
    result.update(stage="validation", reset_seeds=list(range(SEED_START, SEED_START + SEEDS)),
                  episodes_per_policy=result["episodes_per_policy"] * 4,
                  episodes_per_policy_condition={key: value * 4 for key, value in
                                                 result["episodes_per_policy_condition"].items()},
                  selection_only=False)
    result["gates"]["cell_screen"] = "at least 19/20 successes and zero unsafe per cell"
    return result
