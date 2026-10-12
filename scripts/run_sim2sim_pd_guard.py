"""Managed separate actual-state / PD-reference guard and full Flat replay."""
from __future__ import annotations
from dataclasses import asdict
import gc,json,os,shutil,signal,subprocess,sys
from pathlib import Path
import numpy as np
import torch,mujoco
import locomotion_v2_protocol as protocol
import run_sim2sim_faults as services_module
from run_sim2sim_faults import BUILD,POLICY,warm_runtime,fault_matrix,publishing_gate
from run_sim2sim_physics import trial
from sim2sim_actuator_factor import make_dc_scene,audit_probe
from sim2sim_pd_guard_checks import guard_checks
from sim2sim_physics_audit import REFERENCE,REFERENCE_SHA256
from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now,stop_process_tree

PLAN=ROOT/'configs/sim2sim_pd_guard_motion_20261012.json'


def main():
    managed_entrypoint()
    def cancelled(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    torch.set_num_threads(1)
    output=Path(os.environ['B2W_JOB_DIR'])/'sim2sim_pd_guard';output.mkdir()
    sources=[
        'scripts/run_sim2sim_pd_guard.py','scripts/sim2sim_pd_guard_checks.py','scripts/sim2sim_actuator_factor.py',
        'scripts/run_sim2sim_physics.py','scripts/sim2sim_physics_audit.py','scripts/run_sim2sim_faults.py',
        'scripts/run_sim2sim.py','scripts/sdk2_watchdog_client.py','scripts/sdk2_policy_runtime.py',
        'scripts/check_policy_contract.py','scripts/evaluation_policy.py','scripts/mujoco_model.py',
        'scripts/locomotion_v2_protocol.py','scripts/locomotion57_protocol.py','scripts/core_locomotion_protocol.py',
        'scripts/run_support.py','scripts/job_manager.py','scripts/job_worker.py','scripts/manage_runs.py',
        'sim2sim/CMakeLists.txt','sim2sim/bridge.cpp','sim2sim/dc_bridge.cpp','sim2sim/dc_bridge.hpp',
        'sim2sim/actuator_probe.cpp','sim2sim/dc_actuator_probe.cpp','sim2sim/watchdog.cpp','sim2sim/pd_guard.hpp',
        'sim2sim/pd_watchdog.cpp','sim2sim/fault_source.cpp','sim2sim/pd_fault_source.cpp',
        'sim2sim/sdk2_io.hpp','sim2sim/unix_rpc.hpp',
        'configs/sim2sim_pd_guard_motion_20261012.json','configs/sim2sim_pd_guard_plan_20261012.json',
        'tests/test_sim2sim_pd_guard.py','tests/test_sim2sim_actuator.py','tests/test_sim2sim_physics.py',
        'tests/test_sdk2_policy_runtime.py','tests/test_mujoco_model.py','tests/test_locomotion_v2.py','tests/test_dashboard_jobs.py']
    for name in sources:
        target=output/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    plan=read_json(output/'sources'/PLAN.relative_to(ROOT));watchdog_path=output/'sources'/plan['watchdog_plan'];guard=read_json(watchdog_path)
    if plan['hardware_enabled'] or plan['training_updates'] or plan['domain']!=1 or plan['interface']!='lo':raise ValueError('Simulator only')
    if plan['arm_order']!=['dc_pd_guard'] or plan['repeats']!=1:raise ValueError('Bounded five-case replay required')
    cases=protocol.cases_for(plan['terrain'])
    if [c.name for c in cases]!=plan['case_order']:raise ValueError('Frozen case order changed')
    runtime=warm_runtime();cfg=runtime.cfg
    if guard['actual_velocity_limits_rad_s']!=cfg['isaac_velocity_limits']:raise ValueError('State speed contract mismatch')
    write_json(output/'declared_plan.json',{'plan':plan,'guard':guard,'cases':[asdict(c) for c in cases]})
    executables=['b2w_mujoco_dc_bridge','b2w_dc_actuator_probe','b2w_sdk2_pd_watchdog','b2w_pd_fault_source']
    (output/'bin').mkdir()
    for name in executables:shutil.copy2(BUILD/name,output/'bin'/name)
    services_module.BUILD=output/'bin'
    reference=output/'references/actuator_pd.py';reference.parent.mkdir()
    if sha256(REFERENCE)!=REFERENCE_SHA256:raise ValueError('Reference changed')
    shutil.copyfile(REFERENCE,reference)
    shutil.copyfile(ROOT/plan['physx_snapshot'],output/'references/resolved_physx.json')
    previous_scene=ROOT/'logs/dashboard/jobs'/plan['baseline_job']/'sim2sim_armature/dc_baseline/stand/scene.xml'
    artifacts=[POLICY,POLICY.with_name('manifest.json'),ROOT/'policies/local/core_24650/model_24650.pt',
        ROOT/'policies/server/upstream_19999/export/policy.pt',ROOT/'vendor/manifest.json',previous_scene]+[BUILD/n for n in executables]+list(BUILD.glob('b2w_sdk2_native*.so'))
    manifest={'created_utc':utc_now(),'hardware_enabled':False,
        'executed_sha256':{n:sha256(ROOT/n) for n in sources},
        'artifact_sha256':{p.relative_to(ROOT).as_posix():sha256(p) for p in artifacts},
        'declared_plan_sha256':sha256(output/'declared_plan.json'),'reference_sha256':REFERENCE_SHA256,
        'python':sys.version,'torch':torch.__version__,'mujoco':mujoco.__version__}
    write_json(output/'preflight_manifest.json',manifest)
    rows=[];matrix=[];checks=None;law=None;error=None;loads=[];gc_enabled=gc.isenabled()
    try:
        for pattern in ('test_sim2sim_pd_guard.py','test_sim2sim_actuator.py','test_sim2sim_physics.py',
                        'test_sdk2_policy_runtime.py','test_mujoco_model.py','test_locomotion_v2.py','test_dashboard_jobs.py'):
            subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-q'],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'scripts/vendor_materials.py','verify'],cwd=ROOT,check=True)
        directory=output/'law';directory.mkdir();xml=make_dc_scene(directory,cfg,plan)
        if sha256(xml)!=sha256(previous_scene):raise ValueError('Physics XML changed beyond guard')
        model=mujoco.MjModel.from_xml_path(str(xml));joints=model.actuator_trnid[:,0]
        if not np.array_equal(model.jnt_range[joints[:12]],np.asarray(guard['actual_joint_ranges_rad'])):raise ValueError('Mechanical state limits differ')
        subprocess.run([str(output/'bin/b2w_dc_actuator_probe'),str(xml),str(directory/'probe.csv')],cwd=ROOT,check=True,
            stdout=(directory/'stdout.log').open('w'),stderr=(directory/'stderr.log').open('w'))
        law=audit_probe(directory/'probe.csv',cfg,plan,directory/'probe.csv');write_json(output/'actuator_audit.json',law)
        if not law['passed']:raise ValueError('Actuator law failed')
        gc.disable()
        for _ in range(guard['load']['workers']):
            loads.append(subprocess.Popen([sys.executable,'-c','x=1\nwhile True: x=(x*1664525+1013904223)&4294967295'],cwd=ROOT))
        print('START native guard separation and transport regression',flush=True)
        checks=guard_checks(output,watchdog_path)
        matrix=fault_matrix(output,guard,watchdog_path,watchdog_executable='b2w_sdk2_pd_watchdog',source_executable='b2w_pd_fault_source')
        write_json(output/'fault_regression.json',{'records':matrix,'passed':len(matrix)==48 and all(r['passed'] for r in matrix)})
        for process in loads:stop_process_tree(process)
        loads.clear()
        if not checks['passed'] or not checks['publisher']['passed'] or len(matrix)!=48 or not all(r['passed'] for r in matrix):
            raise ValueError('Native guard/fault regression failed')
        print('DONE native guard cases39 + transport cases48',flush=True)
        for case in cases:
            print('START',case.name,flush=True)
            directory=output/case.name
            row=trial(directory,case,plan,watchdog_path,cfg,bridge_executable='b2w_mujoco_dc_bridge',scene_factory=make_dc_scene,
                      watchdog_executable='b2w_sdk2_pd_watchdog')
            row['physics_xml_unchanged']=sha256(directory/'scene.xml')==sha256(xml)
            row['force_caps_preserved']=bool(np.all(np.asarray(row.get('safety',{}).get('torque_peak_nm',[np.inf]*16))<=np.asarray(cfg['torque_limits'])*(1+1e-6)))
            write_json(directory/'result.json',row);rows.append(row)
            write_json(output/'progress.json',{'completed':len(rows),'total':5,'records':rows})
            print('DONE',case.name,row['outcome'],row['policy_ticks'],row.get('transport_fault'),flush=True)
    except BaseException as failure:
        error=repr(failure);raise
    finally:
        for process in loads:stop_process_tree(process)
        if gc_enabled:gc.enable()
        partial=output/'faults/result.json'
        if partial.exists():matrix=read_json(partial)['cases']
        publication={'faults':publishing_gate(output/'faults/publish.csv',guard)} if (output/'faults/publish.csv').exists() else {}
        result={'records':rows,'guard_checks':checks,'fault_matrix_count':len(matrix),
            'fault_matrix_passed':len(matrix)==48 and all(r['passed'] for r in matrix),'publication':publication,'error':error,
            'actuator_law':law,'successes':sum(r['outcome']=='success' for r in rows),
            'full_programs':sum(r.get('measurement_complete',False) for r in rows),
            'simulation_qualified':False,'hardware_enabled':False,'training_updates':0}
        result['regression_passed']=bool(not error and checks and checks['passed'] and checks['publisher']['passed']
            and result['fault_matrix_passed'] and publication.get('faults',{}).get('passed'))
        result['motion_runtime_passed']=bool(len(rows)==5 and all(not r.get('transport_fault') and r.get('measurement_complete')
            and r['publisher']['passed'] and r['force_caps_preserved'] and r['physics_xml_unchanged'] and r.get('measurement_valid')
            and not r.get('safety',{}).get('unsafe_flags') for r in rows))
        write_json(output/'summary.json',result)
        manifest['raw_sha256']={p.relative_to(output).as_posix():sha256(p) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json'}
        write_json(output/'manifest.json',manifest)
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','guard_checks','actuator_law')},indent=2))
    if not result['regression_passed'] or not result['motion_runtime_passed']:raise SystemExit(2)


if __name__=='__main__':main()
