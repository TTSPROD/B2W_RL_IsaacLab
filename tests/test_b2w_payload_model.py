import importlib.util
import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_b2w_payload_urdf.py"
SPEC_PATH = ROOT / "configs" / "payloads" / "b2w_sensor_payload_v1.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_b2w_payload_urdf", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PayloadModelTests(unittest.TestCase):
    def test_payload_spec_mass_and_forward_mapping(self):
        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        self.assertEqual(spec["schema"], "b2w_payload_v1")
        self.assertTrue(math.isclose(sum(item["mass_kg"] for item in spec["components"]), 11.0))
        components = {item["name"]: item for item in spec["components"]}
        thermal_x = components["payload_thermal_imager"]["shapes"][0]["center_xyz_base_m"][0]
        box_x = components["payload_electronics_box"]["shapes"][0]["center_xyz_base_m"][0]
        self.assertGreater(thermal_x, 0.0)
        self.assertLess(box_x, 0.0)

    def test_generated_payload_urdf_keeps_only_fixed_added_joints(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "b2w_payload.urdf"
            manifest = module.build(SPEC_PATH, output)
            root = ET.parse(output).getroot()
            payload_links = [link for link in root.findall("link") if link.attrib["name"].startswith("payload_")]
            payload_joints = [
                joint for joint in root.findall("joint") if joint.attrib["name"].startswith("joint_payload_")
            ]
            self.assertEqual(len(payload_links), 3)
            self.assertEqual(len(payload_joints), 3)
            self.assertTrue(all(joint.attrib["type"] == "fixed" for joint in payload_joints))
            self.assertEqual(manifest["movable_joint_count_added"], 0)
            self.assertTrue(math.isclose(manifest["payload"]["mass_kg"], 11.0))
            self.assertLess(manifest["payload"]["com_xyz_base_m"][0], 0.0)
            self.assertTrue(all(value > 0.0 for value in manifest["payload"]["inertia_diagonal_kg_m2"]))


if __name__ == "__main__":
    unittest.main()
