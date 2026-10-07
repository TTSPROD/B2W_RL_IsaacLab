"""Ten-episode diagnostic protocol: only lateral cases on flat and rough."""
from dataclasses import asdict

import locomotion_v2_protocol as base
from locomotion_v2_protocol import (assess, finalize_result, condition, geometry, meshes_for,
                                    stair_exposure, coverage, SEED_START, SEEDS, POLICIES,
                                    EXPORT_DIRS)

TERRAINS = ("flat_mu_100", "rough_10")


def cases_for(name):
    return [case for case in base.cases_for(name) if case.name == "lateral"]


def protocol_manifest(export_dirs=None):
    result = base.protocol_manifest(export_dirs)
    result.update(diagnostic_only=True, selection_only=False, lateral_curve=True,
                  conditions=["flat", "rough"],
                  variants={name: {"condition": condition(name), "geometry": geometry(name),
                           "cases": [asdict(case) for case in cases_for(name)]} for name in TERRAINS},
                  episodes_per_policy=sum(len(cases_for(name)) for name in TERRAINS) * SEEDS,
                  episodes_per_policy_condition={condition(name): len(cases_for(name)) * SEEDS
                                                   for name in TERRAINS},
                  actor_layout="one actor per fresh process; identical lateral/reset slots")
    result["limitations"].append("Lateral checkpoint-curve diagnostic; no retention or promotion claim")
    return result
