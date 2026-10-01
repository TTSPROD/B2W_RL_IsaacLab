"""Declared minimal comparison suite; historical v1 scoring stays reproducible."""
from __future__ import annotations

from dataclasses import asdict
import numpy as np

import core_locomotion_protocol as terrain
from locomotion57_protocol import ROOT, DT, Case, Segment, assess as legacy_assess

POLICIES = (19999, 24650, "rl_sar")
EXPORT_DIRS = {}
SEED_START = 73001
SEEDS = 5
TERRAINS = ("flat_mu_40", "flat_mu_100", "rough_02", "rough_10",
            "stairs_up_06", "stairs_up_18", "stairs_down_06", "stairs_down_18")
condition = terrain.condition
geometry = terrain.geometry
meshes_for = terrain.meshes_for
stair_exposure = terrain.stair_exposure
coverage = terrain.coverage


def cases_for(name):
    if condition(name).startswith("stairs"):
        # Endpoints of the trained stair bank, plus a stop/restart in the middle.
        return [case for case in terrain.cases_for(name)
                if case.name in {"traverse_0.3", "traverse_0.7", "stop_restart_0.5"}]
    zero = (0., 0., 0.)
    result = [Case("stand", name, (Segment(12., zero),))]
    for axis, label in enumerate(("longitudinal", "lateral", "yaw")):
        segments = [Segment(2., zero, "initialization")]
        # A genuine direct sign reversal; no intervening reset/zero.
        for value in (.3, .7, 1., -1., -.7, -.3):
            command = [0., 0., 0.]
            command[axis] = value
            segments.append(Segment(6., tuple(command)))
        segments.append(Segment(12., zero))
        result.append(Case(label, name, tuple(segments)))
    result.append(Case("mixed", name, (
        Segment(2., zero, "initialization"), Segment(6., (.5, .5, .5)),
        Segment(6., (-.5, -.5, -.5)), Segment(12., zero))))
    return result


def assess(case, velocity, position, safety, completed, definition):
    result = legacy_assess(case, velocity, position, safety, completed, definition)
    # Preserve the old raw metrics, but transitions have a measured response time
    # instead of requiring every overlapping 1-s window to pass forever.
    offset = 0
    segments = {item["segment"]: item for item in result["segments"]}
    deadline_passes, zero_passes = [], []
    for index, segment in enumerate(case.segments):
        length = round(segment.seconds / DT)
        if segment.kind == "initialization":
            offset += length
            continue
        if not any(segment.command):
            zero_passes.append(segments[index].get("continuous_zero_pass", False))
            offset += length
            continue
        values = np.asarray(velocity[offset:offset + length])
        response = None
        if len(values) >= 50:
            squared = (values - segment.command) ** 2
            cumulative = np.vstack([np.zeros(3), np.cumsum(squared, axis=0)])
            rms = np.sqrt(np.maximum(0, (cumulative[50:] - cumulative[:-50]) / 50))
            good = np.isfinite(rms).all(axis=1) & (rms <= [.2, .2, .25]).all(axis=1)
            indices = np.flatnonzero(good)
            if len(indices):
                response = float((indices[0] + 50) * DT)
        segments[index]["response_time_s"] = response
        segments[index]["response_within_2s"] = response is not None and response <= 2.
        deadline_passes.append(segments[index]["response_within_2s"])
        offset += length
    flags = set(result["failure_flags"]) - {"command_transition_failure"}
    if not all(deadline_passes):
        flags.add("command_transition_failure")
    if not all(zero_passes):
        flags.add("standstill_failure")
    result["failure_flags"] = sorted(flags)
    result["outcome"] = next((name for name in (
        "unsafe", "tracking_failure", "command_transition_failure", "standstill_failure")
        if name in flags), "success")
    return result


def finalize_result(case, result, exposed, covered):
    flags = set(result["failure_flags"])
    if condition(case.terrain).startswith("stairs"):
        # Instantaneous flat-ground tracking is diagnostic on stairs. Every zero,
        # including the final stop on the landing, remains an acceptance check.
        flags -= {"tracking_failure", "command_transition_failure"}
        if not result["completed"] or not exposed["moving_exposure_pass"]:
            flags.add("traversal_failure")
        if not all(window["exposed_zero_success"] for window in exposed["zero_windows"]):
            flags.add("standstill_failure")
        covered = result["completed"] and exposed["moving_exposure_pass"]
    result["failure_flags"] = sorted(flags)
    result["outcome"] = next((name for name in (
        "unsafe", "traversal_failure", "tracking_failure", "command_transition_failure", "standstill_failure")
        if name in flags), "success")
    result["checks"] = {
        "safety": "unsafe" not in flags,
        "completed": result["completed"],
        "tracking": None if exposed is not None else "tracking_failure" not in flags,
        "transitions": None if exposed is not None else "command_transition_failure" not in flags,
        "stop": "standstill_failure" not in flags,
        "traversal": None if exposed is None else "traversal_failure" not in flags,
    }
    return result, covered


def protocol_manifest(export_dirs=None):
    selected = EXPORT_DIRS if export_dirs is None else export_dirs
    result = terrain.protocol_manifest(selected)
    variants = {name: {"condition": condition(name), "geometry": geometry(name),
                       "cases": [asdict(case) for case in cases_for(name)]} for name in TERRAINS}
    result.update(schema="b2w_locomotion_v2", stage="screen", variants=variants,
                  reset_seeds=list(range(SEED_START, SEED_START + SEEDS)),
                  episodes_per_policy=sum(len(cases_for(name)) for name in TERRAINS) * SEEDS,
                  episodes_per_policy_condition={group: sum(len(cases_for(name)) for name in TERRAINS
                      if condition(name) == group) * SEEDS for group in result["conditions"]},
                  selection_only=True, qualification=False, automatic_selection=False,
                  command_bounds={"vx_m_s": [-1., 1.], "vy_m_s": [-1., 1.], "wz_rad_s": [-1., 1.]},
                  command_provenance={"19999": "policies/server/upstream_19999/env.yaml",
                      "24650": "policies/local/core_24650/env.yaml",
                      "rl_sar": "user reports analogous robot_lab/train.py; exact run config unavailable"},
                  limitations=["nominal physics, no sensor noise or external pushes",
                               "five reset seeds are not independent training seeds",
                               "stair commands only forward 0.3/0.5/0.7, tread 0.30 m",
                               "sampled cells do not prove the continuous command/terrain envelope"])
    result["gates"]["transition"] = "first full 1-s RMSE window within tolerance by 2 s"
    result["gates"]["cell_screen"] = "all five trials pass; failures retained, no pooled qualification"
    return result
