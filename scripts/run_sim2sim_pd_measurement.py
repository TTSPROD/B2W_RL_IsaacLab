"""One declared yaw repeat for telemetry availability, with frozen prior bytes."""
import os,shutil,json,signal
from pathlib import Path
import numpy as np,torch
import run_sim2sim_faults as services_module
from run_sim2sim_faults import warm_runtime
from run_sim2sim_physics import trial
from sim2sim_actuator_factor import make_dc_scene
import locomotion_v2_protocol as protocol
from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now


def main():
    managed_entrypoint()
    def cancelled(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    torch.set_num_threads(1)
    declared=read_json(ROOT/'configs/sim2sim_pd_measurement_repeat_20261012.json')
    if declared['case']!='yaw' or declared['repeats']!=1 or declared['hardware_enabled'] or declared['training_updates']:raise ValueError('Bounded repeat only')
    source=ROOT/'logs/dashboard/jobs'/declared['source_job']/'sim2sim_pd_guard'
    original=read_json(source/'manifest.json')
    for name,digest in original['raw_sha256'].items():
        if sha256(source/name)!=digest:raise ValueError('Previous raw changed: '+name)
    plan_path=source/'sources/configs/sim2sim_pd_guard_motion_20261012.json'
    if sha256(plan_path)!=declared['frozen_motion_plan_sha256']:raise ValueError('Motion plan changed')
    plan=read_json(plan_path);case=next(c for c in protocol.cases_for(plan['terrain']) if c.name=='yaw')
    output=Path(os.environ['B2W_JOB_DIR'])/'sim2sim_pd_measurement';output.mkdir()
    files=['scripts/run_sim2sim_pd_measurement.py','scripts/run_sim2sim_physics.py','scripts/run_sim2sim_faults.py',
        'scripts/sim2sim_actuator_factor.py','scripts/sim2sim_physics_audit.py','scripts/sdk2_policy_runtime.py',
        'scripts/sdk2_watchdog_client.py','scripts/check_policy_contract.py','scripts/evaluation_policy.py',
        'scripts/mujoco_model.py','scripts/locomotion57_protocol.py','scripts/locomotion_v2_protocol.py',
        'scripts/core_locomotion_protocol.py','scripts/run_support.py','configs/sim2sim_pd_measurement_repeat_20261012.json']
    for name in files:
        target=output/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        if name in original['executed_sha256'] and sha256(ROOT/name)!=original['executed_sha256'][name]:raise ValueError('Runtime changed since replay '+name)
    (output/'bin').mkdir()
    for name in ('b2w_sdk2_pd_watchdog','b2w_mujoco_dc_bridge'):shutil.copy2(source/'bin'/name,output/'bin'/name)
    services_module.BUILD=output/'bin'
    shutil.copyfile(plan_path,output/'frozen_motion_plan.json');shutil.copyfile(source/'sources'/plan['watchdog_plan'],output/'frozen_guard_plan.json')
    cfg=warm_runtime().cfg
    artifact_keys=['policies/local/core_24650/export/policy.pt','policies/local/core_24650/export/manifest.json',
        'policies/local/core_24650/model_24650.pt','policies/server/upstream_19999/export/policy.pt']
    for name in artifact_keys:
        if sha256(ROOT/name)!=original['artifact_sha256'][name]:raise ValueError('Policy artifact changed '+name)
    manifest={'created_utc':utc_now(),'source_job':declared['source_job'],'original_manifest_sha256':sha256(source/'manifest.json'),
        'executed_sha256':{n:sha256(ROOT/n) for n in files},'artifact_sha256':{n:sha256(ROOT/n) for n in artifact_keys},
        'binary_sha256':{p.name:sha256(p) for p in (output/'bin').iterdir()},'hardware_enabled':False}
    write_json(output/'preflight_manifest.json',manifest);result=None
    try:
        result=trial(output/'yaw',case,plan,output/'frozen_guard_plan.json',cfg,scene_factory=make_dc_scene,
            bridge_executable='b2w_mujoco_dc_bridge',watchdog_executable='b2w_sdk2_pd_watchdog')
        result['physics_xml_unchanged']=sha256(output/'yaw/scene.xml')==sha256(source/'law/scene.xml')
        result['force_caps_preserved']=bool(np.all(np.asarray(result['safety']['torque_peak_nm'])<=np.asarray(cfg['torque_limits'])*(1+1e-6)))
        result['repeat_runtime_passed']=bool(result['measurement_valid'] and result['measurement_complete'] and not result['transport_fault']
            and result['publisher']['passed'] and not result['safety']['unsafe_flags'] and result['force_caps_preserved'] and result['physics_xml_unchanged'])
        write_json(output/'yaw/result.json',result)
    finally:
        write_json(output/'summary.json',{'result':result,'simulation_qualified':False,'hardware_enabled':False,'training_updates':0})
        manifest['raw_sha256']={p.relative_to(output).as_posix():sha256(p) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json'}
        write_json(output/'manifest.json',manifest)
    print(json.dumps(result,indent=2))
    if not result['repeat_runtime_passed']:raise SystemExit(2)


if __name__=='__main__':main()
