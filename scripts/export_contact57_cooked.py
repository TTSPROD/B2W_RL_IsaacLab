"""Inspect PhysX collision cooking through its installed public readback API."""
import sys
import numpy as np
from physics57_protocol import ROOT, sha256, save_json
from contact57_model import BASE, geometry


def extract(env, robot, compiled):
    from pxr import UsdUtils, PhysicsSchemaTools
    from omni.physx import get_physx_cooking_interface
    stage_id = UsdUtils.StageCache.Get().GetId(env.sim.stage).ToLongInt()
    results = []
    for shape in geometry()['shapes']:
        if shape['type'] != 'Mesh':
            continue
        received = []
        def on_result(status, convexes):
            received.append({'status':str(status),'hulls':[
                {'vertices':[[float(v.x),float(v.y),float(v.z)] for v in hull.vertices],
                 'indices':list(hull.indices),
                 'polygons':[{'index_base':p.index_base,'num_vertices':p.num_vertices,
                    'plane':[float(p.plane.x),float(p.plane.y),float(p.plane.z),float(p.plane.w)]}
                    for p in hull.polygons]} for hull in convexes]})
        get_physx_cooking_interface().request_convex_collision_representation(
            stage_id=stage_id, collision_prim_id=PhysicsSchemaTools.sdfPathToInt(shape['path']),
            run_asynchronously=False, on_result=on_result)
        assert len(received) == 1, (shape['path'],received)
        results.append({'body':shape['body'],'path':shape['path'],**received[0]})
        print('COOKED',shape['body'],received[0]['status'],[len(h['vertices']) for h in received[0]['hulls']],flush=True)
    save_json(BASE/'isaac_cooked.json',{'results':results,'source_sha256':sha256(__file__),
        'harness_sha256':sha256(BASE/'generated_export_cooked.py'),
        'note':'public PhysX cooking representation; coordinate frame checked separately against source hull'})
    print('DONE cooked export',flush=True)


if __name__ == '__main__':
    assert not (BASE/'isaac_cooked.json').exists()
    code = (BASE/'generated_export_geometry.py').read_text(encoding='utf-8')
    code = code.replace('from export_contact57_geometry import extract','from export_contact57_cooked import extract')
    code = code.replace('contact57_20260925/isaac_geometry.json','contact57_20260925/isaac_cooked.json')
    generated = BASE/'generated_export_cooked.py'
    assert not generated.exists()
    generated.write_text(code,encoding='utf-8')
    sys.argv = [str(generated),'--suite','contact','--dt','.005']
    exec(compile(code,str(generated),'exec'),{'__file__':str(generated),'__name__':'__main__'})
