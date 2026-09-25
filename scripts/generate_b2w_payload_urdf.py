"""Generate a project-local B2W URDF with fixed payload proxy geometry.

The vendor URDF remains immutable.  Payload links are fixed to ``base_link`` and
are intended to be merged by the existing Isaac Lab URDF converter.  This keeps
the 16-DoF action contract unchanged while adding the measured mass, COM,
inertia, visual envelope, and collision envelope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URDF = (
    ROOT
    / "vendor"
    / "robot_lab"
    / "source"
    / "robot_lab"
    / "data"
    / "Robots"
    / "unitree"
    / "b2w_description"
    / "urdf"
    / "b2w_description.urdf"
)
MESH_DIR = SOURCE_URDF.parent.parent / "meshes"
DEFAULT_SPEC = ROOT / "configs" / "payloads" / "b2w_sensor_payload_v1.json"
DEFAULT_OUTPUT = ROOT / ".cache" / "assets" / "b2w_payload_v1" / "b2w_payload_v1.urdf"


def _fmt(values: list[float] | tuple[float, ...]) -> str:
    return " ".join(f"{value:.9g}" for value in values)


def _box_inertia(mass: float, size: list[float]) -> tuple[float, float, float]:
    x, y, z = size
    return (
        mass * (y * y + z * z) / 12.0,
        mass * (x * x + z * z) / 12.0,
        mass * (x * x + y * y) / 12.0,
    )


def _component_properties(component: dict) -> tuple[list[float], list[list[float]]]:
    mass = float(component["mass_kg"])
    shapes = component["shapes"]
    fraction_sum = sum(float(shape["mass_fraction"]) for shape in shapes)
    if not math.isclose(fraction_sum, 1.0, abs_tol=1e-9):
        raise ValueError(f"Mass fractions for {component['name']} sum to {fraction_sum}")

    com = [
        sum(float(shape["mass_fraction"]) * float(shape["center_xyz_base_m"][axis]) for shape in shapes)
        for axis in range(3)
    ]
    inertia = [0.0, 0.0, 0.0]
    for shape in shapes:
        shape_mass = mass * float(shape["mass_fraction"])
        if shape["type"] != "box":
            raise ValueError(f"Unsupported physics proxy {shape['type']!r}")
        intrinsic = _box_inertia(shape_mass, [float(value) for value in shape["size_xyz_m"]])
        offset = [float(shape["center_xyz_base_m"][axis]) - com[axis] for axis in range(3)]
        inertia[0] += intrinsic[0] + shape_mass * (offset[1] ** 2 + offset[2] ** 2)
        inertia[1] += intrinsic[1] + shape_mass * (offset[0] ** 2 + offset[2] ** 2)
        inertia[2] += intrinsic[2] + shape_mass * (offset[0] ** 2 + offset[1] ** 2)
    return com, [inertia, [0.0, 0.0, 0.0]]


def _add_shape(parent: ET.Element, shape: dict, component_com: list[float], color: list[float], visual: bool) -> None:
    element = ET.SubElement(parent, "visual" if visual else "collision", {"name": shape["name"]})
    center = [float(shape["center_xyz_base_m"][axis]) - component_com[axis] for axis in range(3)]
    ET.SubElement(element, "origin", {"xyz": _fmt(center), "rpy": "0 0 0"})
    geometry = ET.SubElement(element, "geometry")
    ET.SubElement(geometry, "box", {"size": _fmt([float(value) for value in shape["size_xyz_m"]])})
    if visual:
        material = ET.SubElement(element, "material", {"name": f"{shape['name']}_material"})
        ET.SubElement(material, "color", {"rgba": _fmt(color)})


def _add_component(robot: ET.Element, component: dict) -> dict:
    name = component["name"]
    mass = float(component["mass_kg"])
    com, inertia_parts = _component_properties(component)
    inertia = inertia_parts[0]

    link = ET.SubElement(robot, "link", {"name": name})
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", {"xyz": "0 0 0", "rpy": "0 0 0"})
    ET.SubElement(inertial, "mass", {"value": f"{mass:.9g}"})
    ET.SubElement(
        inertial,
        "inertia",
        {
            "ixx": f"{inertia[0]:.9g}",
            "ixy": "0",
            "ixz": "0",
            "iyy": f"{inertia[1]:.9g}",
            "iyz": "0",
            "izz": f"{inertia[2]:.9g}",
        },
    )
    color = [float(value) for value in component["color_rgba"]]
    for shape in component["shapes"]:
        _add_shape(link, shape, com, color, visual=True)
        _add_shape(link, shape, com, color, visual=False)

    joint = ET.SubElement(robot, "joint", {"name": f"joint_{name}", "type": "fixed"})
    ET.SubElement(joint, "origin", {"xyz": _fmt(com), "rpy": "0 0 0"})
    ET.SubElement(joint, "parent", {"link": "base_link"})
    ET.SubElement(joint, "child", {"link": name})

    return {"name": name, "mass_kg": mass, "com_xyz_base_m": com, "inertia_diagonal_kg_m2": inertia}


def _payload_properties(components: list[dict]) -> dict:
    total_mass = sum(component["mass_kg"] for component in components)
    com = [
        sum(component["mass_kg"] * component["com_xyz_base_m"][axis] for component in components) / total_mass
        for axis in range(3)
    ]
    diagonal = [0.0, 0.0, 0.0]
    products = [0.0, 0.0, 0.0]
    for component in components:
        mass = component["mass_kg"]
        dx, dy, dz = [component["com_xyz_base_m"][axis] - com[axis] for axis in range(3)]
        own = component["inertia_diagonal_kg_m2"]
        diagonal[0] += own[0] + mass * (dy * dy + dz * dz)
        diagonal[1] += own[1] + mass * (dx * dx + dz * dz)
        diagonal[2] += own[2] + mass * (dx * dx + dy * dy)
        products[0] -= mass * dx * dy
        products[1] -= mass * dx * dz
        products[2] -= mass * dy * dz
    return {
        "mass_kg": total_mass,
        "com_xyz_base_m": com,
        "inertia_diagonal_kg_m2": diagonal,
        "inertia_products_ixy_ixz_iyz_kg_m2": products,
    }


def build(spec_path: Path, output_path: Path) -> dict:
    spec_bytes = spec_path.read_bytes()
    spec = json.loads(spec_bytes)
    if spec.get("schema") != "b2w_payload_v1":
        raise ValueError("Unexpected payload schema")
    if not SOURCE_URDF.is_file():
        raise FileNotFoundError(SOURCE_URDF)

    tree = ET.parse(SOURCE_URDF)
    robot = tree.getroot()
    if robot.tag != "robot" or robot.attrib.get("name") != "b2w_description":
        raise ValueError("Unexpected source B2W URDF")
    for mesh in robot.findall(".//mesh"):
        filename = mesh.attrib.get("filename", "")
        prefix = "package://b2w_description/meshes/"
        if filename.startswith(prefix):
            mesh.attrib["filename"] = (MESH_DIR / filename[len(prefix) :]).resolve().as_posix()

    component_results = [_add_component(robot, component) for component in spec["components"]]
    payload = _payload_properties(component_results)
    expected_mass = float(spec["training_randomization"]["nominal_payload_mass_kg"])
    if not math.isclose(payload["mass_kg"], expected_mass, abs_tol=1e-9):
        raise ValueError(f"Payload mass {payload['mass_kg']} differs from nominal {expected_mass}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    manifest = {
        "schema": "b2w_payload_generated_v1",
        "spec": str(spec_path.resolve()),
        "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "source_urdf": str(SOURCE_URDF.resolve()),
        "source_urdf_sha256": hashlib.sha256(SOURCE_URDF.read_bytes()).hexdigest(),
        "generated_urdf": str(output_path.resolve()),
        "generated_urdf_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "source_step": spec["source_step"],
        "components": component_results,
        "payload": payload,
        "movable_joint_count_added": 0,
        "fixed_joint_count_added": len(component_results),
    }
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build(args.spec.resolve(), args.output.resolve())
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
