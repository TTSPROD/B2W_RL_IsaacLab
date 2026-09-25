"""Opt-in source collision/frame adaptation; no solver tuning or vendor writes."""
from __future__ import annotations
import json
import math
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from physics57_protocol import ROOT, case_boxes
from physics57_mujoco_model import adapt_model, Physics57Controller
from sim2sim_mujoco_b2w import DEFAULT_XML
from locomotion57_protocol import terrain_boxes

BASE = ROOT/'logs/contact57_20260925'
CONFIG = ROOT/'configs/contact57_diagnostics_20260925.json'
GEOMETRY = ROOT/'configs/contact57_geometry_20260925.json'
URDF = ROOT/'vendor/robot_lab/source/robot_lab/data/Robots/unitree/b2w_description/urdf/b2w_description.urdf'
VARIANTS = ('mechanics_control', 'frames', 'frames_masks', 'source_shapes')


def geometry():
    return json.loads(GEOMETRY.read_text(encoding='utf-8'))


def copy_frames(spec):
    for joint in ET.parse(URDF).getroot().findall('joint'):
        if joint.attrib['type'] == 'fixed':
            continue
        name = joint.attrib['name'].replace('_foot_joint','_wheel_joint')
        body = spec.body(joint.find('child').attrib['link'].replace('_foot','_wheel_link'))
        origin = joint.find('origin')
        body.pos = np.fromstring(origin.attrib.get('xyz','0 0 0'),sep=' ')
        rpy = np.fromstring(origin.attrib.get('rpy','0 0 0'),sep=' ')
        body.quat = Rotation.from_euler('xyz',rpy).as_quat()[[3,0,1,2]]
        spec.joint(name).axis = np.fromstring(joint.find('axis').attrib['xyz'],sep=' ')


def add_shapes(spec, source):
    for geom in spec.geoms:
        geom.contype = geom.conaffinity = 0
    for i,shape in enumerate(source['shapes']):
        body = spec.body(shape['body'].replace('_foot','_wheel_link'))
        common = dict(name=f'contact57_{i}', contype=1, conaffinity=2, condim=3,
            friction=[1.,.005,.0001], group=3, mass=0., density=0., rgba=[.3,.8,.5,.7])
        if shape['type'] == 'Mesh':
            name = f'contact57_hull_{i}'
            spec.add_mesh(name=name,uservert=np.asarray(shape['hull_vertices_body_m']).ravel(),
                maxhullvert=-1)
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH,meshname=name,**common)
        else:
            transform = np.asarray(shape['local_to_body'])
            scale = np.linalg.norm(transform[:3,:3],axis=0)
            rotation = transform[:3,:3]/scale
            np.testing.assert_allclose(rotation.T@rotation,np.eye(3),atol=1e-7)
            quat = Rotation.from_matrix(rotation).as_quat()[[3,0,1,2]]
            if shape['type'] == 'Cube':
                kind,size = mujoco.mjtGeom.mjGEOM_BOX,scale*shape['size']/2
            elif shape['type'] == 'Cylinder':
                assert shape['axis'] == 'Z' and abs(scale[0]-scale[1]) < 1e-8
                kind,size = mujoco.mjtGeom.mjGEOM_CYLINDER,[shape['radius']*scale[0],shape['height']*scale[2]/2,0]
            else:
                raise ValueError(shape['type'])
            body.add_geom(type=kind,size=size,pos=transform[:3,3],quat=quat,**common)


def make_model(variant, dt=.002, *, case=None, terrain=None):
    if variant not in VARIANTS:
        raise ValueError(variant)
    assert (case is None) != (terrain is None)
    source = geometry()
    spec = mujoco.MjSpec.from_file(str(DEFAULT_XML))
    spec.geom('floor').contype = spec.geom('floor').conaffinity = 0
    if variant != 'mechanics_control':
        copy_frames(spec)
    if variant == 'source_shapes':
        add_shapes(spec,source)
    elif variant == 'frames_masks':
        for geom in spec.geoms:
            if geom.contype or geom.conaffinity:
                geom.contype,geom.conaffinity = 1,2
    definition = terrain_boxes(terrain) if terrain is not None else {'boxes':case_boxes(case)}
    masks = variant in ('frames_masks','source_shapes')
    for i,box in enumerate(definition['boxes']):
        pitch = box['pitch']
        spec.worldbody.add_geom(name=f'contact57_terrain_{i}',type=mujoco.mjtGeom.mjGEOM_BOX,
            size=np.asarray(box['size'])/2,pos=box['pos'],quat=[math.cos(pitch/2),0,math.sin(pitch/2),0],
            friction=[1.,.005,.0001],condim=3,contype=2 if masks else 1,conaffinity=1)
    model = spec.compile()
    model.opt.timestep = dt
    adapt_model(model,'mechanics_implicit',source['compiled'])
    return model,definition


def controller(model):
    return Physics57Controller(model,'mechanics_implicit')
