"""Instrument-only repair: direct PhysX reports support static triangle meshes.

The initial replay and its unsupported GPU filter are retained unchanged.
This asserted wrapper changes only observation of contacts and output names.
"""
from pathlib import Path

source = Path(__file__).with_name('replay57_isaac.py').read_text(encoding='utf-8')
source = source.replace('isaac_nominal','isaac_contactreports')
begin = source.index('def point_contacts(')
end = source.index('\nenv = None',begin)
replacement = '''def point_contacts(com, velocity):
    from omni.physx import get_physx_simulation_interface
    from pxr import PhysicsSchemaTools
    import re
    headers, data = get_physx_simulation_interface().get_contact_report()
    if not hasattr(point_contacts,'printed'):
        print('CONTACT_DEBUG',len(headers),len(data),flush=True)
        for h in headers[:4]:
            print('PAIR_DEBUG',[str(PhysicsSchemaTools.intToSdfPath(v)) for v in
                (h.actor0,h.actor1,h.collider0,h.collider1)],h.num_contact_data,flush=True)
        point_contacts.printed = True
    result = np.zeros((4,4,3))
    for h in headers:
        actors = [str(PhysicsSchemaTools.intToSdfPath(v)) for v in (h.actor0,h.actor1)]
        colliders = [str(PhysicsSchemaTools.intToSdfPath(v)) for v in (h.collider0,h.collider1)]
        if not any(p.startswith('/World/ground/') for p in colliders):
            continue
        match = next((re.search(r'/env_(\\d+)/Robot/(FR|FL|RR|RL)_foot$',p) for p in actors
                      if re.search(r'/env_(\\d+)/Robot/(FR|FL|RR|RL)_foot$',p)),None)
        if match is None:
            continue
        i,w = int(match[1]),('FR','FL','RR','RL').index(match[2])
        for k in range(h.contact_data_offset,h.contact_data_offset+h.num_contact_data):
            c = data[k]
            p,normal,impulse = [np.array([v[0],v[1],v[2]]) for v in (c.position,c.normal,c.impulse)]
            force = abs(np.dot(impulse,normal))/PHYSICS_DT
            if force < 5.:
                continue
            v = velocity[i,w,:3]+np.cross(velocity[i,w,3:],p-com[i,w])
            tangent = v-np.dot(v,normal)*normal
            result[i,w] += [force,force*np.dot(tangent,tangent),1]
    return result,int(result[...,2].max())

'''
source = source[:begin]+replacement+source[end:]
block = """    for leg in ('FR','FL','RR','RL'):
        setattr(cfg.scene,f'replay_{leg}',ContactSensorCfg(
            prim_path=f'{{ENV_REGEX_NS}}/Robot/{leg}_foot',update_period=PHYSICS_DT,
            filter_prim_paths_expr=['/World/ground/terrain'],max_contact_data_count_per_prim=64))
"""
assert source.count(block)==1
source = source.replace(block,'')
block = """                measured = []
                for w,leg in enumerate(('FR','FL','RR','RL')):
                    slip,count = point_contacts(scene[f'replay_{leg}'],com[:,w],velocity[:,w])
                    max_contacts = max(max_contacts,count)
                    measured.append(slip)
                arrays['physics_contact'].append(np.stack(measured,axis=1))
"""
assert source.count(block)==1
source = source.replace(block,"""                measured,count = point_contacts(com,velocity)
                max_contacts = max(max_contacts,count)
                arrays['physics_contact'].append(measured)
                if step == 5 and sub == 9 and max_contacts == 0:
                    raise RuntimeError('Direct contact report contains no loaded wheel contacts')
""")
source = source.replace("'contact_filter':'/World/ground/terrain','contact_capacity_per_wheel':64,",
    "'contact_filter':'direct PhysX reports, ground collider + wheel actor','contact_capacity_per_wheel':None,")
source = source.replace('if max_contacts >= 64 or arrays','if arrays')
exec(compile(source,str(Path(__file__).with_name('replay57_isaac.py')),'exec'))
