"""Build a four-terrain, one-axis diagnostic from the full v2 protocol."""
from dataclasses import asdict

import locomotion_v2_protocol as base
from locomotion_v2_protocol import (assess, finalize_result, condition, geometry, meshes_for,
                                    stair_exposure, coverage, SEED_START, SEEDS, POLICIES,
                                    EXPORT_DIRS)

TERRAINS = ("flat_mu_40", "flat_mu_100", "rough_02", "rough_10")


def install(namespace, axis):
    def cases_for(name):
        return [case for case in base.cases_for(name) if case.name == axis]

    def protocol_manifest(export_dirs=None):
        result = base.protocol_manifest(export_dirs)
        result.update(diagnostic_only=True, selection_only=False, axis_endpoint_screen=True,
                      axis=axis, conditions=["flat", "rough"],
                      variants={name: {"condition": condition(name), "geometry": geometry(name),
                               "cases": [asdict(case) for case in cases_for(name)]}
                                for name in TERRAINS},
                      episodes_per_policy=len(TERRAINS) * SEEDS,
                      episodes_per_policy_condition={"flat": 2 * SEEDS, "rough": 2 * SEEDS},
                      actor_layout="one actor per fresh process; identical axis/reset slots")
        result["limitations"].append(
            "Saved-checkpoint endpoint diagnostic; no qualification or promotion claim")
        return result

    namespace.update(cases_for=cases_for, protocol_manifest=protocol_manifest)
