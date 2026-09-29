"""Compact Flat/Rough/Stairs evaluation for the B2W low-level policy.

The suite deliberately excludes slopes, blocks, curbs, gaps, mixed transitions,
route following and absolute-heading objectives.  Each variant has five command
programs and twenty paired reset seeds.  Three variants form each of the four
acceptance conditions, yielding 300 episodes per policy and condition.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import numpy as np

from locomotion57_protocol import ROOT, DT, Case, Segment

POLICIES = (24650, "rl_sar")
EXPORT_DIRS = {
    24650: ROOT / "policies/local/core_24650/export",
    "rl_sar": ROOT / "logs/core_locomotion_24650_vs_rl_sar/reference_export",
}
SEED_START = 63001
SEEDS = 20
GEOMETRY_SEED = 2026092801

FLAT = tuple(f"flat_mu_{value:02d}" for value in (40, 70, 100))
ROUGH = tuple(f"rough_{value:02d}" for value in (2, 6, 10))
STAIRS_UP = tuple(f"stairs_up_{value:02d}" for value in (6, 12, 18))
STAIRS_DOWN = tuple(f"stairs_down_{value:02d}" for value in (6, 12, 18))
TERRAINS = FLAT + ROUGH + STAIRS_UP + STAIRS_DOWN


def condition(terrain):
    if terrain in FLAT:
        return "flat"
    if terrain in ROUGH:
        return "rough"
    if terrain in STAIRS_UP:
        return "stairs_up"
    if terrain in STAIRS_DOWN:
        return "stairs_down"
    raise ValueError(terrain)


def _motion_cases(terrain):
    zero = (0.0, 0.0, 0.0)
    init = Segment(2.0, zero, "initialization")
    stop = Segment(12.0, zero)

    def axis(name, component):
        positive = []
        negative = []
        for value, seconds in ((0.3, 6.0), (0.7, 6.0), (1.0, 8.0)):
            command = [0.0, 0.0, 0.0]
            command[component] = value
            positive.append(Segment(seconds, tuple(command)))
            command[component] = -value
            negative.append(Segment(seconds, tuple(command)))
        return Case(name, terrain, (init, *positive, stop, *negative, stop))

    return (
        Case("stand", terrain, (Segment(12.0, zero),)),
        axis("longitudinal", 0),
        axis("lateral", 1),
        axis("yaw", 2),
        Case("mixed", terrain, (
            init,
            Segment(8.0, (0.5, 0.5, 0.0)),
            Segment(8.0, (0.5, 0.0, 0.5)),
            stop,
            Segment(8.0, (-0.5, -0.5, 0.0)),
            Segment(8.0, (-0.5, 0.0, -0.5)),
            stop,
        )),
    )


def _stair_cases(terrain):
    zero = (0.0, 0.0, 0.0)
    init = Segment(2.0, zero, "initialization")
    stop = Segment(12.0, zero)
    traverse = tuple(
        Case(f"traverse_{speed:.1f}", terrain,
             (init, Segment(20.0, (speed, 0.0, 0.0)), stop))
        for speed in (0.3, 0.5, 0.7)
    )
    return traverse + (
        Case("stop_restart_0.3", terrain,
             (init, Segment(5.0, (0.3, 0.0, 0.0)), stop,
              Segment(20.0, (0.3, 0.0, 0.0)), stop)),
        Case("stop_restart_0.5", terrain,
             (init, Segment(4.0, (0.5, 0.0, 0.0)), stop,
              Segment(16.0, (0.5, 0.0, 0.0)), stop)),
    )


def cases_for(terrain):
    group = condition(terrain)
    return list(_stair_cases(terrain) if group.startswith("stairs") else _motion_cases(terrain))


def geometry(terrain):
    group = condition(terrain)
    base = {
        "name": terrain,
        "condition": group,
        "size_m": [80.0, 80.0],
        "geometry_seed": GEOMETRY_SEED + TERRAINS.index(terrain),
        "start_height": 0.0,
        "physical_edge_x": None,
    }
    if group == "flat":
        base.update(kind="flat", friction=int(terrain.rsplit("_", 1)[1]) / 100.0)
    elif group == "rough":
        amplitude = int(terrain[-2:]) / 100.0
        base.update(kind="rough", friction=1.0, cell_m=0.25,
                    height_min_m=-amplitude, height_max_m=amplitude)
    else:
        height = int(terrain[-2:]) / 100.0
        direction = 1 if group == "stairs_up" else -1
        base.update(kind="stairs", friction=1.0, risers=12, first_edge_x=0.8,
                    step_width=0.3, last_edge_x=4.1, step_height=height,
                    direction=direction)
        if direction < 0:
            base["start_height"] = 12 * height
    return base


def surface_height(terrain, x, y):
    cfg = geometry(terrain)
    x, y = np.broadcast_arrays(x, y)
    if cfg["kind"] != "stairs":
        return np.zeros_like(x)
    riser = np.clip(np.floor((x - cfg["first_edge_x"]) / cfg["step_width"]) + 1,
                    0, cfg["risers"])
    return cfg["start_height"] + cfg["direction"] * cfg["step_height"] * riser


def meshes_for(terrain):
    import trimesh
    cfg = geometry(terrain)

    def box(size, center):
        mesh = trimesh.creation.box(size)
        mesh.apply_translation(center)
        return mesh

    meshes = []
    if cfg["kind"] == "stairs":
        meshes.append(box((80, 80, 2), (0, 0, -1)))
        height = cfg["step_height"]
        for index in range(cfg["risers"]):
            edge = cfg["first_edge_x"] + index * cfg["step_width"]
            if cfg["direction"] > 0:
                low, high, top = edge, 40.0, (index + 1) * height
            else:
                low, high, top = -40.0, edge, (cfg["risers"] - index) * height
            meshes.append(box((high - low, 80, top), ((low + high) / 2, 0, top / 2)))
    elif cfg["kind"] == "rough":
        axis = np.linspace(-40.0, 40.0, 321)
        xx, yy = np.meshgrid(axis, axis, indexing="ij")
        rng = np.random.default_rng(cfg["geometry_seed"])
        zz = rng.uniform(cfg["height_min_m"], cfg["height_max_m"], xx.shape)
        zz[(np.abs(xx) <= 0.5) & (np.abs(yy) <= 0.5)] = 0
        vertices = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
        ids = np.arange(xx.size).reshape(xx.shape)
        a, b, c, d = (value.ravel() for value in
                      (ids[:-1, :-1], ids[1:, :-1], ids[:-1, 1:], ids[1:, 1:]))
        faces = np.concatenate((np.column_stack((a, b, c)), np.column_stack((b, d, c))))
        meshes.append(trimesh.Trimesh(vertices=vertices, faces=faces, process=False))
    else:
        meshes.append(box((80, 80, 2), (0, 0, -1)))
    for mesh in meshes:
        mesh.apply_translation([40, 40, 0])
    return meshes, np.array([40.0, 40.0, cfg["start_height"]])


def stair_exposure(terrain, root_xyz, wheel_xyz, wheel_up_force):
    cfg = geometry(terrain)
    if cfg["kind"] != "stairs":
        return np.zeros(len(root_xyz), dtype=bool)
    height = surface_height(terrain, wheel_xyz[..., 0], wheel_xyz[..., 1])
    gap = wheel_xyz[..., 2] - 0.0875 - height
    supported = (wheel_up_force > 1.0) & (gap >= -0.03) & (gap <= 0.10)
    interior = ((wheel_xyz[..., 0] >= cfg["first_edge_x"])
                & (wheel_xyz[..., 0] < cfg["last_edge_x"]))
    return ((root_xyz[..., 0] >= cfg["first_edge_x"])
            & (root_xyz[..., 0] < cfg["last_edge_x"])
            & (supported.sum(axis=-1) >= 2) & (supported & interior).any(axis=-1))


def coverage(case, exposed, root_xyz, valid):
    cfg = geometry(case.terrain)
    if cfg["kind"] != "stairs":
        return None
    schedule, _ = case.schedule()
    count = min(len(schedule), len(valid))
    valid = valid[:count]
    exposed = exposed[:count]
    root_x = root_xyz[:count, 0]
    moving = schedule[:count, 0] > 0
    crossed = np.flatnonzero(valid & (root_x > cfg["last_edge_x"] + 0.5))
    crossed_step = int(crossed[0]) if len(crossed) else None
    if crossed_step is None:
        progress_ratio = 0.0
    else:
        commanded = float(np.maximum(schedule[:crossed_step + 1, 0], 0).sum() * DT)
        start_x = float(root_x[np.flatnonzero(valid)[0]])
        progress_ratio = float((root_x[crossed_step] - start_x) / max(commanded, 1e-9))
    motion_exposure_s = float(np.sum(exposed & valid & moving) * DT)
    windows = []
    offset = 0
    for index, segment in enumerate(case.segments):
        length = round(segment.seconds / DT)
        required = (case.name.startswith("stop_restart") and not any(segment.command)
                    and segment.kind != "initialization" and index == 2)
        if required:
            low, high = offset + round(2.0 / DT), offset + length
            complete = high <= count and bool(valid[low:high].all())
            fraction = float(exposed[low:min(high, count)].sum() / max(high - low, 1))
            windows.append({"segment": index, "complete": complete,
                            "exposure_fraction": fraction,
                            "exposure_pass": bool(complete and fraction >= 0.9)})
        offset += length
    traversal_pass = bool(crossed_step is not None and progress_ratio >= 0.8
                          and motion_exposure_s >= 1.0)
    return {
        "moving_stair_exposure_s": motion_exposure_s,
        "crossed_final_riser": crossed_step is not None,
        "crossed_step": crossed_step,
        "progress_ratio": progress_ratio,
        "moving_exposure_pass": traversal_pass,
        "zero_windows": windows,
    }


def finalize_result(case, result, terrain_coverage, covered):
    """Use traversal/tempo rather than flat-like instantaneous RMSE on stairs."""
    if not condition(case.terrain).startswith("stairs"):
        return result, covered
    unsafe = bool(result["safety"]["unsafe_flags"])
    complete = bool(result["completed"])
    zero_pass = all(window.get("exposed_zero_success", False)
                    for window in terrain_coverage["zero_windows"])
    covered = bool(complete and terrain_coverage["moving_exposure_pass"] and zero_pass)
    flags = []
    if unsafe:
        flags.append("unsafe")
    if not complete or not terrain_coverage["moving_exposure_pass"]:
        flags.append("traversal_failure")
    if not zero_pass:
        flags.append("standstill_failure")
    result["diagnostic_flat_like_outcome"] = result["outcome"]
    result["failure_flags"] = flags
    result["outcome"] = ("unsafe" if unsafe else "success" if covered
                         else "standstill_failure" if not zero_pass
                         else "traversal_failure")
    return result, covered


def protocol_manifest(export_dirs=None):
    from evaluation_policy import validate_export
    selected = EXPORT_DIRS if export_dirs is None else export_dirs
    exports = {}
    for policy, folder in selected.items():
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        exports[policy] = validate_export(policy, folder / "policy.pt", manifest)
    variants = {name: {"condition": condition(name), "geometry": geometry(name),
                       "cases": [asdict(case) for case in cases_for(name)]}
                for name in TERRAINS}
    per_condition = 3 * 5 * SEEDS
    return {
        "schema": "b2w_core_locomotion_v1",
        "policies": list(selected),
        "reset_seeds": list(range(SEED_START, SEED_START + SEEDS)),
        "variants": variants,
        "conditions": ["flat", "rough", "stairs_up", "stairs_down"],
        "episodes_per_policy_condition": per_condition,
        "episodes_per_policy": per_condition * 4,
        "exports": exports,
        "gates": {
            "observed_success_fraction": 0.95,
            "one_sided_wilson95_lower": 0.90,
            "unsafe_allowed": 0,
            "flat_rough_rmse": [0.2, 0.2, 0.25],
            "response_fraction": 0.8,
            "settling_s": 2.0,
            "continuous_zero_s": 10.0,
            "zero_vxy": 0.1,
            "zero_wz": 0.1,
            "stair_progress_ratio": 0.8,
        },
        "excluded_from_acceptance": [
            "blocks", "slopes", "cross_slopes", "curbs", "gaps",
            "mixed_surface_transitions", "route", "waypoint", "absolute_heading",
            "lateral_or_yaw_commands_on_stairs",
        ],
        "actor_only": True,
        "qualification": False,
        "hardware_approval": False,
    }


if __name__ == "__main__":
    print(json.dumps(protocol_manifest(), indent=2))
