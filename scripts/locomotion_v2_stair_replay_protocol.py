"""Diagnostic replay of the pilot's exact stair batches; no policy selection."""
from locomotion_v2_pilot_protocol import (assess, finalize_result, condition, geometry,
    meshes_for, stair_exposure, coverage, SEED_START, SEEDS, POLICIES, EXPORT_DIRS, cases_for)
import locomotion_v2_pilot_protocol as pilot

TERRAINS = ('stairs_up_18', 'stairs_down_18')


def protocol_manifest(export_dirs=None):
    result = pilot.protocol_manifest(export_dirs)
    result.update(diagnostic_only=True, selection_only=False,
                  conditions=['stairs_up', 'stairs_down'],
                  variants={name: result['variants'][name] for name in TERRAINS},
                  episodes_per_policy=20,
                  episodes_per_policy_condition={'stairs_up': 10, 'stairs_down': 10})
    result['limitations'].append('Same selection seeds: repeated runs/order sensitivity are not independent validation')
    return result
