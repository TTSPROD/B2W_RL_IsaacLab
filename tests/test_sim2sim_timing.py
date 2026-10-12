"""GC scope, timing-only policy change and role topology invariants."""
import gc,sys,importlib.util
from pathlib import Path
import unittest
import numpy as np,torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from sim2sim_timing import bounded_gc,physical_core_roles
from sdk2_policy_runtime import PolicyRuntime
from check_policy_contract import fixtures


class TimingTests(unittest.TestCase):
    def test_gc_restored_on_success_exception_and_nested_scope(self):
        before=gc.isenabled()
        try:
            gc.enable()
            with self.assertRaises(RuntimeError):
                with bounded_gc():
                    self.assertFalse(gc.isenabled());raise RuntimeError('cancelled')
            self.assertTrue(gc.isenabled())
            gc.disable()
            with bounded_gc():self.assertFalse(gc.isenabled())
            self.assertFalse(gc.isenabled())
        finally:
            if before:gc.enable()
            else:gc.disable()

    def test_runtime_instrumentation_matches_previous_raw_history_and_outputs(self):
        torch.set_num_threads(1)
        old_path=ROOT/'logs/dashboard/jobs/040549c8e4174c8288112a8d2eeea858/sim2sim_pd_guard/sources/scripts/sdk2_policy_runtime.py'
        spec=importlib.util.spec_from_file_location('frozen_actor_runtime',old_path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        legacy=old.PolicyRuntime(ROOT/'policies/local/core_24650/export/policy.pt')
        current=PolicyRuntime(ROOT/'policies/local/core_24650/export/policy.pt');current.timing_enabled=True
        rng=np.random.default_rng(73001);state=fixtures(current.cfg)['neutral_reset']
        for i in range(256):
            q=rng.normal(size=4);q/=np.linalg.norm(q)
            sample=dict(state,quat_wxyz=q.tolist(),omega_body=rng.normal(size=3).tolist(),
                        joint_pos=rng.normal(size=16).tolist(),joint_vel=rng.normal(size=16).tolist())
            command=rng.uniform(-1,1,size=3).tolist()
            a=legacy.step(sample,command);b=current.step(sample,command)
            for name in ('observation','raw_action','targets','motors'):self.assertEqual(a[name],b[name])
            self.assertEqual(legacy.previous_action.tolist(),current.previous_action.tolist())
            self.assertEqual(set(b['runtime_timing']),{'observation','actor_forward','target_mapping','evidence_snapshot'})

    def test_role_placement_uses_distinct_physical_cores(self):
        roles=physical_core_roles();cpus=[roles[k][0] for k in ('actor','physics','watchdog')]
        self.assertEqual(len(set(cpus)),3)
        siblings=[]
        for cpu in cpus:
            siblings.append((Path(f'/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list')).read_text().strip())
        self.assertEqual(len(set(siblings)),3)
        self.assertTrue(set(cpus).issubset(roles['reserved_siblings']))


if __name__=='__main__':unittest.main()
