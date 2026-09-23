"""Inventory pinned B2W source model differences; not simulator equivalence."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / 'vendor/robot_lab/source/robot_lab/data/Robots/unitree/b2w_description/urdf/b2w_description.urdf'
OFFICIAL = ROOT / 'vendor/unitree_ros/robots/b2w_description/urdf/b2w_description.urdf'
MUJOCO = ROOT / 'vendor/unitree_mujoco/unitree_robots/b2w/b2w.xml'


def inventory(path):
    tree = ET.parse(path).getroot()
    is_urdf = path.suffix == '.urdf'
    bodies = {}
    for body in tree.findall('link') if is_urdf else tree.findall('.//body'):
        inertial = body.find('inertial')
        if inertial is None:
            continue
        if is_urdf:
            mass = float(inertial.find('mass').get('value'))
            inertia = {'origin': dict(inertial.find('origin').attrib),
                       'tensor': dict(inertial.find('inertia').attrib)}
        else:
            mass = float(inertial.get('mass'))
            inertia = dict(inertial.attrib)
        collisions = [ET.tostring(item, encoding='unicode').strip() for item in
                      (body.findall('collision') if is_urdf else body.findall("geom[@class='collision']"))]
        bodies[body.get('name')] = {'mass_kg': mass, 'inertial_source_frame': inertia, 'collision_source': collisions}
    joints = {}
    for joint in tree.findall('joint') if is_urdf else tree.findall('.//body/joint'):
        if joint.get('type') in ('fixed', 'free'):
            continue
        joints[joint.get('name')] = {'attributes': dict(joint.attrib),
                                   'children': {child.tag: dict(child.attrib) for child in joint}}
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'total_source_mass_kg': sum(body['mass_kg'] for body in bodies.values()),
            'bodies': bodies, 'movable_joints': joints,
            'defaults': [ET.tostring(item, encoding='unicode').strip() for item in tree.findall('default')],
            'actuators': [dict(item.attrib) for item in tree.findall('./actuator/*')]}


def inertia_comparison():
    import numpy as np
    from scipy.spatial.transform import Rotation
    tree = ET.parse(TRAIN).getroot()
    links = {link.get('name'): link for link in tree.findall('link')}
    parent = {joint.find('child').get('link'): joint for joint in tree.findall('joint')}
    def vector(text, default='0 0 0'):
        return np.array([float(x) for x in (text or default).split()])
    def fixed_transform(name):
        joint = parent.get(name)
        if joint is None or joint.get('type') != 'fixed':
            return name, np.eye(3), np.zeros(3)
        anchor, rotation, translation = fixed_transform(joint.find('parent').get('link'))
        origin = joint.find('origin')
        local_rotation = Rotation.from_euler('xyz', vector(origin.get('rpy'))).as_matrix()
        local_translation = vector(origin.get('xyz'))
        return anchor, rotation @ local_rotation, translation + rotation @ local_translation
    groups = {}
    for name, link in links.items():
        inertial = link.find('inertial')
        if inertial is None:
            continue
        anchor, rotation, translation = fixed_transform(name)
        origin = inertial.find('origin')
        mass = float(inertial.find('mass').get('value'))
        com = translation + rotation @ vector(origin.get('xyz'))
        rotation = rotation @ Rotation.from_euler('xyz', vector(origin.get('rpy'))).as_matrix()
        data = {key: float(value) for key, value in inertial.find('inertia').attrib.items()}
        tensor = np.array([[data['ixx'], data['ixy'], data['ixz']],
                           [data['ixy'], data['iyy'], data['iyz']],
                           [data['ixz'], data['iyz'], data['izz']]])
        groups.setdefault(anchor, []).append((name, mass, com, rotation @ tensor @ rotation.T))
    merged = {}
    for name, entries in groups.items():
        mass = sum(entry[1] for entry in entries)
        com = sum(entry[1] * entry[2] for entry in entries) / mass
        tensor = np.zeros((3, 3))
        for _, m, c, inertia in entries:
            offset = c - com
            tensor += inertia + m * (np.dot(offset, offset) * np.eye(3) - np.outer(offset, offset))
        if np.linalg.eigvalsh(tensor).min() < -1e-10:
            raise ValueError(f'Non-positive merged inertia: {name}')
        merged[name] = {'source_links': [entry[0] for entry in entries], 'mass_kg': mass,
                        'com_m': com.tolist(), 'inertia_body_frame_kg_m2': tensor.tolist()}
    source_mass = sum(float(link.find('inertial/mass').get('value')) for link in links.values() if link.find('inertial') is not None)
    assert abs(source_mass - sum(body['mass_kg'] for body in merged.values())) < 1e-9
    pairs = []
    for body in ET.parse(MUJOCO).getroot().findall('.//body'):
        source = body.find('inertial')
        if source is None:
            continue
        name = body.get('name')
        match = name.replace('_wheel_link', '_foot')
        if match not in merged:
            continue
        quaternion = vector(source.get('quat'), '1 0 0 0')
        rotation = Rotation.from_quat(quaternion[[1, 2, 3, 0]]).as_matrix()
        inertia = rotation @ np.diag(vector(source.get('diaginertia'))) @ rotation.T
        reference = merged[match]
        pairs.append({'urdf_body': match, 'mujoco_body': name, 'urdf': reference,
                      'mujoco': {'mass_kg': float(source.get('mass')), 'com_m': vector(source.get('pos')).tolist(),
                                  'inertia_body_frame_kg_m2': inertia.tolist()},
                      'mass_delta_kg': float(source.get('mass')) - reference['mass_kg'],
                      'com_delta_m': (vector(source.get('pos')) - np.array(reference['com_m'])).tolist(),
                      'max_abs_inertia_delta_kg_m2': float(np.abs(inertia - np.array(reference['inertia_body_frame_kg_m2'])).max())})
    assert len(pairs) == 17, f'Expected 17 matched bodies, got {len(pairs)}'
    return {'scope': 'URDF fixed joints merged with parallel-axis theorem; tensors expressed in each named body frame',
            'frame_caveat': 'Body frame correspondences are by source names (wheel_link->foot); kinematic/collision equivalence is not asserted.',
            'mass_conservation_checked': True, 'pairs': pairs}


def main():
    training, official, mujoco = map(inventory, (TRAIN, OFFICIAL, MUJOCO))
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'source inventory, no dynamics engine loaded',
              'training_model_reference': training['path'],
              'training_and_official_urdf_byte_identical': training['sha256'] == official['sha256'],
              'mujoco_minus_training_mass_kg': mujoco['total_source_mass_kg'] - training['total_source_mass_kg'],
              'training': training, 'official': official, 'mujoco': mujoco,
              'merged_inertial_comparison': inertia_comparison(),
              'limitations': ['Raw source inventory has unmerged links; use merged_inertial_comparison for named-body aggregates.',
                              'COM/inertia transformed to named body frames; full kinematic and mesh/contact equivalence remain to be validated.',
                              'XML defaults and geometries inventoried, not compiled by MuJoCo.',
                              'Hardware torque-speed curves, payload and wheel contact properties are not measured.']}
    path = ROOT / 'logs/qualification/robot_model_comparison.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('training_and_official_urdf_byte_identical', 'mujoco_minus_training_mass_kg')}, indent=2))
    print(path)


if __name__ == '__main__':
    main()
