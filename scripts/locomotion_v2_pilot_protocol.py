"""Predeclared 60-episode pilot probe; reuse v2 scoring without threshold changes."""
from dataclasses import asdict
import locomotion_v2_protocol as base
from locomotion_v2_protocol import (assess,finalize_result,condition,geometry,meshes_for,
                                   stair_exposure,coverage,SEED_START,SEEDS,POLICIES,EXPORT_DIRS)
TERRAINS=('flat_mu_100','rough_10','stairs_up_18','stairs_down_18')


def cases_for(name):
    wanted={'stand','longitudinal','lateral','yaw'} if not name.startswith('stairs') else {'traverse_0.7','stop_restart_0.5'}
    return [case for case in base.cases_for(name) if case.name in wanted]


def protocol_manifest(export_dirs=None):
    result=base.protocol_manifest(export_dirs)
    result.update(pilot_probe=True,variants={name:{'condition':condition(name),'geometry':geometry(name),
                    'cases':[asdict(case) for case in cases_for(name)]} for name in TERRAINS},
                  episodes_per_policy=sum(len(cases_for(name)) for name in TERRAINS)*SEEDS,
                  episodes_per_policy_condition={group:sum(len(cases_for(n)) for n in TERRAINS if condition(n)==group)*SEEDS
                                                   for group in result['conditions']})
    result['limitations'].append('Restricted pilot probe, not the full 32-cell screen')
    return result
