"""Isolated armature factor with DC law and strict guard unchanged."""
from __future__ import annotations
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from run_support import ROOT, read_json, sha256, write_json
from sim2sim_actuator_factor import make_dc_scene


def armature_parameters(cfg,plan):
    path=ROOT/plan['physx_snapshot']
    if sha256(path)!=plan['physx_snapshot_sha256']:raise ValueError('Live snapshot changed')
    snapshot=read_json(path)
    if not snapshot['live_physx']:raise ValueError('Live PhysX required')
    values=np.asarray(snapshot['joint_physx']['armature'])
    if values.shape!=(16,) or not np.isfinite(values).all():raise ValueError('Invalid armature snapshot')
    result=[float(values[snapshot['joint_names'].index(name)]) for name in cfg['joint_names']]
    if result!=[0.]*16:raise ValueError('Frozen zero-armature factor changed')
    return result


def make_armature_scene(directory,cfg,plan):
    path=make_dc_scene(directory,cfg,plan);document=ET.fromstring(path.read_text())
    values=armature_parameters(cfg,plan)
    for name,value in zip(cfg['joint_names'],values):
        item=document.find(f".//joint[@name='{name.replace('_foot_joint','_wheel_joint')}']")
        if item is None:raise ValueError('Missing actuator joint '+name)
        item.set('armature',format(value,'.17g'))
    path.write_text(ET.tostring(document,encoding='unicode'))
    write_json(directory/'armature_parameters.json',{'joint_names':cfg['joint_names'],'armature_kg_m2':values})
    return path


def armature_invariants(baseline_path,factor_path,cfg,plan):
    original=ET.fromstring(baseline_path.read_text());restored=ET.fromstring(factor_path.read_text())
    values=armature_parameters(cfg,plan)
    for name in cfg['joint_names']:
        name=name.replace('_foot_joint','_wheel_joint')
        a=original.find(f".//joint[@name='{name}']");b=restored.find(f".//joint[@name='{name}']")
        if a is None or b is None:raise ValueError('Missing joint')
        if 'armature' in a.attrib:b.set('armature',a.get('armature'))
        else:b.attrib.pop('armature',None)
    if ET.tostring(original)!=ET.tostring(restored):raise ValueError('Unexpected non-armature XML change')
    a=mujoco.MjModel.from_xml_path(str(baseline_path));b=mujoco.MjModel.from_xml_path(str(factor_path))
    dofs=a.jnt_dofadr[a.actuator_trnid[:,0]]
    if not np.array_equal(a.dof_armature[dofs],np.full(16,.1)):raise ValueError('DC baseline armature changed')
    expected=a.dof_armature.copy();expected[dofs]=values
    if not np.array_equal(b.dof_armature,expected):raise ValueError('Unexpected armature DOF change')
    # These are compiled inverse inertia / unit actuator acceleration derived
    # from the changed generalized inertia, rather than additional parameters.
    derived={'actuator_acc0','body_invweight0','dof_invweight0','dof_M0'}
    inertia_error=float(np.max(np.abs((b.dof_M0-a.dof_M0)-(b.dof_armature-a.dof_armature))))
    if inertia_error>1e-12:raise ValueError('Generalized inertia changed beyond armature contribution')
    equal=[];changed=[]
    for name in dir(a):
        if name.startswith('_') or name=='dof_armature':continue
        x=getattr(a,name)
        if isinstance(x,np.ndarray):
            if np.array_equal(x,getattr(b,name),equal_nan=True):equal.append(name)
            elif name in derived:changed.append(name)
            else:raise ValueError('Unexpected compiled array change '+name)
    for name in ('nq','nv','nu','nbody','njnt','ngeom','nsensor','nkey','nnumeric'):
        if getattr(a,name)!=getattr(b,name):raise ValueError('Unexpected model count change '+name)
    for name in dir(a.opt):
        x=getattr(a.opt,name)
        if isinstance(x,(float,int,np.ndarray)) and not np.array_equal(x,getattr(b.opt,name)):
            raise ValueError('Unexpected physics option change '+name)
    return {'passed':True,'equal_compiled_arrays':equal,'changed_derived_arrays':changed,
        'baseline_armature_kg_m2':a.dof_armature[dofs].tolist(),'factor_armature_kg_m2':b.dof_armature[dofs].tolist(),
        'passive_damping':b.dof_damping[dofs].tolist(),'total_mass_kg':float(b.body_mass.sum()),
        'physics_dt_s':b.opt.timestep,'control_caps_nm':b.actuator_ctrlrange.tolist(),
        'diagonal_inertia_delta_vs_armature_max_error_kg_m2':inertia_error}
