"""Read the live training asset's collision geometry without changing the asset."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
from physics57_protocol import ROOT, sha256, save_json

BASE = ROOT/'logs/contact57_20260925'
GEOMETRY = BASE/'isaac_geometry.json'


def extract(env, robot, compiled):
    from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema
    cache = UsdGeom.XformCache()
    root = env.sim.stage.GetPrimAtPath('/World/envs/env_0/Robot')
    shapes = []
    for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies()):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        if not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():
            continue
        body = prim
        while body and body.GetName() not in robot.body_names:
            body = body.GetParent()
        assert body, str(prim.GetPath())
        inverse = cache.GetLocalToWorldTransform(body).GetInverse()
        nodes = [prim] if prim.GetTypeName() in ('Cube', 'Cylinder', 'Mesh') else [
            p for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Mesh)]
        assert len(nodes) == 1, (str(prim.GetPath()), len(nodes))
        node = nodes[0]
        # Gf uses row vectors; transpose for conventional column-vector matrices.
        transform = np.asarray(cache.GetLocalToWorldTransform(node)*inverse).T
        collision = PhysxSchema.PhysxCollisionAPI(prim)
        mesh_collision = UsdPhysics.MeshCollisionAPI(prim)
        item = {'body':body.GetName(), 'path':str(prim.GetPath()), 'geometry_path':str(node.GetPath()),
            'type':node.GetTypeName(), 'local_to_body':transform.tolist(),
            'approximation':mesh_collision.GetApproximationAttr().Get() if mesh_collision else None,
            'contact_offset_authored':collision.GetContactOffsetAttr().HasAuthoredValueOpinion(),
            'contact_offset_schema_value':collision.GetContactOffsetAttr().Get(),
            'rest_offset_authored':collision.GetRestOffsetAttr().HasAuthoredValueOpinion(),
            'rest_offset_schema_value':collision.GetRestOffsetAttr().Get()}
        if node.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(node)
            points = np.asarray(mesh.GetPointsAttr().Get(), dtype=float)
            item['points_body_m'] = (points@transform[:3,:3].T+transform[:3,3]).tolist()
            item['face_vertex_counts'] = list(mesh.GetFaceVertexCountsAttr().Get())
            item['face_vertex_indices'] = list(mesh.GetFaceVertexIndicesAttr().Get())
        elif node.IsA(UsdGeom.Cube):
            item['size'] = UsdGeom.Cube(node).GetSizeAttr().Get()
        elif node.IsA(UsdGeom.Cylinder):
            shape = UsdGeom.Cylinder(node)
            item.update(radius=shape.GetRadiusAttr().Get(), height=shape.GetHeightAttr().Get(),
                        axis=shape.GetAxisAttr().Get())
        shapes.append(item)
    assert len(shapes) == 20
    save_json(GEOMETRY, {'schema':'contact57_usd_geometry_v1', 'shapes':shapes,
        'compiled':compiled, 'self_collision':env.cfg.scene.robot.spawn.articulation_props.enabled_self_collisions,
        'terrain_material':str(env.cfg.scene.terrain.physics_material),
        'note':'USD source hull vertices, not PhysX cooked hulls; schema defaults are not runtime offset readback',
        'source_sha256':sha256(__file__), 'harness_sha256':sha256(BASE/'generated_export_geometry.py'),
        'asset_config_sha256':sha256(ROOT/'scripts/local_b2w_assets.py')})
    print('DONE', GEOMETRY, flush=True)


if __name__ == '__main__':
    if GEOMETRY.exists():
        raise FileExistsError(GEOMETRY)
    source = ROOT/'scripts/probe_physics57_isaac.py'
    code = source.read_text(encoding='utf-8')
    code = code[:code.index('    roots = robot.data.default_root_state.clone()')]+\
        '    from export_contact57_geometry import extract\n    extract(env, robot, compiled)\n'+\
        code[code.index('except BaseException:'):]
    code = code.replace("output = BASE/f'{tag}.json'", "output = ROOT/'logs/contact57_20260925/isaac_geometry.json'")
    BASE.mkdir(parents=True, exist_ok=True)
    generated = BASE/'generated_export_geometry.py'
    if generated.exists():
        raise FileExistsError(generated)
    generated.write_text(code, encoding='utf-8')
    sys.argv = [str(generated),'--suite','contact','--dt','.005']
    exec(compile(code,str(generated),'exec'),{'__file__':str(generated),'__name__':'__main__'})
