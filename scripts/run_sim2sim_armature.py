"""Managed paired armature-only factor, simulator DDS domain 1 / lo only."""
from __future__ import annotations
from dataclasses import asdict
import gc
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import torch
import mujoco
import locomotion_v2_protocol as protocol
import run_sim2sim_faults as services_module
from run_sim2sim_faults import BUILD, POLICY, warm_runtime
from run_sim2sim_physics import make_scene, trial
from sim2sim_actuator_factor import make_dc_scene, parameters, model_invariants, audit_probe
from sim2sim_physics_audit import REFERENCE, REFERENCE_SHA256
from sim2sim_armature_factor import make_armature_scene, armature_parameters, armature_invariants
from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256, utc_now

PLAN=ROOT/'configs/sim2sim_armature_plan_20261012.json'


def acceptable(row,directory):
    rejection=directory/'rejected_policy_tick.json'
    target_rejected=(rejection.exists() and read_json(rejection)['accepted'].get('fault')=='target_limit')
    # No desired-target limit waiver: a rejection remains incomplete and failed
    # as a locomotion trial. It is an expected observable diagnostic endpoint.
    return (row.get('measurement_valid',False) and row['publisher']['passed']
        and row.get('bridge_returncode')==0 and not row.get('safety',{}).get('unsafe_flags')
        and (not row.get('transport_fault') or target_rejected))


def main():
    managed_entrypoint()
    def cancelled(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    torch.set_num_threads(1)
    output=Path(os.environ['B2W_JOB_DIR'])/'sim2sim_armature';output.mkdir()
    sources=[
        'scripts/run_sim2sim_armature.py','scripts/sim2sim_armature_factor.py','scripts/sim2sim_actuator_factor.py','scripts/run_sim2sim_physics.py',
        'scripts/sim2sim_physics_audit.py','scripts/run_sim2sim_faults.py','scripts/run_sim2sim.py',
        'scripts/sdk2_watchdog_client.py','scripts/sdk2_policy_runtime.py','scripts/check_policy_contract.py',
        'scripts/evaluation_policy.py','scripts/mujoco_model.py','scripts/locomotion_v2_protocol.py',
        'scripts/locomotion57_protocol.py','scripts/core_locomotion_protocol.py','scripts/run_support.py',
        'scripts/job_manager.py','scripts/job_worker.py','scripts/manage_runs.py',
        'sim2sim/CMakeLists.txt','sim2sim/bridge.cpp','sim2sim/actuator_probe.cpp',
        'sim2sim/dc_bridge.cpp','sim2sim/dc_bridge.hpp','sim2sim/dc_actuator_probe.cpp',
        'sim2sim/watchdog.cpp','sim2sim/sdk2_io.hpp','sim2sim/unix_rpc.hpp',
        'configs/sim2sim_armature_plan_20261012.json','configs/sim2sim_fault_plan_20261012.json',
        'tests/test_sim2sim_armature.py','tests/test_sim2sim_actuator.py','tests/test_sim2sim_physics.py','tests/test_sdk2_policy_runtime.py',
        'vendor/unitree_mujoco/simulate/src/unitree_sdk2_bridge.h']
    for name in sources:
        target=output/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    plan=read_json(output/'sources'/PLAN.relative_to(ROOT))
    if plan['hardware_enabled'] or plan['training_updates'] or plan['domain']!=1 or plan['interface']!='lo':
        raise ValueError('Simulator-only plan required')
    if plan['arm_order']!=['dc_baseline','armature_zero'] or plan['repeats']!=1:raise ValueError('Bounded pair required')
    cases=protocol.cases_for(plan['terrain'])
    if [c.name for c in cases]!=plan['case_order']:raise ValueError('Frozen case order changed')
    runtime=warm_runtime();cfg=runtime.cfg;resolved=parameters(cfg,plan)
    write_json(output/'declared_plan.json',{'plan':plan,'cases':[asdict(c) for c in cases],'leg_parameters':resolved,'armature_parameters':armature_parameters(cfg,plan)})
    reference=output/'references/actuator_pd.py';reference.parent.mkdir()
    if sha256(REFERENCE)!=REFERENCE_SHA256:raise ValueError('Pinned reference changed')
    shutil.copyfile(REFERENCE,reference)
    shutil.copyfile(ROOT/plan['physx_snapshot'],output/'references/resolved_physx.json')
    executables=['b2w_mujoco_dc_bridge','b2w_dc_actuator_probe','b2w_sdk2_watchdog']
    (output/'bin').mkdir()
    for name in executables:shutil.copy2(BUILD/name,output/'bin'/name)
    # Every native child executes frozen bytes, including the fresh baseline.
    services_module.BUILD=output/'bin'
    artifacts=[POLICY,POLICY.with_name('manifest.json'),ROOT/'policies/local/core_24650/model_24650.pt',
        ROOT/'policies/server/upstream_19999/export/policy.pt',ROOT/'vendor/manifest.json']+[BUILD/n for n in executables]
    manifest={'created_utc':utc_now(),'hardware_enabled':False,
        'executed_sha256':{n:sha256(ROOT/n) for n in sources},
        'artifact_sha256':{p.relative_to(ROOT).as_posix():sha256(p) for p in artifacts},
        'declared_plan_sha256':sha256(output/'declared_plan.json'),'reference_sha256':REFERENCE_SHA256,
        'physx_snapshot_sha256':plan['physx_snapshot_sha256'],'python':sys.version,
        'torch':torch.__version__,'mujoco':mujoco.__version__}
    write_json(output/'preflight_manifest.json',manifest)
    records=[];audit=None;error=None;gc_enabled=gc.isenabled()
    try:
        for pattern in ('test_sim2sim_armature.py','test_sim2sim_actuator.py','test_sim2sim_physics.py','test_sdk2_policy_runtime.py',
                        'test_mujoco_model.py','test_locomotion_v2.py','test_dashboard_jobs.py'):
            subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-q'],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'scripts/vendor_materials.py','verify'],cwd=ROOT,check=True)
        paths={}
        for arm,factory,exe in [('dc_baseline',make_dc_scene,'b2w_dc_actuator_probe'),('armature_zero',make_armature_scene,'b2w_dc_actuator_probe')]:
            directory=output/'law'/arm;directory.mkdir(parents=True)
            paths[arm]=factory(directory,cfg,plan)
            subprocess.run([str(output/'bin'/exe),str(paths[arm]),str(directory/'probe.csv')],cwd=ROOT,check=True,
                stdout=(directory/'stdout.log').open('w'),stderr=(directory/'stderr.log').open('w'))
        audit={'model':armature_invariants(paths['dc_baseline'],paths['armature_zero'],cfg,plan),
            'law':{arm:audit_probe(output/'law'/arm/'probe.csv',cfg,plan,output/'law/dc_baseline/probe.csv')
                   for arm in plan['arm_order']}}
        write_json(output/'armature_audit.json',audit)
        if not all(a['passed'] for a in audit['law'].values()):raise ValueError('Native law gate failed')
        gc.disable();watchdog_plan=output/'sources'/plan['watchdog_plan']
        for arm in plan['arm_order']:
            exe='b2w_mujoco_dc_bridge'
            factory=make_dc_scene if arm=='dc_baseline' else make_armature_scene
            for case in cases:
                print('START',arm,case.name,flush=True)
                directory=output/arm/case.name
                row=trial(directory,case,plan,watchdog_plan,cfg,bridge_executable=exe,scene_factory=factory)
                row['arm']=arm;row['diagnostic_execution_passed']=bool(acceptable(row,directory));records.append(row)
                write_json(directory/'result.json',row)
                write_json(output/'progress.json',{'completed':len(records),'total':10,'records':records})
                print('DONE',arm,case.name,row['outcome'],row['policy_ticks'],flush=True)
    except BaseException as failure:
        error=repr(failure);raise
    finally:
        if gc_enabled:gc.enable()
        result={'audit':audit,'records':records,'error':error,
            'diagnostic_execution_passed':bool(not error and len(records)==10 and all(r['diagnostic_execution_passed'] for r in records)),
            'all_motion_programs_complete':bool(len(records)==10 and all(r.get('measurement_complete') for r in records)),
            'successes_by_arm':{a:sum(r['arm']==a and r['outcome']=='success' for r in records) for a in plan['arm_order']},
            'simulation_qualified':False,'hardware_enabled':False,'training_updates':0}
        write_json(output/'summary.json',result)
        manifest['raw_sha256']={p.relative_to(output).as_posix():sha256(p) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json'}
        write_json(output/'manifest.json',manifest)
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','audit')},indent=2))
    if not result['diagnostic_execution_passed']:raise SystemExit(2)


if __name__=='__main__':main()
