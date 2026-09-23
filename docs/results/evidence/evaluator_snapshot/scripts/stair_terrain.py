"""Project-owned solid stair-flight geometry for training and evaluation."""

import numpy as np
import trimesh

from isaaclab.terrains.sub_terrain_cfg import SubTerrainBaseCfg
from isaaclab.terrains.height_field.hf_terrains import random_uniform_terrain
from isaaclab.terrains.height_field.hf_terrains_cfg import HfRandomUniformTerrainCfg
from isaaclab.terrains.trimesh.mesh_terrains import inverted_pyramid_stairs_terrain
from isaaclab.terrains.trimesh.mesh_terrains_cfg import MeshInvertedPyramidStairsTerrainCfg
from isaaclab.utils import configclass

TILE_X = 10.0
TILE_Y = 8.0
START_X = -3.0
GOAL_X = 2.7


def stair_flight(difficulty, cfg):
    """Build a straight flight with an approach and an exit landing."""
    rise = cfg.min_rise + difficulty * (cfg.max_rise - cfg.min_rise)
    run = cfg.max_run - difficulty * (cfg.max_run - cfg.min_run)
    half = cfg.num_steps * run / 2.0
    total = cfg.num_steps * rise
    edges = [-TILE_X / 2, -half]
    edges.extend(-half + (i + 1) * run for i in range(cfg.num_steps))
    edges.append(TILE_X / 2)
    if cfg.direction == "up":
        heights = [0.0] + [(i + 1) * rise for i in range(cfg.num_steps)] + [total]
        start_height = 0.0
    else:
        heights = [total] + [total - (i + 1) * rise for i in range(cfg.num_steps)] + [0.0]
        start_height = total
    meshes = []
    for left, right, height in zip(edges[:-1], edges[1:], heights):
        bottom = -1.0
        dims = (right - left, TILE_Y, height - bottom)
        pos = ((left + right) / 2 + TILE_X / 2, TILE_Y / 2, (height + bottom) / 2)
        meshes.append(trimesh.creation.box(dims, trimesh.transformations.translation_matrix(pos)))
    # TerrainGenerator recenters this origin with the mesh. The robot starts
    # here on the approach instead of at the center of the flight.
    origin = np.array((TILE_X / 2 + START_X, TILE_Y / 2, start_height))
    return meshes, origin


@configclass
class StairFlightCfg(SubTerrainBaseCfg):
    function = stair_flight
    direction: str = "up"
    min_rise: float = 0.14
    max_rise: float = 0.14
    min_run: float = 0.32
    max_run: float = 0.32
    num_steps: int = 6


def rough_replay(difficulty, cfg):
    """Upstream random rough surface with the same approach origin as stairs."""
    meshes, _ = random_uniform_terrain(difficulty, cfg)
    origin = np.array((TILE_X / 2 + START_X, TILE_Y / 2, 0.0))
    return meshes, origin


@configclass
class RoughReplayCfg(HfRandomUniformTerrainCfg):
    function = rough_replay


def inverted_stairs_replay(difficulty, cfg):
    """Upstream inverted stairs with a safe approach origin on the fourth outer step."""
    meshes, _ = inverted_pyramid_stairs_terrain(difficulty, cfg)
    step_height = cfg.step_height_range[0] + difficulty * (cfg.step_height_range[1] - cfg.step_height_range[0])
    # START_X maps to tile x=2.0; with a 1 m border and 0.3 m treads,
    # this point is on ring k=3, whose top is at -(k+1)*step_height.
    origin = np.array((TILE_X / 2 + START_X, TILE_Y / 2, -4.0 * step_height))
    return meshes, origin


@configclass
class InvertedStairsReplayCfg(MeshInvertedPyramidStairsTerrainCfg):
    function = inverted_stairs_replay
