"""Freeze source hulls and the bounded contact diagnosis before outcome runs."""
import json
import numpy as np
from scipy.spatial import ConvexHull
from physics57_protocol import ROOT, save_json, sha256
from export_contact57_geometry import GEOMETRY as RAW
from contact57_model import CONFIG, GEOMETRY, URDF, VARIANTS


def main():
    source = json.loads(RAW.read_text())
    for shape in source['shapes']:
        if shape['type'] != 'Mesh':
            continue
        assert shape['approximation'] == 'convexHull'
        points = np.unique(np.asarray(shape.pop('points_body_m')),axis=0)
        hull = ConvexHull(points)
        vertices = points[hull.vertices]
        shape.pop('face_vertex_counts')
        shape.pop('face_vertex_indices')
        shape['hull_vertices_body_m'] = vertices.tolist()
        shape['original_unique_vertices'] = len(points)
        shape['bounds_body_m'] = [points.min(axis=0).tolist(),points.max(axis=0).tolist()]
        shape['hull_volume_m3'] = float(hull.volume)
        print(shape['body'],len(points),'->',len(vertices),'bounds',shape['bounds_body_m'])
    source['raw_export_sha256'] = sha256(RAW)
    source['urdf_sha256'] = sha256(URDF)
    source['preparation_source_sha256'] = sha256(__file__)
    save_json(GEOMETRY,source)
    old = json.loads((ROOT/'configs/physics57_diagnostics_20260925.json').read_text())
    screen = old['micro_screen']
    screen['variants'] = ['source_shapes']
    screen['criteria'] = 'unchanged locomotion57_v1; 40 new episodes paired with 40 existing mechanics_implicit controls'
    save_json(CONFIG,{'schema':'contact57_diagnostics_v1',
        'purpose':'training-source collision/frame diagnosis; not hardware identification or release qualification',
        'geometry_sha256':sha256(GEOMETRY),'variants':VARIANTS,
        'semantics':{'mechanics_control':'exact previous mechanics_implicit control',
            'frames':'control plus exact movable URDF joint origins/axes',
            'frames_masks':'frames plus no self-collisions, preserving vendor physical geometry',
            'source_shapes':'frames_masks with 20 training USD collision primitives/convex hulls'},
        'contact_states_config':'configs/physics57_contact_states_20260925.json',
        'contact_states_config_sha256':sha256(ROOT/'configs/physics57_contact_states_20260925.json'),
        'dt_s':[.005,.002,.001], 'state_reset_horizon_s':.1,
        'contact_solver':'MuJoCo defaults unchanged; not asserted equivalent to PhysX restitution or cooked hulls',
        'static_tolerance':{'body_pose_m':1e-5,'body_orientation_rad':1e-4,'shape_support_m':1e-6},
        'micro_screen':screen,
        'selection':'source_shapes selected from asset correspondence before outcomes; do not select physics by policy score',
        'not_covered':['PhysX cooked hull simplification','measured hardware contacts','solver/restitution equivalence',
            'full policy qualification','new training'], 'source_sha256':sha256(__file__)})


if __name__ == '__main__':
    main()
