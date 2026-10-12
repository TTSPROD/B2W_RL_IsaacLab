"""Managed resolved PhysX audit; preserves parent/export and runs no optimizer."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now,local_command,stop_process_tree
import sim2sim_isaac_protocol as protocol

PLAN=ROOT/"configs/sim2sim_isaac_plan_20261012.json"


def main():
    managed_entrypoint()
    def cancelled(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    output=Path(os.environ["B2W_JOB_DIR"])/"isaac_audit";output.mkdir(parents=True,exist_ok=True)
    sources=["scripts/run_sim2sim_isaac_audit.py","scripts/run_isaac_audit_child.py",
        "scripts/sim2sim_isaac_protocol.py","scripts/isaac_physics_snapshot.py",
        "scripts/eval_fullcycle_terrain.py","scripts/locomotion_v2_protocol.py",
        "scripts/locomotion57_protocol.py","scripts/core_locomotion_protocol.py",
        "scripts/check_policy_contract.py","scripts/evaluation_policy.py",
        "scripts/b2w_runtime.py","scripts/local_b2w_assets.py","scripts/run_support.py",
        "scripts/job_manager.py","scripts/job_worker.py","scripts/manage_runs.py",
        "scripts/setup_isaac_ubuntu.sh","requirements/isaac-ubuntu-constraints.txt",
        "scripts/prepare_isaac_native_libs.py",
        "requirements/isaaclab-sim51-metadata.patch","configs/sim2sim_isaac_plan_20261012.json",
        "tests/test_isaac_physics_audit.py"]
    for name in sources:
        target=output/"sources"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    runtime=read_json(ROOT/".runtime/isaac-ubuntu-runtime.json")
    write_json(output/"runtime_installation.json",runtime)
    native_libs=ROOT/".runtime/isaac-native-libs/manifest.json"
    if native_libs.exists():shutil.copyfile(native_libs,output/"native_libraries_manifest.json")
    plan=read_json(PLAN)
    if plan["hardware_enabled"] or plan["training_updates"] or not runtime["eula_accepted"]:raise ValueError("Simulator-only, licensed runtime required")
    commit=subprocess.check_output(["git","-C",str(ROOT/".runtime/IsaacLab"),"rev-parse","HEAD"],text=True).strip()
    if commit!=plan["isaaclab_commit"]:raise ValueError("Wrong Isaac Lab revision")
    shutil.copyfile(ROOT/"logs/setup/isaac-ubuntu/pip-freeze.txt",output/"pip-freeze.txt")
    subprocess.run(["nvidia-smi"],stdout=(output/"nvidia-smi.txt").open("w"),check=True)
    mapping={"24650":"policies/local/core_24650/export"};write_json(output/"policy_map.json",mapping)
    declared=protocol.protocol_manifest()
    declared.update(source_sha256={name:sha256(ROOT/name) for name in sources},policy_map_sha256=sha256(output/"policy_map.json"))
    write_json(output/"declared_plan.json",declared)
    artifacts=[ROOT/"policies/local/core_24650/model_24650.pt",ROOT/"policies/local/core_24650/export/policy.pt",
        ROOT/"policies/local/core_24650/export/manifest.json",ROOT/"policies/server/upstream_19999/export/policy.pt",
        ROOT/"vendor/manifest.json",ROOT/".runtime/IsaacLab/source/isaaclab/setup.py"]
    lab_source={p.relative_to(ROOT/".runtime/IsaacLab").as_posix():sha256(p)
        for p in (ROOT/".runtime/IsaacLab/source").rglob("*") if p.is_file() and p.suffix in {".py",".kit",".toml"}}
    manifest={"created_utc":utc_now(),"hardware_enabled":False,"training_updates":0,
        "executed_sha256":declared["source_sha256"],"isaaclab_commit":commit,"isaaclab_source_sha256":lab_source,
        "artifact_sha256":{p.relative_to(ROOT).as_posix():sha256(p) for p in artifacts},
        "frozen_plan_sha256":sha256(PLAN),"declared_plan_sha256":sha256(output/"declared_plan.json"),
        "pip_freeze_sha256":sha256(output/"pip-freeze.txt")}
    write_json(output/"preflight_manifest.json",manifest)
    process=None;error=None;data=None
    try:
        for pattern in ("test_isaac_physics_audit.py","test_dashboard_jobs.py","test_locomotion_v2.py"):
            subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-q"],cwd=ROOT,check=True)
        subprocess.run([sys.executable,"scripts/vendor_materials.py","verify"],cwd=ROOT,check=True)
        arguments=["--terrain",plan["terrain"],"--output",str(output/"flat_mu_100.json"),"--seeds","1",
            "--protocol-module","sim2sim_isaac_protocol","--policy-map",str(output/"policy_map.json"),
            "--resolved-physics-output",str(output/"resolved_physx.json"),"--audit-target-guards"]
        print("START native Isaac/PhysX audit",flush=True)
        with (output/"isaac.stdout.log").open("w") as stdout,(output/"isaac.stderr.log").open("w") as stderr:
            env=dict(os.environ)
            libraries=ROOT/".runtime/isaac-native-libs/usr/lib/x86_64-linux-gnu"
            if libraries.is_dir():env["LD_LIBRARY_PATH"]=str(libraries)+(":"+env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
            process=subprocess.Popen(local_command("scripts/run_isaac_audit_child.py",arguments),cwd=ROOT,stdout=stdout,stderr=stderr,env=env)
            code=process.wait()
        if code!=0:raise RuntimeError(f"Isaac child exit {code}; see isaac.stderr.log")
        data=read_json(output/"flat_mu_100.json")
        if len(data["records"])!=5 or not (output/"resolved_physx.json").exists():raise ValueError("Incomplete live audit")
        for p in artifacts:
            if sha256(p)!=manifest["artifact_sha256"][p.relative_to(ROOT).as_posix()]:raise ValueError("Runtime artifact changed during audit")
    except BaseException as failure:
        error=repr(failure);raise
    finally:
        if process is not None:stop_process_tree(process)
        summary={"execution_passed":not error and data is not None,"error":error,"hardware_enabled":False,
            "simulation_qualified":False,"training_updates":0,
            "records":None if data is None else data["records"],
            "counterfactual_target_guard":None if data is None else data["counterfactual_target_guard"],
            "successes":None if data is None else sum(r["outcome"]=="success" for r in data["records"])}
        write_json(output/"summary.json",summary)
        manifest["raw_sha256"]={p.relative_to(output).as_posix():sha256(p) for p in output.rglob("*")
            if p.is_file() and p.name!="manifest.json"}
        write_json(output/"manifest.json",manifest)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=="__main__":main()
