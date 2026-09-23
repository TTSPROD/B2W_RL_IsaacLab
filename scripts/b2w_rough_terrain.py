"""Project collision meshes for the bounded Rough protocol; no Isaac imports.

Coordinates cover [0,size] with a horizontal 3m spawn square at the centre.
All height samples are quantized symmetrically, including negative noise.
"""
from __future__ import annotations

import hashlib
import numpy as np
import trimesh

FAMILIES = ('flat', 'random', 'slope_up', 'slope_down', 'blocks')
NOISE = (.01, .025, .04)
SLOPE = (.05, .10, .20)
BLOCKS = ((.02, .04), (.04, .07), (.07, .10))
SCALE = .005


def mesh_hash(mesh):
    digest = hashlib.sha256()
    for values in (np.asarray(mesh.vertices, dtype='<f8'), np.asarray(mesh.faces, dtype='<i8')):
        digest.update(values.tobytes())
    return digest.hexdigest()


def grid_mesh(x, y, height):
    xx, yy = np.meshgrid(x, y, indexing='ij')
    vertices = np.stack((xx, yy, height), axis=-1).reshape(-1, 3)
    a = np.arange((len(x)-1)*len(y)).reshape(len(x)-1, len(y))[:, :-1].ravel()
    faces = np.concatenate((np.stack((a, a+len(y), a+1), axis=1),
                            np.stack((a+1, a+len(y), a+len(y)+1), axis=1)))
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def build_tile(family, level, seed, size=(12., 12.)):
    if family not in FAMILIES or level not in range(3):
        raise ValueError('Unknown Rough family/level')
    if tuple(size) != (12., 12.):
        raise ValueError('R0 uses frozen 12m tiles')
    rng = np.random.default_rng(seed)
    x, y = (np.linspace(0, side, round(side/.1)+1) for side in size)
    xx, yy = np.meshgrid(x-size[0]/2, y-size[1]/2, indexing='ij')
    pad = (abs(xx) <= 1.5+1e-9) & (abs(yy) <= 1.5+1e-9)
    height = np.zeros_like(xx)
    meshes = []
    if family == 'random':
        units = round(NOISE[level]/SCALE)
        height = rng.integers(-units, units+1, size=xx.shape)*SCALE
        height[pad] = 0.
    elif family.startswith('slope'):
        sign = 1. if family == 'slope_up' else -1.
        # An entire horizontal strip covers spawn and any reset yaw.
        height = np.rint(sign*SLOPE[level]*np.sign(xx)*np.maximum(abs(xx)-1.5, 0)/SCALE)*SCALE
    meshes.append(grid_mesh(x, y, height))
    if family == 'blocks':
        low, high = (round(v/SCALE) for v in BLOCKS[level])
        # Exact 0.45m cells, explicit vertical faces; no height-field rounding.
        for cx in np.arange(.225, size[0]-.224, .45):
            for cy in np.arange(.225, size[1]-.224, .45):
                if abs(cx-size[0]/2) < 1.725 and abs(cy-size[1]/2) < 1.725:
                    continue
                h = rng.integers(low, high+1)*SCALE
                box = trimesh.creation.box(extents=(.45, .45, h))
                box.apply_translation((cx, cy, h/2))
                meshes.append(box)
    return trimesh.util.concatenate(meshes), np.array([size[0]/2, size[1]/2, 0.])


def terrain_function(difficulty, cfg):
    level = min(2, int(difficulty*3))
    mesh, origin = build_tile(cfg.family, level, cfg.geometry_seed + 100*level, cfg.size)
    return [mesh], origin


def geometry_fixtures(seed=2026091970):
    records = []
    for family in FAMILIES:
        for level in range(3):
            mesh, origin = build_tile(family, level, seed+100*level)
            points = np.asarray(mesh.vertices)
            near = np.all(abs(points[:, :2]-origin[:2]) <= 1.5+1e-9, axis=1)
            if not np.isfinite(points).all() or not np.allclose(points[near, 2], 0., atol=1e-8):
                raise ValueError('Nonfinite mesh or nonhorizontal spawn')
            if not np.allclose(points[:, 2]/SCALE, np.rint(points[:, 2]/SCALE), atol=1e-8):
                raise ValueError('Mesh heights violate quantization')
            zmin, zmax = points[:, 2].min(), points[:, 2].max()
            if family == 'random' and not (np.isclose(zmin, -NOISE[level]) and np.isclose(zmax, NOISE[level])):
                raise ValueError('Signed random heights were lost')
            if family == 'blocks' and not (np.isclose(zmin, 0.) and np.isclose(zmax, BLOCKS[level][1])):
                raise ValueError('Incorrect block geometry')
            if family.startswith('slope'):
                left = points[np.isclose(points[:, 0], 0), 2].mean()
                right = points[np.isclose(points[:, 0], 12), 2].mean()
                expected = (1 if family == 'slope_up' else -1)*SLOPE[level]
                if not np.isclose((right-left)/9, expected):
                    raise ValueError('Incorrect slope sign/grade')
            records.append(dict(family=family, level=level, mesh_sha256=mesh_hash(mesh),
                                vertices=len(points), faces=len(mesh.faces), min_z=float(zmin), max_z=float(zmax),
                                spawn_origin=origin.tolist(), spawn_square_m=3.))
    return records
