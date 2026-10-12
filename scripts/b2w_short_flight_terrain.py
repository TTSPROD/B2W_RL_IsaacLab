"""Straight short stair flight (марш) geometry helpers, pure Python (no Isaac).

F1 single factor: target stairs become a straight one-direction march instead of a
multi-side pyramid, so the real-crossing success window becomes reachable. The
geometry mirrors the evaluation protocol (first edge 0.8 m, tread 0.30 m, crossing
past last edge + 0.5 m) so training exposure transfers to the v2 staircase cells.

Level (terrain_levels, 0..9) -> deterministic geometry (no per-tile jitter in the
riser count/height); the generator still fills each column with every level row.
"""
from __future__ import annotations

import numpy as np
import trimesh

TILE_X, TILE_Y = 8.0, 8.0


def flight_geometry(level, plan):
    """Deterministic per-level flight: (num_steps, step_height, first_edge, last_edge)."""
    g = plan["target_geometry"]
    frac = min(1.0, max(0.0, int(level) / 9.0))
    num_steps = int(round(g["flight_min_steps"] + frac * (g["flight_max_steps"] - g["flight_min_steps"])))
    step_height = g["flight_height_m"][0] + frac * (g["flight_height_m"][1] - g["flight_height_m"][0])
    first = float(g["flight_first_edge_m"])
    last = first + (num_steps - 1) * float(g["flight_tread_m"])
    return num_steps, step_height, first, last


def stair_flight(difficulty, cfg):
    """Straight flight along +x within an 8x8 m tile; up/down by cfg.direction.

    Mirrors the evaluation stair geometry (mesh_terrains style): a single flat
    ground slab plus per-riser landing boxes so the top edge of riser k is
    (k+1)*height (up) or (n-k)*height (down). The returned origin is the flight
    base platform; the robot spawns there before the first riser.
    """
    level = min(9, max(0, int(np.floor(difficulty * 10.0))))
    num_steps, step_height, first, _ = flight_geometry(level, plan_from_cfg(cfg))
    tread = float(cfg.tread_m)
    last = first + (num_steps - 1) * tread
    direction = int(cfg.direction)
    start_height = 0.0 if direction > 0 else num_steps * step_height

    def box(x0, x1, top, y0=0.0, y1=TILE_Y, bottom=-1.0):
        x0, x1 = float(x0), float(x1)
        width, depth, height = x1 - x0, y1 - y0, top - bottom
        mesh = trimesh.creation.box((width, depth, height))
        mesh.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (top + bottom) / 2))
        return mesh

    meshes = [box(0.0, TILE_X, 0.0, bottom=-1.0)]
    for index in range(num_steps):
        edge = first + index * tread
        if direction > 0:
            meshes.append(box(edge, TILE_X, (index + 1) * step_height))
        else:
            meshes.append(box(0.0, edge, (num_steps - index) * step_height))
    origin = np.array([TILE_X / 2, TILE_Y / 2, start_height])
    return meshes, origin


def plan_from_cfg(cfg):
    """Ad-hoc plan view so stair_flight stays callable without Isaac config classes."""
    return {"target_geometry": {
        "flight_min_steps": int(cfg.num_steps_min), "flight_max_steps": int(cfg.num_steps_max),
        "flight_height_m": tuple(float(v) for v in cfg.step_height_range),
        "flight_first_edge_m": float(cfg.first_edge_x), "flight_tread_m": float(cfg.tread_m)}}
