"""Declared paired terrain tests for final 21999 versus frozen upstream 19999."""
from dataclasses import asdict
import json
import numpy as np

from locomotion57_protocol import ROOT, DT, Case, Segment, sha256
from operating57_protocol import cases_for as flat_cases, protocol_manifest as flat_manifest

POLICIES = (19999, 21999)
SEED_START, SEEDS = 10201, 32
GEOMETRY_SEED = 20260927
TERRAINS = ('rough_04', 'boxes_10', 'slope_up_10', 'slope_down_10',
            'stairs_up_06', 'stairs_down_06', 'stairs_up_12', 'stairs_down_12',
            'stairs_up_18', 'stairs_down_18')
EXPORT_DIRS = {19999: ROOT/'policies/server/upstream_19999/export',
              21999: ROOT/'logs/fullcycle21999_validation_20260927/contract/policy-contract-export'}


def cases_for(terrain):
    if terrain not in TERRAINS:
        raise ValueError(terrain)
    if not terrain.startswith('stairs_'):
        return [Case(c.name, terrain, c.segments) for c in flat_cases()]
    zero = (0., 0., 0.)
    init, stop = Segment(2, zero, 'initialization'), Segment(12, zero)
    cases = [Case(f'traverse_{speed:.1f}', terrain, (init, Segment(20, (speed, 0, 0)), stop))
             for speed in (.3, .5, .7)]
    cases.append(Case('backward_traverse', terrain, (init, Segment(20, (-.3, 0, 0)), stop)))
    for speed, approach in ((.3, 5.), (.5, 4.)):
        cases.append(Case(f'stair_stop_restart_{speed:.1f}', terrain,
                         (init, Segment(approach, (speed, 0, 0)), stop, Segment(14, (speed, 0, 0)), stop)))
    cases.append(Case('stair_stop_reverse', terrain,
                     (init, Segment(5, (.3, 0, 0)), stop, Segment(8, (-.3, 0, 0)), stop)))
    for sign in (-1, 1):
        cases.append(Case(f'stair_stop_yaw_{sign:+d}', terrain,
                         (init, Segment(5, (.3, 0, 0)), stop, Segment(6, (0, 0, sign*.3)), stop)))
    return cases


def geometry(terrain):
    base = {'name': terrain, 'size_m': [80., 80.], 'geometry_seed': GEOMETRY_SEED,
            'start_height': 0., 'rough_patch_y': [-40., 40.], 'physical_edge_x': None}
    if terrain.startswith('stairs_'):
        height = int(terrain[-2:]) / 100
        base.update(kind='stairs', risers=12, first_edge_x=.8, step_width=.3,
                    last_edge_x=4.1, step_height=height, direction=1 if '_up_' in terrain else -1)
        if base['direction'] < 0:
            base['start_height'] = 12*height
    elif terrain.startswith('slope_'):
        base.update(kind='slope', angle_deg=10 if '_up_' in terrain else -10)
    elif terrain == 'rough_04':
        base.update(kind='rough', cell_m=.25, height_min_m=-.04, height_max_m=.04)
    elif terrain == 'boxes_10':
        base.update(kind='boxes', cell_m=.5, width_m=.4, height_min_m=.05, height_max_m=.10,
                    patch_min=-35., patch_max=35.)
    else:
        raise ValueError(terrain)
    return base


def surface_height(terrain, x, y):
    """Analytic top surface for stair exposure checks; x/y are local world coordinates."""
    cfg = geometry(terrain)
    x, y = np.broadcast_arrays(x, y)
    if cfg['kind'] == 'stairs':
        riser = np.clip(np.floor((x-cfg['first_edge_x'])/cfg['step_width'])+1, 0, cfg['risers'])
        return cfg['start_height'] + cfg['direction']*cfg['step_height']*riser
    if cfg['kind'] == 'slope':
        return x*np.tan(np.deg2rad(cfg['angle_deg']))
    return np.zeros_like(x)


def meshes_for(terrain):
    import trimesh
    cfg = geometry(terrain)

    def box(size, center):
        mesh = trimesh.creation.box(size)
        mesh.apply_translation(center)
        return mesh

    meshes = []
    if cfg['kind'] == 'stairs':
        meshes.append(box((80, 80, 2), (0, 0, -1)))
        h = cfg['step_height']
        for i in range(cfg['risers']):
            edge = cfg['first_edge_x'] + i*cfg['step_width']
            if cfg['direction'] > 0:
                lo, hi, top = edge, 40., (i+1)*h
            else:
                lo, hi, top = -40., edge, (cfg['risers']-i)*h
            meshes.append(box((hi-lo, 80, top), ((lo+hi)/2, 0, top/2)))
    elif cfg['kind'] == 'slope':
        angle = np.deg2rad(cfg['angle_deg'])
        mesh = trimesh.creation.box((80/np.cos(angle), 80, 2))
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-angle, [0, 1, 0]))
        mesh.apply_translation([0, 0, -1/np.cos(angle)])
        meshes.append(mesh)
    elif cfg['kind'] == 'rough':
        axis = np.linspace(-40., 40., 321)
        xx, yy = np.meshgrid(axis, axis, indexing='ij')
        zz = np.random.default_rng(GEOMETRY_SEED).uniform(-.04, .04, xx.shape)
        # A small level spawn patch shared by both policies; rough exposure begins outside it.
        zz[(np.abs(xx) <= .5) & (np.abs(yy) <= .5)] = 0
        vertices = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
        ids = np.arange(xx.size).reshape(xx.shape)
        a, b, c, d = (v.ravel() for v in (ids[:-1,:-1], ids[1:,:-1], ids[:-1,1:], ids[1:,1:]))
        faces = np.concatenate((np.column_stack((a,b,c)), np.column_stack((b,d,c))))
        meshes.append(trimesh.Trimesh(vertices=vertices, faces=faces, process=False))
    else:
        meshes.append(box((80, 80, 2), (0, 0, -1)))
        rng = np.random.default_rng(GEOMETRY_SEED)
        for x in np.arange(-34.75, 35, .5):
            for y in np.arange(-34.75, 35, .5):
                h = rng.uniform(.05, .10)
                if abs(x) < .75 and abs(y) < .75:
                    continue
                meshes.append(box((.4, .4, h), (x, y, h/2)))
    for mesh in meshes:
        mesh.apply_translation([40, 40, 0])
    return meshes, np.array([40., 40., cfg['start_height']])


def stair_exposure(terrain, root_xyz, wheel_xyz, wheel_up_force):
    cfg = geometry(terrain)
    height = surface_height(terrain, wheel_xyz[..., 0], wheel_xyz[..., 1])
    gap = wheel_xyz[..., 2] - .0875 - height
    supported = (wheel_up_force > 1.) & (gap >= -.03) & (gap <= .10)
    interior = (wheel_xyz[..., 0] >= cfg['first_edge_x']) & (wheel_xyz[..., 0] < cfg['last_edge_x'])
    return ((root_xyz[..., 0] >= cfg['first_edge_x']) & (root_xyz[..., 0] < cfg['last_edge_x'])
            & (supported.sum(axis=-1) >= 2) & (supported & interior).any(axis=-1))


def coverage(case, exposed, root_xyz, valid):
    cfg = geometry(case.terrain)
    if cfg['kind'] != 'stairs':
        return None
    schedule, _ = case.schedule()
    count = min(len(exposed), len(schedule))
    moving = np.any(schedule[:count] != 0, axis=1)
    motion_exposure_s = float(np.sum(exposed[:count] & valid[:count] & moving)*DT)
    windows, offset = [], 0
    for index, segment in enumerate(case.segments):
        length = round(segment.seconds/DT)
        # Only named stair-stop cases demand exposure; terminal stops after traversal may be on landings.
        required = case.name.startswith('stair_stop_') and not any(segment.command) and segment.kind != 'initialization' and index == 2
        if required:
            lo, hi = offset+round(2/DT), offset+length
            complete = hi <= len(valid) and bool(valid[lo:hi].all())
            fraction = float(exposed[lo:min(hi,len(exposed))].sum() / (hi-lo))
            windows.append({'segment': index, 'complete': complete, 'exposure_fraction': fraction,
                            'exposure_pass': bool(complete and fraction >= .9)})
        offset += length
    return {'moving_stair_exposure_s': motion_exposure_s, 'moving_exposure_pass': motion_exposure_s >= 1.,
            'zero_windows': windows, 'crossed_final_riser_diagnostic': bool(np.any(valid & (root_xyz[:,0] > cfg['last_edge_x']+.5)))}


def protocol_manifest(export_dirs=None):
    flat = flat_manifest()
    export_dirs = EXPORT_DIRS if export_dirs is None else export_dirs
    if len(export_dirs) != 2 or 10000 in export_dirs:
        raise ValueError('Select two distinct allowed policies')
    exports = {}
    for policy, folder in export_dirs.items():
        data = json.loads((folder/'manifest.json').read_text())['export_validation']
        if sha256(folder/'policy.pt') != data['export_sha256'] or data['checkpoint_iteration'] != policy:
            raise RuntimeError(f'Export identity mismatch: {policy}')
        exports[policy] = data
    return {'schema': 'fullcycle21999_validation_v1', 'policies': list(export_dirs),
            'terrain_seeds': list(range(SEED_START, SEED_START+SEEDS)),
            'flat_seeds': flat['reset_seeds'], 'flat_protocol': flat,
            'terrains': {name: {'geometry': geometry(name), 'cases': [asdict(c) for c in cases_for(name)]} for name in TERRAINS},
            'exports': exports, 'episodes_total': (36+sum(len(cases_for(t)) for t in TERRAINS))*SEEDS*2,
            'gates': {'rmse': [.2,.2,.25], 'response': .8, 'settling_s': 2., 'continuous_zero_s': 10.,
                      'zero_vxy': .1, 'zero_wz': .1, 'physics_safety_hz': 200, 'row_success_fraction': .99},
            'qualification': False, 'hardware_approval': False}


if __name__ == '__main__':
    print(json.dumps(protocol_manifest(), indent=2))
