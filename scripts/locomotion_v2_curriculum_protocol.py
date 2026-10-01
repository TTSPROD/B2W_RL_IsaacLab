"""The unchanged 60-episode probe, one actor per process in fixed slots."""
from locomotion_v2_pilot_protocol import (assess,finalize_result,condition,geometry,meshes_for,
    stair_exposure,coverage,SEED_START,SEEDS,POLICIES,EXPORT_DIRS,cases_for,TERRAINS)
import locomotion_v2_pilot_protocol as pilot


def protocol_manifest(export_dirs=None):
    if export_dirs is None or len(export_dirs)!=1:
        raise ValueError('Curriculum probe requires exactly one actor per process')
    result=pilot.protocol_manifest(export_dirs)
    result.update(diagnostic_only=True, selection_only=False,
                  actor_layout='one actor per fresh process; identical case/reset slots')
    return result
