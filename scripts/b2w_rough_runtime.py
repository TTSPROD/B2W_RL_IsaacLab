"""R0-only Rough configuration. No development training is authorized by this module."""
from __future__ import annotations
import json
from pathlib import Path

from b2w_runtime import PROJECT_ROOT, B2W_MODULE, prepare_env_cfg, register_b2w_tasks
from b2w_rough_terrain import terrain_function, mesh_hash

ROUGH_TASK = 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0'
GEOMETRY_SEED = 2026091970
ANCHOR_SHA256 = 'f3509a695591ca5235c0a68df7051379ffa315df6dc4515481db4209aa8f8cee'


def make_rough_env_cfg(*, num_envs, device, seed, headless=True):
    import importlib
    from isaaclab.utils import configclass
    from isaaclab.terrains import TerrainGeneratorCfg, SubTerrainBaseCfg
    register_b2w_tasks()
    from b2w_yaw_commands import MeasuredYawVelocityCommand

    @configclass
    class ProjectTileCfg(SubTerrainBaseCfg):
        function = terrain_function
        family: str = 'flat'
        geometry_seed: int = GEOMETRY_SEED

    cfg = importlib.import_module(f'{B2W_MODULE}.rough_env_cfg').UnitreeB2WRoughEnvCfg()
    cfg = prepare_env_cfg(cfg, num_envs=num_envs, device=device, seed=seed, headless=headless)
    cfg.scene.terrain.max_init_terrain_level = 0
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
        seed=GEOMETRY_SEED, curriculum=True, size=(12., 12.), num_rows=3, num_cols=10,
        border_width=10., horizontal_scale=.1, vertical_scale=.005, use_cache=False,
        cache_dir=str(PROJECT_ROOT/'.cache/rough_terrains'),
        sub_terrains={name: ProjectTileCfg(family=name, proportion=proportion)
                      for name, proportion in [('flat', .3), ('random', .3), ('slope_up', .1),
                                                ('slope_down', .1), ('blocks', .2)]})
    # R0 stays on level 0. Upstream distance promotion is deliberately disabled.
    cfg.curriculum.terrain_levels = None
    cfg.events.randomize_reset_base.params['pose_range']['roll'] = (-.1, .1)
    cfg.events.randomize_reset_base.params['pose_range']['pitch'] = (-.1, .1)
    cfg.commands.base_velocity.class_type = MeasuredYawVelocityCommand
    cfg.commands.base_velocity.pure_yaw_fraction = .25
    return cfg


def flat_bank_path():
    qualified = json.loads((PROJECT_ROOT/'docs/results/2026-09-19-reference-qualification-verification.json').read_text(encoding='utf-8'))
    return (PROJECT_ROOT/qualified['finals']['54']['checkpoint']).parent/'reference_update_150.pt'


def validate_environment(env, expected_level=0):
    """Check actual collision mesh, ray hits, spawn, and action/observation ABI."""
    import numpy as np
    import torch
    from isaaclab.utils.warp import raycast_mesh
    from smoke_b2w import _gpu_evidence
    base = env.unwrapped
    terrain = base.scene.terrain
    robot = base.scene['robot']
    scanner = base.scene['height_scanner']
    obs = base.observation_manager.compute()
    if tuple(obs['policy'].shape) != (base.num_envs, 57) or tuple(obs['critic'].shape) != (base.num_envs, 247):
        raise ValueError('Rough observation ABI mismatch')
    if not bool(torch.isfinite(obs['critic']).all()) or scanner.data.ray_hits_w.shape[1] != 187:
        raise ValueError('Invalid privileged height scan')
    if not bool((terrain.terrain_levels == expected_level).all()):
        raise ValueError('Terrain level differs from the requested runtime check')
    import trimesh
    from pxr import Usd, UsdGeom
    mesh_prims = [prim for prim in Usd.PrimRange(base.sim.stage.GetPrimAtPath('/World/ground/terrain'))
                  if prim.IsA(UsdGeom.Mesh)]
    if len(mesh_prims) != 1:
        raise ValueError('Expected exactly one collision terrain mesh')
    usd_mesh = UsdGeom.Mesh(mesh_prims[0])
    mesh = trimesh.Trimesh(vertices=np.asarray(usd_mesh.GetPointsAttr().Get()),
                           faces=np.asarray(usd_mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1, 3), process=False)
    # Probe all 30 spawn pads against the same mesh used by PhysX and the scanner.
    origins = terrain.terrain_origins.reshape(-1, 3)
    offsets = torch.tensor([[x, y, 10.] for x in (-1.4, 0., 1.4) for y in (-1.4, 0., 1.4)], device=base.device)
    starts = origins[:, None, :]+offsets
    directions = torch.zeros_like(starts); directions[..., 2] = -1
    hits, _, normals, _ = raycast_mesh(starts, directions, scanner.meshes['/World/ground'], return_normal=True)
    error = (hits[..., 2]-origins[:, None, 2]).abs().max().item()
    if not torch.isfinite(hits).all() or error > 1e-4 or not bool((normals[..., 2] > .999).all()):
        raise ValueError(f'Collision mesh spawn pad/rays fail: {error}')
    relative = robot.data.root_pos_w - base.scene.env_origins
    if not bool((relative[:, :2].abs() <= .501).all()):
        raise ValueError('Reset lies outside verified spawn pad')
    return dict(task=ROUGH_TASK, actor=57, critic=247, actions=16, height_rays=187,
                mesh_sha256=mesh_hash(mesh), vertices=len(mesh.vertices), faces=len(mesh.faces),
                spawn_probe_count=int(np.prod(hits.shape[:-1])), spawn_max_error_m=error,
                terrain_levels=terrain.terrain_levels.tolist(), terrain_types=terrain.terrain_types.tolist(),
                env_origins=base.scene.env_origins.tolist(), physics=_gpu_evidence(base, robot, torch),
                training_level=expected_level, safe_curriculum_implemented=False, r1_permitted=False)


def load_flat_bank(device):
    import torch
    values = torch.load(flat_bank_path(), map_location='cpu', weights_only=False)['observations']
    if values.shape != (4096, 57) or not torch.isfinite(values).all():
        raise ValueError('Invalid frozen Flat observation bank')
    return {'policy': values.to(device)}


def verify_export(policy, observations, directory):
    import copy
    import torch
    from isaaclab_rl.rsl_rl import export_policy_as_jit
    export_policy_as_jit(policy, policy.actor_obs_normalizer, path=str(directory), filename='policy.pt')
    exported = torch.jit.load(str(Path(directory)/'policy.pt'), map_location='cpu').eval()
    actor = copy.deepcopy(policy.actor).cpu().eval()
    inputs = observations['policy'].detach().cpu()
    with torch.no_grad():
        expected, actual = actor(inputs), exported(inputs)
    delta = float((expected-actual).abs().max())
    if not torch.isfinite(actual).all() or delta > 1e-5:
        raise ValueError('Rough export/live parity failed')
    return {'max_abs_error': delta, 'sample_count': len(inputs), 'tolerance': 1e-5,
            'scope': 'CPU live actor versus exported actor on actual observations; same action adapter'}
