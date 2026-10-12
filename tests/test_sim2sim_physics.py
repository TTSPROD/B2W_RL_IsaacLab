"""Pinned source checks and reset/protocol invariants for the native physics audit."""
import ast
from pathlib import Path
import sys
import tempfile
import unittest

import mujoco
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from run_support import read_json
from sim2sim_physics_audit import actuator_config, reference_clip, model_audit, REFERENCE
from run_sim2sim_physics import make_scene
from locomotion57_protocol import reset_sample
import locomotion_v2_protocol as protocol


class PhysicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=read_json(ROOT/"policies/local/core_24650/export/manifest.json")["contract"]
        cls.plan=read_json(ROOT/"configs/sim2sim_physics_plan_20261012.json")

    def test_declared_order_contains_complete_v2_commands_and_zero_windows(self):
        cases=protocol.cases_for(self.plan["terrain"])
        self.assertEqual([c.name for c in cases],self.plan["case_order"])
        self.assertEqual([c.steps for c in cases],[600,2500,2500,2500,1300])
        for case in cases:
            command,_=case.schedule()
            self.assertTrue(np.all(command[-600:]==0))

    def test_reset_matches_shared_seed_by_joint_names(self):
        with tempfile.TemporaryDirectory() as folder:
            path=make_scene(Path(folder),self.cfg,self.plan)
            model=mujoco.MjModel.from_xml_path(str(path));data=mujoco.MjData(model)
            mujoco.mj_resetDataKeyframe(model,data,0)
            sample=reset_sample(self.plan["reset_seed"])
            np.testing.assert_allclose(data.qpos[:2],sample["xy"])
            for i,name in enumerate(self.cfg["joint_names"]):
                joint=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,name.replace("_foot_joint","_wheel_joint"))
                expected=self.cfg["default_dof_pos"][i]+(sample["qdelta"][i] if i<12 else 0)
                self.assertAlmostEqual(data.qpos[model.jnt_qposadr[joint]],expected)
                self.assertAlmostEqual(data.qvel[model.jnt_dofadr[joint]],sample["dq"][i])

    def test_source_config_keeps_distinct_leg_and_wheel_classes(self):
        cfg=actuator_config()
        self.assertEqual(cfg["calf"]["saturation_effort"],320)
        self.assertEqual(cfg["hip"]["velocity_limit"],23)
        self.assertEqual(cfg["wheel"]["class"],"ImplicitActuatorCfg")
        self.assertEqual(cfg["wheel"]["damping"],1)

    def test_asset_audit_exposes_passive_dynamics_and_mass_difference(self):
        audit=model_audit(self.cfg)
        self.assertFalse(audit["physx_runtime_inspected"])
        self.assertGreater(audit["mujoco_total_mass_kg"],audit["urdf_total_mass_kg"])
        self.assertEqual(audit["joints"][2]["mujoco_ctrl_range_nm"],[-300,300])
        self.assertEqual(audit["joints"][0]["mujoco_damping_nm_s_rad"],1)

    @unittest.skipUnless(REFERENCE.exists(),"Cached pinned Isaac source required")
    def test_upstream_motor_brakes_beyond_no_load_speed_and_keeps_all_quadrants(self):
        from types import SimpleNamespace
        state=SimpleNamespace(_joint_vel=torch.tensor([0.,10.,20.,30.,-10.,-30.]),
            velocity_limit=torch.full((6,),20.),effort_limit=torch.full((6,),200.),
            _saturation_effort=torch.full((6,),200.),_vel_at_effort_lim=torch.full((6,),40.))
        actual=reference_clip()(state,torch.tensor([300.,300.,300.,300.,-300.,-300.]))
        torch.testing.assert_close(actual,torch.tensor([200.,100.,0.,-100.,-100.,100.]))

    def test_managed_recipe_is_allowlisted(self):
        import job_manager
        self.assertEqual(job_manager.recipe({"kind":"sim2sim_physics"}),
            ("scripts/run_sim2sim_physics.py",[]))

    def test_rejected_policy_tick_retains_exact_action_and_state(self):
        from sdk2_watchdog_client import policy_tick, RejectedPolicyTick
        from types import SimpleNamespace
        state={"fault":"","count":17}
        class Client:
            def command(self,c):pass
            def state(self):return state
            def begin(self,s):return {"command_ns":__import__("time").monotonic_ns()}
            def target(self,m,require_ok=True):return {"ok":False,"error":"latched","fault":"target_limit"}
        runtime=SimpleNamespace(step=lambda *a:{"motors":[[1,0,51,0,1,0]],"targets":[51],"raw_action":[10.2]})
        with self.assertRaises(RejectedPolicyTick) as error:policy_tick(Client(),runtime,[0,0,0])
        self.assertIs(error.exception.detail["state"],state)
        self.assertEqual(error.exception.detail["targets"],[51])
        self.assertEqual(error.exception.detail["raw_action"],[10.2])


if __name__=="__main__":unittest.main()
