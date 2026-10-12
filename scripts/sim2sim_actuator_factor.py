"""Leg actuator-law factor from saved live PhysX, outside pinned assets."""
from __future__ import annotations
import csv
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
import torch
from run_support import ROOT, read_json, sha256, write_json
from run_sim2sim_physics import make_scene
from sim2sim_physics_audit import reference_clip


def parameters(cfg, plan):
    path=ROOT/plan['physx_snapshot']
    if sha256(path)!=plan['physx_snapshot_sha256']:raise ValueError('Live PhysX snapshot changed')
    snapshot=read_json(path)
    if not snapshot['live_physx']:raise ValueError('Resolved live snapshot required')
    result={key:[] for key in ('effort','saturation','velocity')}
    for i,name in enumerate(cfg['joint_names'][:12]):
        group=snapshot['actuator_models'][name.split('_')[1]]
        if group['class']!='isaaclab.actuators.actuator_pd.DCMotor':raise ValueError('Wrong leg actuator')
        resolved=group['resolved'];index=resolved['joint_names'].index(name)
        def value(key):
            values=np.asarray(resolved[key])[:,index]
            if not np.all(values==values[0]):raise ValueError('Environment-dependent actuator parameter')
            return float(values[0])
        effort=value('effort_limit');velocity=value('velocity_limit')
        if (effort!=cfg['torque_limits'][i] or velocity!=cfg['isaac_velocity_limits'][i]
            or value('stiffness')!=cfg['rl_kp'][i] or value('damping')!=cfg['rl_kd'][i]):
            raise ValueError('Resolved actuator/export contract disagreement')
        result['effort'].append(effort);result['velocity'].append(velocity)
        result['saturation'].append(float(group['cfg']['saturation_effort']))
    return result


def make_dc_scene(directory,cfg,plan):
    path=make_scene(directory,cfg,plan);document=ET.fromstring(path.read_text())
    motors=list(document.find('actuator'))
    if len(motors)!=16:raise ValueError('Actuator count changed')
    values=parameters(cfg,plan)
    for i in range(12):
        # First 12 slot ordering was validated by the original scene factory.
        motors[i].set('ctrlrange',f"{-values['effort'][i]:.17g} {values['effort'][i]:.17g}")
    custom=document.find('custom')
    if custom is None:custom=ET.SubElement(document,'custom')
    for key,label in [('effort','dc_effort_limits'),('saturation','dc_saturation_efforts'),('velocity','dc_velocity_limits')]:
        ET.SubElement(custom,'numeric',name=label,data=' '.join(format(x,'.17g') for x in values[key]))
    path.write_text(ET.tostring(document,encoding='unicode'))
    write_json(directory/'actuator_parameters.json',values)
    return path


def model_invariants(baseline_path,factor_path,cfg):
    original=ET.fromstring(baseline_path.read_text());restored=ET.fromstring(factor_path.read_text())
    for x,y in zip(original.find('actuator'),restored.find('actuator')):
        y.set('ctrlrange',x.get('ctrlrange'))
    for label in ('dc_effort_limits','dc_saturation_efforts','dc_velocity_limits'):
        item=restored.find(f"custom/numeric[@name='{label}']")
        if item is None:raise ValueError('Missing declared DC parameter table')
        restored.find('custom').remove(item)
    if ET.tostring(original)!=ET.tostring(restored):raise ValueError('Unexpected source XML change')
    a=mujoco.MjModel.from_xml_path(str(baseline_path));b=mujoco.MjModel.from_xml_path(str(factor_path))
    compared=[]
    for name in dir(a):
        if name.startswith(('_','numeric_','name_')) or name in ('names','names_map','actuator_ctrlrange'):continue
        value=getattr(a,name)
        if isinstance(value,np.ndarray):
            # Some pinned visual mesh polygon normals contain NaNs. Require
            # identical NaN placement as well as identical finite values.
            if not np.array_equal(value,getattr(b,name),equal_nan=True):raise ValueError('Unexpected model array change: '+name)
            compared.append(name)
    for name in ('nq','nv','nu','nbody','njnt','ngeom','nsensor','nkey'):
        if getattr(a,name)!=getattr(b,name):raise ValueError('Unexpected model count change: '+name)
    for name in dir(a.opt):
        x=getattr(a.opt,name)
        if isinstance(x,(int,float,np.ndarray)) and not np.array_equal(x,getattr(b.opt,name)):
            raise ValueError('Unexpected physics option change: '+name)
    expected=a.actuator_ctrlrange.copy();expected[:12,0]=-np.asarray(cfg['torque_limits'][:12]);expected[:12,1]=cfg['torque_limits'][:12]
    if not np.array_equal(expected,b.actuator_ctrlrange):raise ValueError('Unexpected ctrl cap change')
    return {'passed':True,'equal_compiled_arrays':compared,'baseline_caps':a.actuator_ctrlrange.tolist(),
            'factor_caps':b.actuator_ctrlrange.tolist(),'total_mass_kg':float(b.body_mass.sum()),
            'physics_dt_s':b.opt.timestep,'passive_damping':b.dof_damping.tolist(),'armature':b.dof_armature.tolist()}


def audit_probe(path,cfg,plan,baseline_path):
    rows=list(csv.DictReader(path.open()));baseline=list(csv.DictReader(baseline_path.open()))
    if len(rows)!=1232 or len(baseline)!=1232:raise ValueError('Incomplete law grid')
    array=lambda name:np.asarray([float(r[name]) for r in rows])
    slots=array('slot').astype(int);legs=slots<12
    pd=array('tau_ff')+array('kp')*(array('q_target')-array('q'))+array('kd')*(array('dq_target')-array('dq'))
    values=parameters(cfg,plan)
    effort=np.asarray(values['effort'])[slots[legs]];speed=np.asarray(values['velocity'])[slots[legs]]
    saturation=np.asarray(values['saturation'])[slots[legs]]
    state=SimpleNamespace(_joint_vel=torch.tensor(array('dq')[legs]),effort_limit=torch.tensor(effort),
        velocity_limit=torch.tensor(speed),_saturation_effort=torch.tensor(saturation),
        _vel_at_effort_lim=torch.tensor(speed*(1+effort/saturation)))
    expected=pd.copy();expected[legs]=reference_clip()(state,torch.tensor(pd[legs])).numpy()
    expected[~legs]=np.clip(pd[~legs],-20,20)
    actual=array('mujoco_force');ctrl=array('bridge_ctrl')
    # Wheel raw PD as well as compiled force must match the baseline grid.
    wheel_ctrl=np.asarray([float(r['bridge_ctrl']) for r in baseline])[~legs]
    wheel_force=np.asarray([float(r['mujoco_force']) for r in baseline])[~legs]
    disabled=list(csv.DictReader(path.with_name(path.name+'.disabled.csv').open()))
    if len(disabled)!=240:raise ValueError('Incomplete disabled grid')
    checks={'leg_ctrl_vs_upstream_max_error_nm':float(np.max(abs(ctrl[legs]-expected[legs]))),
        'leg_force_vs_upstream_max_error_nm':float(np.max(abs(actual[legs]-expected[legs]))),
        'wheel_raw_pd_vs_baseline_max_error_nm':float(np.max(abs(ctrl[~legs]-wheel_ctrl))),
        'wheel_force_vs_baseline_max_error_nm':float(np.max(abs(actual[~legs]-wheel_force))),
        'disabled_max_abs_ctrl_nm':max(abs(float(r['ctrl'])) for r in disabled),
        'disabled_max_abs_force_nm':max(abs(float(r['force'])) for r in disabled)}
    write_json(path.with_suffix('.comparison.json'),[{**r,'requested_pd_nm':float(t),'upstream_expected_nm':float(e)} for r,t,e in zip(rows,pd,expected)])
    return {'passed':all(np.isfinite(v) and v<=1e-8 for v in checks.values()),'grid_samples':len(rows),
            'disabled_samples':len(disabled),'checks':checks,'physx_wheel_integration_parity':None}
