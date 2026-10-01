"""Same-slot diagnostic: one actor, ten ascent episodes per fresh process."""
from locomotion_v2_stair_replay_protocol import (assess, finalize_result, condition, geometry,
    meshes_for, stair_exposure, coverage, SEED_START, SEEDS, POLICIES, EXPORT_DIRS, cases_for)
import locomotion_v2_stair_replay_protocol as replay

TERRAINS = ('stairs_up_18',)


def protocol_manifest(export_dirs=None):
    if export_dirs is None or len(export_dirs) != 1:
        raise ValueError('Same-slot comparison requires exactly one actor per process')
    result = replay.protocol_manifest(export_dirs)
    result.update(conditions=['stairs_up'], episodes_per_policy=10,
                  episodes_per_policy_condition={'stairs_up': 10},
                  variants={name: result['variants'][name] for name in TERRAINS},
                  actor_layout='one actor per fresh process; identical case/reset slots')
    return result
