"""Managed native actuator audit and frozen one-reset Flat DDS diagnostic."""
from __future__ import annotations

from dataclasses import asdict
import csv
import gc
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import torch

import locomotion_v2_protocol as protocol
from locomotion57_protocol import reset_sample, Telemetry
from mujoco_model import DEFAULT_XML, initialize, validate_model_contract
from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256, utc_now
from run_sim2sim_faults import BUILD, POLICY, Services, wait_for, warm_runtime, publishing_gate
from sdk2_watchdog_client import policy_tick, RejectedPolicyTick
from sim2sim_physics_audit import REFERENCE, REFERENCE_SHA256, REFERENCE_COMMIT, model_audit, probe_audit
from sim2sim_timing import bounded_gc

PLAN = ROOT / "configs/sim2sim_physics_plan_20261012.json"


def make_scene(directory, cfg, plan):
    model=mujoco.MjModel.from_xml_path(str(DEFAULT_XML))
    validate_model_contract(model,cfg)
    data=mujoco.MjData(model);initialize(model,data,cfg,{"kind":"flat"})
    sample=reset_sample(plan["reset_seed"])
    data.qpos[:2]+=sample["xy"]
    yaw=sample["yaw"];data.qpos[3:7]=[np.cos(yaw/2),0,0,np.sin(yaw/2)]
    for index,name in enumerate(cfg["joint_names"]):
        joint=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,name.replace("_foot_joint","_wheel_joint"))
        if index<12:data.qpos[model.jnt_qposadr[joint]]+=sample["qdelta"][index]
        data.qvel[model.jnt_dofadr[joint]]=sample["dq"][index]
    spec=mujoco.MjSpec.from_file(str(DEFAULT_XML))
    spec.meshdir=str((DEFAULT_XML.parent/spec.meshdir).resolve())
    spec.geom("floor").friction=[plan["friction"],.005,.0001]
    spec.add_key(name="policy_reset",qpos=data.qpos.tolist(),qvel=data.qvel.tolist())
    spec.add_numeric(name="policy_velocity_limits",data=cfg["isaac_velocity_limits"])
    # MjSpec serializes keyframes at limited precision. Preserve the declared
    # reset samples exactly rather than changing the parity tolerance.
    document=ET.fromstring(spec.to_xml())
    key=document.find(".//key[@name='policy_reset']")
    key.set("qpos"," ".join(format(value,".17g") for value in data.qpos))
    key.set("qvel"," ".join(format(value,".17g") for value in data.qvel))
    path=directory/"scene.xml";path.write_text(ET.tostring(document,encoding="unicode"))
    write_json(directory/"reset.json",{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in sample.items()})
    return path


def score(directory, case, rows, origin_ns, cfg, completed, bridge_code, transport_fault):
    physics=list(csv.DictReader((directory/"physics.csv").open()))
    details=list(csv.DictReader((directory/"physics.csv.detailed.csv").open()))
    if len(physics)!=len(details):raise ValueError("Physics/detail sample mismatch")
    model=mujoco.MjModel.from_xml_path(str(directory/"scene.xml"))
    joints=model.actuator_trnid[:12,0]
    telemetry=Telemetry(1,cfg["torque_limits"],model.jnt_range[joints],model.opt.timestep)
    for simple,full in zip(physics,details):
        q=np.array([[float(full[f"m{i}_q"]) for i in range(16)]])
        dq=np.array([[float(full[f"m{i}_dq"]) for i in range(16)]])
        tau=np.array([[float(full[f"m{i}_tau"]) for i in range(16)]])
        finite=np.isfinite(np.r_[q.ravel(),dq.ravel(),tau.ravel(),[float(simple[k]) for k in ("x","y","z","qw","qx","qy","qz")]]).all()
        gravity=-np.cos(float(simple["tilt_rad"]))
        telemetry.update(q,dq,tau,np.array([gravity]),np.array([float(simple["forbidden_force_n"])]),
            np.array([finite]),np.array([True]),float(simple["time"]))
    safety=telemetry.result(0)
    if bridge_code not in (None,0):safety["unsafe_flags"].append("native_bridge_abort")
    if rows:
        targets=np.asarray([row["targets"] for row in rows]);previous=np.asarray(cfg["default_dof_pos"])
        safety["physical_target_slew_peak"]=np.max(np.abs(np.diff(np.vstack([previous,targets]),axis=0))/.02,axis=0).tolist()
    safety["wheel_rolling_residual_peak_m_s"]=None  # needs geometry-specific radius/contact interpretation
    timestamps=np.array([int(row["monotonic_ns"]) for row in details],dtype=np.int64)
    velocity=[];position=[];ages=[]
    for index in range(len(rows)):
        end=origin_ns+(index+1)*20_000_000
        selected=int(np.searchsorted(timestamps,end,side="right")-1)
        if selected<0:
            velocity.append([np.nan]*3);position.append([np.nan]*3);ages.append(None);continue
        full=details[selected];simple=physics[selected]
        velocity.append([float(full[k]) for k in ("body_vx","body_vy","body_wz")])
        position.append([float(simple[k]) for k in ("x","y","z")])
        ages.append((end-int(full["monotonic_ns"]))/1e9)
    velocity=np.asarray(velocity).reshape(-1,3);position=np.asarray(position).reshape(-1,3)
    np.savez_compressed(directory/"measurement.npz",velocity=velocity,position=position,
                        commands=case.schedule()[0],physics_sample_age_s=np.array([np.nan if a is None else a for a in ages]))
    result=protocol.assess(case,velocity,position,safety,completed,protocol.geometry(case.terrain))
    result,_=protocol.finalize_result(case,result,None,completed)
    result.update(case=case.name,terrain=case.terrain,policy=24650,bridge_returncode=bridge_code,
        transport_fault=transport_fault,policy_ticks=len(rows),expected_policy_ticks=case.steps,
        physics_sample_age_max_s=max((a for a in ages if a is not None),default=None),
        measurement_complete=bool(len(rows)==case.steps and np.isfinite(velocity).all()))
    result["measurement_valid"]=bool(len(rows) and np.isfinite(velocity).all()
        and all(a is not None and 0<=a<=.01 for a in ages))
    return result


def trial(directory, case, plan, watchdog_plan_path, cfg, *, bridge_executable="b2w_mujoco_bridge", scene_factory=make_scene, watchdog_executable="b2w_sdk2_watchdog", cpu_roles=None, profile_timing=False):
    directory.mkdir(parents=True,exist_ok=True)
    runtime=warm_runtime();xml=scene_factory(directory,cfg,plan)
    runtime.timing_enabled=profile_timing
    services=Services(directory,watchdog_plan_path);rows=[];bridge=None;error=None;origin_ns=0;code=None;rejected=None
    if cpu_roles:services.cpu_roles={bridge_executable:cpu_roles['physics'],watchdog_executable:cpu_roles['watchdog']}
    cycle=bounded_gc();cycle.__enter__()
    try:
        client,_=services.service(watchdog_executable)
        bridge=services.launch(bridge_executable,[xml,case.steps*.02+5,directory/"physics.csv"])
        wait_for(lambda:client.state().get("count",0)>=3)
        origin_ns=time.monotonic_ns()
        for index,command in enumerate(case.schedule()[0]):
            if bridge.poll() is not None:break
            row=policy_tick(client,runtime,command.tolist())
            if index==0:client.arm()
            row["scheduled_start_ns"]=origin_ns+index*20_000_000;rows.append(row)
            deadline=(origin_ns+(index+1)*20_000_000)/1e9
            time.sleep(max(0,deadline-time.monotonic()))
        final=client.state()
        if final["fault"]:error=final["fault"]
        write_json(directory/"final_native_state.json",final)
        client.stop();time.sleep(.004)
    except RejectedPolicyTick as failure:
        error=repr(failure)
        rejected=failure.detail
        rejected["policy_tick"]=len(rows)
        write_json(directory/"rejected_policy_tick.json",rejected)
    except (RuntimeError,TimeoutError) as failure:
        error=repr(failure)
    finally:
        if error and services.clients:
            try:write_json(directory/"final_native_state.json",services.clients[0].state())
            except (RuntimeError,TimeoutError,OSError):pass
        try:services.close()
        finally:cycle.__exit__(None,None,None)
        if bridge is not None:code=bridge.returncode
        with (directory/"policy.jsonl").open("w") as stream:
            for row in rows:stream.write(json.dumps(row,allow_nan=False)+"\n")
    if not (directory/"physics.csv").exists():
        result={"case":case.name,"outcome":"infrastructure_failure","transport_fault":error,"completed":False}
    else:
        result=score(directory,case,rows,origin_ns,cfg,len(rows)==case.steps and not error and code==0,code,error)
    result["publisher"]=publishing_gate(directory/"publish.csv",read_json(watchdog_plan_path)) if (directory/"publish.csv").exists() else {"passed":False}
    result["rejected_policy_tick"] = None if rejected is None else rejected["policy_tick"]
    write_json(directory/"result.json",result);return result


def main():
    managed_entrypoint()
    def cancelled(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    torch.set_num_threads(1)
    output=Path(os.environ["B2W_JOB_DIR"])/"sim2sim_physics";output.mkdir(parents=True,exist_ok=True)
    sources=["scripts/run_sim2sim_physics.py","scripts/sim2sim_physics_audit.py",
        "scripts/run_sim2sim_faults.py","scripts/run_sim2sim.py","scripts/sdk2_watchdog_client.py",
        "scripts/sdk2_policy_runtime.py","scripts/check_policy_contract.py","scripts/evaluation_policy.py",
        "scripts/mujoco_model.py","scripts/locomotion_v2_protocol.py","scripts/locomotion57_protocol.py",
        "scripts/core_locomotion_protocol.py","scripts/run_support.py","scripts/job_manager.py",
        "scripts/job_worker.py","scripts/manage_runs.py","sim2sim/CMakeLists.txt","sim2sim/actuator_probe.cpp",
        "sim2sim/bridge.cpp","sim2sim/watchdog.cpp","sim2sim/sdk2_io.hpp","sim2sim/unix_rpc.hpp",
        "configs/sim2sim_physics_plan_20261012.json","configs/sim2sim_fault_plan_20261012.json",
        "tests/test_sim2sim_physics.py","tests/test_sdk2_policy_runtime.py"]
    for name in sources:
        target=output/"sources"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    reference=output/"references/actuator_pd.py";reference.parent.mkdir(parents=True,exist_ok=True)
    if sha256(REFERENCE)!=REFERENCE_SHA256:raise ValueError("Reference SHA mismatch")
    shutil.copyfile(REFERENCE,reference)
    frozen_plan=output/"sources/configs/sim2sim_physics_plan_20261012.json";plan=read_json(frozen_plan)
    if plan["hardware_enabled"] or plan["training_updates"] or plan["domain"]!=1 or plan["interface"]!="lo":raise ValueError("Simulator-only plan required")
    cases=protocol.cases_for(plan["terrain"])
    if [case.name for case in cases]!=plan["case_order"]:raise ValueError("Case order changed")
    runtime=warm_runtime();cfg=runtime.cfg
    declared={"plan":plan,"cases":[asdict(case) for case in cases],"reset":reset_sample(plan["reset_seed"])["yaw"]}
    write_json(output/"declared_plan.json",declared)
    artifacts=[POLICY,POLICY.with_name("manifest.json"),ROOT/"policies/local/core_24650/model_24650.pt",
        ROOT/"policies/server/upstream_19999/export/policy.pt",ROOT/"vendor/manifest.json",
        BUILD/"b2w_actuator_probe",BUILD/"b2w_mujoco_bridge",BUILD/"b2w_sdk2_watchdog"]
    manifest={"created_utc":utc_now(),"executed_sha256":{n:sha256(ROOT/n) for n in sources},
        "artifact_sha256":{p.relative_to(ROOT).as_posix():sha256(p) for p in artifacts},
        "reference":{"repository":"isaac-sim/IsaacLab","tag":"v2.3.2","commit":REFERENCE_COMMIT,
            "path":"source/isaaclab/isaaclab/actuators/actuator_pd.py","sha256":REFERENCE_SHA256,
            "git_blob_sha1":__import__("hashlib").sha1(b"blob "+str(reference.stat().st_size).encode()+b"\0"+reference.read_bytes()).hexdigest()},
        "declared_plan_sha256":sha256(output/"declared_plan.json"),"frozen_plan_sha256":sha256(frozen_plan),
        "python":sys.version,"torch":torch.__version__,"mujoco":mujoco.__version__,"hardware_enabled":False}
    write_json(output/"preflight_manifest.json",manifest)
    records=[];audit=None;error=None;gc_enabled=gc.isenabled()
    try:
        for pattern in ("test_sim2sim_physics.py","test_sdk2_policy_runtime.py","test_mujoco_model.py","test_locomotion_v2.py","test_dashboard_jobs.py"):
            subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-q"],cwd=ROOT,check=True)
        subprocess.run([sys.executable,"scripts/vendor_materials.py","verify"],cwd=ROOT,check=True)
        audit_directory=output/"actuator_audit";audit_directory.mkdir()
        xml=make_scene(audit_directory,cfg,plan)
        subprocess.run([str(BUILD/"b2w_actuator_probe"),str(xml),str(audit_directory/"probe.csv")],cwd=ROOT,check=True,
            stdout=(audit_directory/"stdout.log").open("w"),stderr=(audit_directory/"stderr.log").open("w"))
        audit={"model":model_audit(cfg),"actuator_law":probe_audit(audit_directory/"probe.csv",cfg)}
        write_json(output/"physics_audit.json",audit)
        if not audit["actuator_law"]["audit_passed"]:raise ValueError("Actuator numerical audit failed")
        gc.disable()
        watchdog_plan_path=output/"sources/configs/sim2sim_fault_plan_20261012.json"
        for case in cases:
            print("START",case.name,flush=True)
            records.append(trial(output/case.name,case,plan,watchdog_plan_path,cfg))
            write_json(output/"progress.json",{"completed":len(records),"total":len(cases),"records":records})
            print("DONE",case.name,records[-1]["outcome"],flush=True)
    except BaseException as failure:
        error=repr(failure);raise
    finally:
        if gc_enabled:gc.enable()
        infrastructure_passed=(not error and len(records)==len(cases) and all(not row.get("transport_fault")
            and row.get("measurement_valid") and row["publisher"]["passed"] for row in records))
        result={"audit":None if audit is None else audit["actuator_law"],"records":records,"error":error,
            "infrastructure_passed":bool(infrastructure_passed),"successes":sum(row["outcome"]=="success" for row in records),
            "simulation_qualified":False,"hardware_enabled":False,"live_isaac_comparison":False}
        write_json(output/"summary.json",result)
        manifest["raw_sha256"]={p.relative_to(output).as_posix():sha256(p) for p in output.rglob("*") if p.is_file() and p.name!="manifest.json"}
        write_json(output/"manifest.json",manifest)
    print(json.dumps(result,indent=2))
    if not result["infrastructure_passed"]:raise SystemExit(2)


if __name__=="__main__":main()
