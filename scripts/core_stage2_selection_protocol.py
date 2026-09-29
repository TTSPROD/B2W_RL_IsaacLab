"""Five-seed checkpoint selection for the 24650 stage-2 continuation."""
from __future__ import annotations

from core_locomotion_protocol import (
    FLAT, ROUGH, STAIRS_DOWN, STAIRS_UP, TERRAINS,
    cases_for, condition, coverage, finalize_result, geometry, meshes_for,
    stair_exposure, surface_height,
)
from core_locomotion_protocol import protocol_manifest as _core_manifest

POLICIES = (24650, 24675, 24700, 24725, 24750, 24775, 24800)
EXPORT_DIRS = {}
SEED_START = 66001
SEEDS = 5


def protocol_manifest(export_dirs=None):
    selected = EXPORT_DIRS if export_dirs is None else export_dirs
    result = _core_manifest(selected)
    result.update(
        schema="b2w_core_stage2_selection_v1",
        reset_seeds=list(range(SEED_START, SEED_START + SEEDS)),
        episodes_per_policy_condition=3 * 5 * SEEDS,
        episodes_per_policy=4 * 3 * 5 * SEEDS,
        selection_only=True,
        qualification=False,
        hardware_approval=False,
    )
    return result
