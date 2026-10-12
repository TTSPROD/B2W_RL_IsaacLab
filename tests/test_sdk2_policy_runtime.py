"""Real actor, native field/CRC parity, raw history, and latched IO faults."""
import math
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/".runtime/sim2sim-build"))
from sdk2_policy_runtime import PolicyRuntime, lowcmd_motors, disabled_motors
from check_policy_contract import fixtures


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.runtime=PolicyRuntime(ROOT/"policies/local/core_24650/export/policy.pt")
        self.neutral=fixtures(self.runtime.cfg)["neutral_reset"]

    def test_leg_wheel_and_unused_fields_in_actual_sdk_message(self):
        import b2w_sdk2_native as native
        targets=[i/8 for i in range(16)]
        result=native.echo(lowcmd_motors(targets,self.runtime.cfg))
        for i,m in enumerate(result["motors"]):
            if i<12:self.assertEqual(m,[1,targets[i],0,160,5,0])
            elif i<16:self.assertEqual(m,[1,0,targets[i],0,1,0])
            else:self.assertEqual(m,disabled_motors()[i])
        self.assertTrue(result["crc_valid"])
        with self.assertRaises(ValueError):native.Transport(0,"lo")
        with self.assertRaises(ValueError):native.Transport(1,"eth0")

    def test_stop_retains_raw_history_and_reset_clears_it(self):
        runtime=self.runtime
        runtime.policy=lambda obs:torch.full((1,16),200.0)
        first=runtime.step(self.neutral,[.2,0,0])
        second=runtime.step(self.neutral,[0,0,0])
        self.assertEqual(first["targets"][12:],[100]*4)
        self.assertEqual(runtime.previous_action.tolist(),[200]*16)
        self.assertEqual(second["observation"][41:],[100]*16)
        runtime.reset()
        self.assertEqual(runtime.previous_action.tolist(),[0]*16)

    def test_invalid_state_command_and_actor_latch_until_explicit_reset(self):
        cases=[(dict(self.neutral,omega_body=[math.nan,0,0]),[0,0,0]),
               (dict(self.neutral,crc_valid=False),[0,0,0]),
               (dict(self.neutral,quat_wxyz=[0,0,0,0]),[0,0,0]),
               (dict(self.neutral,joint_pos=[math.inf]*16),[0,0,0]),
               (dict(self.neutral,age_s=.1),[0,0,0]),
               (self.neutral,[math.nan,0,0])]
        for state,command in cases:
            self.runtime.reset()
            with self.assertRaises(ValueError):self.runtime.step(state,command)
            self.assertIsNotNone(self.runtime.fault)
            with self.assertRaises(ValueError):self.runtime.step(self.neutral,[0,0,0])
        self.runtime.reset()
        self.runtime.policy=lambda obs:torch.full((1,16),math.inf)
        with self.assertRaises(ValueError):self.runtime.step(self.neutral,[0,0,0])

    def test_transport_budgets_latch_independently(self):
        for ages,reason in [((.05,0,0),"stale_state"),((0,.11,0),"stale_command"),
                            ((0,0,.07),"expired_target"),((math.nan,0,0),"stale_state")]:
            self.runtime.reset()
            self.assertFalse(self.runtime.guard(*ages))
            self.assertEqual(self.runtime.fault,reason)
            self.assertFalse(self.runtime.guard(0,0,0))
            self.runtime.reset();self.assertTrue(self.runtime.guard(0,0,0))

    def test_ubuntu_supervisor_uses_project_python(self):
        from run_support import local_command
        if sys.platform=="win32":self.skipTest("Ubuntu test")
        self.assertEqual(local_command("scripts/run_sim2sim.py"),
                         [str(ROOT/".venv/bin/python"),"scripts/run_sim2sim.py"])

    def test_native_service_startup_failure_keeps_diagnostic_evidence(self):
        from run_sim2sim_faults import nominal, Services
        with tempfile.TemporaryDirectory() as folder, \
                patch("run_sim2sim_faults.warm_runtime", return_value=self.runtime), \
                patch.object(Services, "service", side_effect=RuntimeError("watchdog exited")):
            result=nominal(Path(folder), {"nominal_duration_s":20}, Path(folder)/"plan.json")
            self.assertEqual(result["status"], "failed")
            self.assertIn("watchdog exited", result["fault"])
            self.assertEqual(result["policy_ticks"], 0)
            self.assertTrue((Path(folder)/"nominal/summary.json").exists())

    @unittest.skipIf(sys.platform=="win32","POSIX process groups")
    def test_stop_reaps_child_in_owned_process_group(self):
        from run_support import stop_process_tree
        with tempfile.TemporaryDirectory() as folder:
            pidfile=Path(folder)/"pid"
            code=("import subprocess,sys,time,signal,pathlib;"
                  "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
                  "signal.signal(signal.SIGTERM,lambda *_:(p.wait(timeout=5),sys.exit(0)));"
                  f"pathlib.Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(120)")
            process=subprocess.Popen([sys.executable,"-c",code],start_new_session=True)
            try:
                deadline=time.monotonic()+5
                while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue(pidfile.exists())
                child=int(pidfile.read_text())
                stop_process_tree(process)
                self.assertEqual(process.returncode,0)
                self.assertFalse(Path(f"/proc/{child}").exists())
            finally:
                stop_process_tree(process)


if __name__=="__main__":unittest.main()
