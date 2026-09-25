"""Validate compiled cooked hulls and quantify the source-to-cooked difference."""
import json
import numpy as np
from scipy.spatial import ConvexHull
from contact57_model import geometry
from contact57b_model import BASE,CONFIG,COOKED,make_model
from probe_contact57 import source_support,model_support
from physics57_protocol import ROOT,sha256,save_json


def main():
    original=geometry()
    cooked=json.loads(COOKED.read_text())
    model,_=make_model('cooked_shapes')
    directions=np.random.default_rng(20260925).normal(size=(4096,3))
    directions/=np.linalg.norm(directions,axis=1,keepdims=True)
    directions=np.r_[directions,np.eye(3),-np.eye(3)]
    rows=[]
    for i,(source,shape) in enumerate(zip(original['shapes'],cooked['shapes'])):
        geom=model.geom(f'contact57_{i}').id
        error=float(np.max(np.abs(model_support(model,geom,directions)-source_support(shape,directions))))
        assert error<1e-6,(shape['body'],error)
        if shape['type']=='Mesh':
            before=np.asarray(source['hull_vertices_body_m'])
            after=np.asarray(shape['hull_vertices_body_m'])
            delta=source_support(shape,directions)-source_support(source,directions)
            assert np.max(np.abs(after.mean(axis=0)-before.mean(axis=0)))<.10
            rows.append({'body':shape['body'],'source_vertices':len(before),'cooked_vertices':len(after),
                'max_abs_support_delta_m':float(np.max(np.abs(delta))),
                'support_delta_min_m':float(delta.min()),'support_delta_max_m':float(delta.max()),
                'source_volume_m3':float(ConvexHull(before).volume),'cooked_volume_m3':float(ConvexHull(after).volume),
                'cooked_bounds_body_m':[after.min(axis=0).tolist(),after.max(axis=0).tolist()],
                'compiled_support_error_m':error})
    active=(model.geom_bodyid!=0)&((model.geom_contype!=0)|(model.geom_conaffinity!=0))
    assert active.sum()==20
    save_json(BASE/'static.json',{'rows':rows,'active_shapes':int(active.sum()),
        'config_sha256':sha256(CONFIG),'cooked_geometry_sha256':sha256(COOKED),
        'source_sha256':sha256(__file__),'adapter_sha256':sha256(ROOT/'scripts/contact57b_model.py')})
    for row in rows:
        print(row['body'],row['source_vertices'],row['cooked_vertices'],row['max_abs_support_delta_m'])
    print('DONE static',flush=True)


if __name__=='__main__':
    main()
