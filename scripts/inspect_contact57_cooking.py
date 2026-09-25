"""Cook an explicit isolated copy of each training mesh; no policy inference."""
from __future__ import annotations
import json
import sys
import numpy as np
from physics57_protocol import ROOT, save_json, sha256

BASE = ROOT/'logs/contact57b_20260925'
OUTPUT = BASE/'cooking.json'


def extract(env, robot, compiled):
    from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, UsdUtils, PhysicsSchemaTools, Sdf, Vt, Gf
    from omni.physx import get_physx_cooking_interface
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageMetersPerUnit(stage,1.)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    stage_id = UsdUtils.StageCache.Get().Insert(stage).ToLongInt()
    raw_path = ROOT/'logs/contact57_20260925/isaac_geometry.json'
    source = json.loads(raw_path.read_text())
    rows = []
    for i,shape in enumerate(source['shapes']):
        if shape['type'] != 'Mesh':
            continue
        original = env.sim.stage.GetPrimAtPath(shape['path'])
        original_mesh = env.sim.stage.GetPrimAtPath(shape['geometry_path'])
        body = UsdGeom.Xform.Define(stage,f'/Body{i}')
        UsdPhysics.RigidBodyAPI.Apply(body.GetPrim())
        mesh = UsdGeom.Mesh.Define(stage,f'/Body{i}/Mesh')
        mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.asarray(shape['points_body_m'],np.float32)))
        mesh.CreateFaceVertexCountsAttr(shape['face_vertex_counts'])
        mesh.CreateFaceVertexIndicesAttr(shape['face_vertex_indices'])
        prim = mesh.GetPrim()
        UsdPhysics.CollisionAPI.Apply(prim)
        UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr('convexHull')
        copied = {}
        for node in (original,original_mesh):
            for schema in node.GetAppliedSchemas():
                if schema.startswith('Physx'):
                    prim.AddAppliedSchema(schema)
            for attr in node.GetAttributes():
                name = str(attr.GetName())
                if name.startswith('physx') and attr.HasAuthoredValueOpinion():
                    prim.CreateAttribute(name,attr.GetTypeName()).Set(attr.Get())
                    copied[name] = str(attr.Get())
        # Apply only schema APIs to read their fallback values, not overrides.
        hull = PhysxSchema.PhysxConvexHullCollisionAPI.Apply(prim)
        collision = PhysxSchema.PhysxCollisionAPI.Apply(prim)
        defaults = {str(a.GetName()):str(a.Get()) for a in prim.GetAttributes() if str(a.GetName()).startswith('physx')}
        received = []
        def callback(status, convexes):
            received.append({'status':str(status),'hulls':[
                {'vertices_body_m':[[float(v.x),float(v.y),float(v.z)] for v in c.vertices],
                 'indices':list(c.indices),'polygons':[
                     {'index_base':p.index_base,'num_vertices':p.num_vertices,
                      'plane':[float(p.plane.x),float(p.plane.y),float(p.plane.z),float(p.plane.w)]}
                     for p in c.polygons]} for c in convexes]})
        get_physx_cooking_interface().request_convex_collision_representation(
            stage_id=stage_id,collision_prim_id=PhysicsSchemaTools.sdfPathToInt(prim.GetPath()),
            run_asynchronously=False,on_result=callback)
        assert len(received)==1
        rows.append({'body':shape['body'],'source_path':shape['path'],
            'source_applied_schemas':list(original.GetAppliedSchemas()),
            'mesh_applied_schemas':list(original_mesh.GetAppliedSchemas()),
            'copied_authored_properties':copied,'copy_schema_defaults':defaults,**received[0]})
        print('COOK',shape['body'],received[0]['status'],[len(h['vertices_body_m']) for h in received[0]['hulls']],flush=True)
    stage.GetRootLayer().Export(str(BASE/'isolated_cooking.usda'))
    save_json(OUTPUT,{'schema':'contact57b_isolated_cooking_v1','rows':rows,
        'provenance':'explicit non-instanced meshes with source points, topology and authored PhysX settings; isolated cooking result, not live shape memory readback',
        'raw_source_sha256':sha256(raw_path),'source_sha256':sha256(__file__),
        'stage_sha256':sha256(BASE/'isolated_cooking.usda')})
    print('DONE',OUTPUT,flush=True)


if __name__=='__main__':
    assert not OUTPUT.exists()
    BASE.mkdir(parents=True,exist_ok=True)
    code = (ROOT/'logs/contact57_20260925/generated_export_geometry.py').read_text(encoding='utf-8')
    code = code.replace('from export_contact57_geometry import extract','from inspect_contact57_cooking import extract')
    code = code.replace('contact57_20260925/isaac_geometry.json','contact57b_20260925/cooking.json')
    generated = BASE/'generated_inspect_cooking.py'
    assert not generated.exists()
    generated.write_text(code,encoding='utf-8')
    sys.argv = [str(generated),'--suite','contact','--dt','.005']
    exec(compile(code,str(generated),'exec'),{'__file__':str(generated),'__name__':'__main__'})
