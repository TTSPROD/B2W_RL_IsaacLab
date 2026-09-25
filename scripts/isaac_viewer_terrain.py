"""Solid straight stair flight used only by the interactive Isaac viewer."""
import numpy as np
import trimesh
from isaaclab.terrains.sub_terrain_cfg import SubTerrainBaseCfg
from isaaclab.utils import configclass

TILE_X, TILE_Y = 10.0, 8.0


def stair_flight(difficulty, cfg):
    rise = cfg.min_rise + difficulty * (cfg.max_rise - cfg.min_rise)
    run = cfg.max_run - difficulty * (cfg.max_run - cfg.min_run)
    half = cfg.num_steps * run / 2
    total = cfg.num_steps * rise
    edges = [-TILE_X / 2, -half]
    edges.extend(-half + (i + 1) * run for i in range(cfg.num_steps))
    edges.append(TILE_X / 2)
    if cfg.direction == 'up':
        heights = [0.] + [(i + 1) * rise for i in range(cfg.num_steps)] + [total]
        start_height = 0.
    else:
        heights = [total] + [total - (i + 1) * rise for i in range(cfg.num_steps)] + [0.]
        start_height = total
    meshes = []
    for left, right, height in zip(edges[:-1], edges[1:], heights):
        bottom = -1.
        position = ((left + right) / 2 + TILE_X / 2, TILE_Y / 2, (height + bottom) / 2)
        meshes.append(trimesh.creation.box(
            (right - left, TILE_Y, height - bottom),
            trimesh.transformations.translation_matrix(position)))
    return meshes, np.array((TILE_X / 2 - 3., TILE_Y / 2, start_height))


@configclass
class StairFlightCfg(SubTerrainBaseCfg):
    function = stair_flight
    direction: str = 'up'
    min_rise: float = 0.14
    max_rise: float = 0.14
    min_run: float = 0.32
    max_run: float = 0.32
    num_steps: int = 6
