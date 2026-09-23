"""CPU tests for bounded event configuration and applied-property verification."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

try:
    import torch
except ImportError:
    torch = None

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("physical_evaluation", ROOT / "scripts/physical_evaluation.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def fake_api():
    package, envs, managers = (ModuleType(name) for name in ("isaaclab", "isaaclab.envs", "isaaclab.managers"))
    envs.mdp = NS(**{name: object() for name in (
        "randomize_rigid_body_material", "randomize_rigid_body_mass", "randomize_actuator_gains",
    )})
    managers.EventTermCfg = lambda **kwargs: NS(**kwargs)
    managers.SceneEntityCfg = lambda name: NS(name=name)
    return {"isaaclab": package, "isaaclab.envs": envs, "isaaclab.managers": managers}


def fixture():
    generator = torch.Generator().manual_seed(20260920)
    n, bodies, joints = 16, 3, 4
    rand = lambda shape: torch.rand(shape, generator=generator, dtype=torch.float64)
    static = .6 + .4 * rand((n, 5))
    dynamic = torch.minimum(.5 + .3 * rand((n, 5)), static)
    material = torch.stack((static, dynamic, torch.zeros_like(static)), -1)
    default_mass = torch.tensor([20., 3., 1.], dtype=torch.float64).repeat(n, 1)
    scale = .9 + .2 * rand((n, bodies))
    mass = default_mass * scale
    default_inertia = torch.eye(3, dtype=torch.float64).flatten().repeat(n, bodies, 1)
    inertia = default_inertia * scale[..., None]
    default_kp = torch.tensor([20., 20., 0., 0.], dtype=torch.float64).repeat(n, 1)
    default_kd = torch.tensor([.5, .5, 1., 1.], dtype=torch.float64).repeat(n, 1)
    kp = default_kp * (.9 + .2 * rand((n, joints)))
    kd = default_kd * (.9 + .2 * rand((n, joints)))
    robot = NS(
        root_physx_view=NS(get_material_properties=lambda: material, get_masses=lambda: mass, get_inertias=lambda: inertia),
        data=NS(default_mass=default_mass, default_inertia=default_inertia,
                default_joint_stiffness=default_kp, default_joint_damping=default_kd),
        actuators={"legs": NS(joint_indices=torch.tensor([0, 1]), stiffness=kp[:, :2], damping=kd[:, :2]),
                   "wheels": NS(joint_indices=torch.tensor([2, 3]), stiffness=kp[:, 2:], damping=kd[:, 2:])},
        body_names=["base", "leg", "wheel"], joint_names=["a", "b", "c", "d"],
    )
    cfg = NS(events=NS(), seed=20260920)
    with patch.dict(sys.modules, fake_api()):
        m.configure_physical_evaluation(cfg, "bounded_v1")
    return NS(cfg=cfg, scene={"robot": robot}), NS(material=material, mass=mass, inertia=inertia, kp=kp, kd=kd)


class PhysicalEvaluationTests(unittest.TestCase):
    def test_nominal_is_noop_and_invalid_profile_rejected(self):
        cfg = NS(events=NS(existing=object()))
        before = vars(cfg.events).copy()
        self.assertFalse(m.configure_physical_evaluation(cfg, "nominal")["randomized"])
        self.assertEqual(vars(cfg.events), before)
        with self.assertRaises(ValueError):
            m.configure_physical_evaluation(cfg, "unknown")

    def test_active_training_event_rejected(self):
        cfg = NS(events=NS(push=NS(mode="interval")))
        with self.assertRaisesRegex(ValueError, "_nominal_cfg"):
            m.configure_physical_evaluation(cfg, "bounded_v1")

    def test_exact_startup_profile_and_pinned_api_keywords(self):
        cfg = NS(events=NS(reset=None))
        with patch.dict(sys.modules, fake_api()):
            specification = m.configure_physical_evaluation(cfg, "bounded_v1")
        self.assertEqual(len([v for v in vars(cfg.events).values() if v is not None]), 3)
        material = cfg.events.physical_eval_material
        self.assertTrue(material.params["make_consistent"])
        self.assertEqual(material.params["static_friction_range"], (.6, 1.))
        self.assertEqual(material.params["dynamic_friction_range"], (.5, .8))
        self.assertTrue(cfg.events.physical_eval_mass.params["recompute_inertia"])
        self.assertEqual(specification["event_mode"], "startup")
        # Inspect signatures from the pinned source without importing Kit.
        source = ROOT / ".runtime/IsaacLab/source/isaaclab/isaaclab/envs/mdp/events.py"
        if source.exists():
            classes = {node.name: node for node in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(node, ast.ClassDef)}
            for event, name in zip(m._EVENT_NAMES, ("randomize_rigid_body_material", "randomize_rigid_body_mass", "randomize_actuator_gains")):
                term = getattr(cfg.events, event)
                self.assertEqual(term.mode, "startup")
                method = next(node for node in classes[name].body if isinstance(node, ast.FunctionDef) and node.name == "__call__")
                keywords = {arg.arg for arg in method.args.args}
                self.assertLessEqual(set(term.params), keywords)

    @unittest.skipUnless(torch is not None, "requires project torch runtime")
    def test_deterministic_readback_real_values_and_zero_wheel_kp(self):
        base, raw = fixture()
        first = m.physical_evidence(base)
        other, _ = fixture()
        self.assertEqual(first, m.physical_evidence(other))
        self.assertTrue(first["variation_applied_verified"])
        self.assertEqual(first["environment_seed"], 20260920)
        self.assertEqual(first["default_properties_env0"]["joint_kp"], [20., 20., 0., 0.])
        self.assertEqual(first["first_environment_samples"][0]["body_inertia_kg_m2_flat9"], raw.inertia[0].tolist())
        self.assertEqual(len(first["per_environment"]), 16)
        self.assertEqual(len(first["first_environment_samples"]), 8)
        self.assertEqual(first["first_environment_samples"][0]["joint_kp_scale"][2:], [None, None])
        self.assertEqual(first["first_environment_samples"][0]["materials_static_dynamic_restitution"], raw.material[0].tolist())
        self.assertEqual(first["properties_sha256"], m.physical_evidence(base)["properties_sha256"])

    @unittest.skipUnless(torch is not None, "requires project torch runtime")
    def test_missing_gain_variation_and_mass_inertia_mismatch_rejected(self):
        base, raw = fixture()
        raw.kd[:] = base.scene["robot"].data.default_joint_damping
        with self.assertRaisesRegex(RuntimeError, "Kd scale variation"):
            m.physical_evidence(base)
        base, raw = fixture()
        raw.inertia *= 1.03
        with self.assertRaisesRegex(RuntimeError, "Inertia"):
            m.physical_evidence(base)

    @unittest.skipUnless(torch is not None, "requires project torch runtime")
    def test_nonfinite_and_inconsistent_material_rejected(self):
        base, raw = fixture()
        raw.mass[0, 0] = float("nan")
        with self.assertRaisesRegex(RuntimeError, "non-finite"):
            m.physical_evidence(base)
        base, raw = fixture()
        raw.material[0, 0, :2] = torch.tensor([.6, .8])
        with self.assertRaisesRegex(RuntimeError, "Dynamic friction"):
            m.physical_evidence(base)


if __name__ == "__main__":
    unittest.main()
