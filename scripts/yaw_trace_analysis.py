"""Offline geometric/actuator diagnostics of passive yaw traces."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import sha256

MESH_DIR=ROOT/'vendor/robot_lab/source/robot_lab/data/Robots/unitree/b2w_description/meshes'


def rotate(q, v):
    xyz=q[...,1:]
    uv=np.cross(xyz,v)
    return v+2*(q[...,:1]*uv+np.cross(xyz,uv))


def mesh_vertices(name):
    path=MESH_DIR/(name+'.dae')
    r=ET.parse(path).getroot();ns={'c':r.tag.split('}')[0][1:]}
    assert r.find('c:asset/c:up_axis',ns).text=='Z_UP'
    unit=float(r.find('c:asset/c:unit',ns).get('meter'))
    blocks=[]
    nodes=r.findall('c:library_visual_scenes/c:visual_scene/c:node',ns)
    for node in nodes:
        assert node.find('c:node',ns) is None
        assert not any(node.find('c:'+t,ns) is not None for t in ('translate','rotate','scale'))
        mat=np.fromstring(node.find('c:matrix',ns).text,sep=' ').reshape(4,4)
        for inst in node.findall('c:instance_geometry',ns):
            geom=r.find(".//c:geometry[@id='"+inst.get('url')[1:]+"']",ns)
            src=geom.find('.//c:vertices/c:input',ns)
            assert src.get('semantic')=='POSITION'
            source=geom.find(".//c:source[@id='"+src.get('source')[1:]+"']",ns)
            v=np.fromstring(source.find('c:float_array',ns).text,sep=' ').reshape(-1,3)
            blocks.append((np.c_[v,np.ones(len(v))]@mat.T)[:,:3]*unit)
    points=np.unique(np.concatenate(blocks),axis=0)
    # Convex hull preserves all directional minima of the source vertices.
    from scipy.spatial import ConvexHull
    points=points[ConvexHull(points).vertices]
    return points, {'source':str(path.relative_to(ROOT)),'sha256':sha256(path),
                    'bounds_m':[points.min(0).tolist(),points.max(0).tolist()]}


def bottom_point(pos, quat, points):
    inverse=quat.copy();inverse[...,1:]*=-1
    local_z=rotate(inverse,np.broadcast_to([0.,0.,1.],quat.shape[:-1]+(3,)))
    heights=local_z@points.T
    low=points[np.argmin(heights,axis=-1)]
    offset=rotate(quat,low)
    return pos[...,2]+offset[...,2],offset


def load_trace(report):
    p=Path(report['yaw_trace']['path'])
    assert p.is_relative_to(ROOT) and sha256(p)==report['yaw_trace']['sha256']
    with np.load(p,allow_pickle=False) as f:
        arrays={k:f[k] for k in f.files if k!='metadata_json'}
        meta=json.loads(str(f['metadata_json']))
    return arrays,meta


def window_metrics(arr,meta,env,start,end,geometry):
    e=meta['env_ids'].index(env)
    mask=(arr['time_s']>=start)&(arr['time_s']<end-1e-7)
    if not mask.any(): raise ValueError('Empty comparison window')
    computed=arr['computed_torque'][mask,e,:12];applied=arr['applied_torque'][mask,e,:12]
    clipped=np.abs(computed-applied)>1e-3
    out={'samples':int(mask.sum()),'any_leg_clipping_fraction':float(clipped.any(1).mean()),
         'leg_clipping_fraction_by_joint':dict(zip(meta['policy_joint_names'][:12],clipped.mean(0).tolist())),
         'leg_torque_clip_delta_max_nm':float(np.abs(computed-applied).max()),
         'rms_vx_vy_yaw':np.sqrt(np.mean((arr['actual'][mask,e]-arr['command'][mask,e])**2,axis=0)).tolist(),
         'bodies':{}}
    for b,name in enumerate(meta['body_names']):
        pos=arr['body_pos'][mask,e,b];q=arr['body_quat'][mask,e,b]
        clearance,offset=bottom_point(pos,q,geometry[name])
        force=np.linalg.norm(arr['contact_force'][mask,e,b],axis=-1)
        row={'source_mesh_min_clearance_m':float(clearance.min()),'source_mesh_median_clearance_m':float(np.median(clearance)),
             'max_contact_n':float(force.max())}
        if name.endswith('_foot'):
            velocity=arr['body_lin_vel'][mask,e,b]+np.cross(arr['body_ang_vel'][mask,e,b],offset)
            axle=rotate(q,np.broadcast_to([0.,1.,0.],pos.shape));axle[:,2]=0
            axle/=np.maximum(np.linalg.norm(axle,axis=1,keepdims=True),1e-8)
            roll=np.cross(axle,np.broadcast_to([0.,0.,1.],pos.shape))
            loaded=force>1.
            row['loaded_fraction']=float(loaded.mean())
            if loaded.any():
                lateral=np.abs((velocity*axle).sum(1))[loaded]
                longitudinal=np.abs((velocity*roll).sum(1))[loaded]
                row.update(bottom_point_lateral_speed_mean_m_s=float(lateral.mean()),
                           bottom_point_lateral_speed_p95_m_s=float(np.quantile(lateral,.95)),
                           bottom_point_longitudinal_speed_mean_m_s=float(longitudinal.mean()),
                           bottom_point_longitudinal_speed_p95_m_s=float(np.quantile(longitudinal,.95)))
        out['bodies'][name]=row
    return out


def analyze_profile(profile,seed):
    directory=ROOT/'logs/qualification/staged_yaw_diagnostics_20260918'
    reports={a:json.loads((directory/f'{a}_{profile}_{seed}.json').read_text()) for a in ('seed49','seed50','seed51','reference')}
    traces={a:load_trace(r) for a,r in reports.items()}
    names=traces['seed49'][1]['body_names']
    loaded={n:mesh_vertices(n) for n in names}
    geometry={n:v[0] for n,v in loaded.items()}
    result={'profile':profile,'geometry':{n:v[1] for n,v in loaded.items()},'matched_prefailure_windows':[]}
    for failed_arm in ('seed50','seed51'):
        for failure in reports[failed_arm]['first_failures']:
            start=max(2.,failure['time_s']-.5);end=failure['time_s']
            row={'failed_arm':failed_arm,'env':failure['env'],'first_failure':failure,'window_s':[start,end], 'policies':{}}
            for arm,(arr,meta) in traces.items():
                row['policies'][arm]=window_metrics(arr,meta,failure['env'],start,end,geometry)
                prior_fail=[f for f in reports[arm]['first_failures'] if f['env']==failure['env'] and f['time_s']<end]
                row['policies'][arm]['already_failed_before_window_end']=bool(prior_fail)
            result['matched_prefailure_windows'].append(row)
    result['limitations']=[
        'Source DAE support clearance is a proxy: actual PhysX cooked hull/contact offsets may differ.',
        'Bottom mesh point velocity is a kinematic slip proxy, not solver contact-point velocity; evaluated only at wheel force >1 N.',
        'Implicit wheel torque is estimated; clipping analysis above uses explicit leg motors only.',
        'Matched windows use identical command/initial-state cases; another policy may already have failed (flag recorded).',
        'Correlations before contact do not establish causation; disclosed cases are diagnostic, not independent acceptance.']
    return result
