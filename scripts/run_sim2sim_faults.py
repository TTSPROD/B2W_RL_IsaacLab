"""Frozen native-watchdog plan: real MuJoCo nominal + repeated DDS fault matrix."""
from __future__ import annotations
import csv
import ctypes
import gc
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import uuid

from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256, utc_now, stop_process_tree
from sdk2_watchdog_client import WatchdogClient, policy_tick

BUILD = ROOT/".runtime/sim2sim-build"
POLICY = ROOT/"policies/local/core_24650/export/policy.pt"
PLAN = ROOT/"configs/sim2sim_fault_plan_20261012.json"


def wait_for(predicate, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            value=predicate()
            if value:return value
        except (FileNotFoundError,ConnectionRefusedError,TimeoutError,socket_error):
            pass
        time.sleep(.002)
    raise TimeoutError("Native service readiness/fault deadline exceeded")


socket_error = __import__("socket").timeout


class Services:
    def __init__(self, directory, plan_path):
        self.directory=directory;directory.mkdir(parents=True,exist_ok=True)
        self.plan_path=plan_path
        self.processes=[];self.streams=[];self.clients=[]
        self.cpu_roles={}

    def launch(self, executable, arguments):
        stdout=(self.directory/(executable+".stdout.log")).open("w")
        stderr=(self.directory/(executable+".stderr.log")).open("w")
        self.streams.extend((stdout,stderr))
        command=[str(BUILD/executable),*map(str,arguments)]
        if executable in self.cpu_roles:
            command=['taskset','--cpu-list',','.join(map(str,self.cpu_roles[executable])),*command]
        process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr)
        self.processes.append(process);return process

    def service(self, executable):
        name="b2w-"+uuid.uuid4().hex
        process=self.launch(executable,[name,self.plan_path,self.directory])
        client=WatchdogClient(name);self.clients.append(client)
        wait_for(lambda:client.state() if process.poll() is None else (_ for _ in ()).throw(RuntimeError(executable+" exited")))
        return client,name

    def close(self):
        for process in reversed(self.processes):stop_process_tree(process)
        for client in self.clients:client.close()
        for stream in self.streams:stream.close()


def warm_runtime():
    from sdk2_policy_runtime import PolicyRuntime
    from check_policy_contract import fixtures
    runtime=PolicyRuntime(POLICY)
    neutral=fixtures(runtime.cfg)["neutral_reset"]
    for _ in range(8):runtime.step(neutral,[0,0,0])
    runtime.reset();return runtime


def actor_exit_helper(name, ready):
    import torch
    torch.set_num_threads(1)
    runtime=warm_runtime();client=WatchdogClient(name)
    status=client.state();client.epoch=status["epoch"]
    client.command_seq=status["command_seq"];client.inference_seq=status["inference_seq"]
    row=policy_tick(client,runtime,[0,0,0]);client.arm()
    write_json(ready,row["accepted"])
    time.sleep(120)  # killed between ticks by the supervisor-owned test producer


def nominal(output, plan, plan_path):
    from run_sim2sim import scene, percentiles
    runtime=warm_runtime();directory=output/"nominal";services=Services(directory,plan_path)
    rows=[];fault=None;bridge=None;final={};contract=None
    try:
        client,_=services.service("b2w_sdk2_watchdog")
        xml,contract=scene(directory,runtime.cfg)
        bridge=services.launch("b2w_mujoco_bridge",[xml,plan["nominal_duration_s"]+2,directory/"physics.csv"])
        wait_for(lambda:client.state().get("count",0)>=3)
        origin=time.monotonic();deadline=origin
        while time.monotonic()-origin<plan["nominal_duration_s"] and bridge.poll() is None:
            elapsed=time.monotonic()-origin
            command=([.2,0,0] if 2<=elapsed<4 else [0,.2,0] if 5<=elapsed<6 else [0,0,.2] if 7<=elapsed<8 else [0,0,0])
            row=policy_tick(client,runtime,command)
            if not rows:client.arm()
            row["elapsed_s"]=elapsed;rows.append(row)
            deadline+=.02;time.sleep(max(0,deadline-time.monotonic()))
        final=client.state();fault=final["fault"]
        client.stop();time.sleep(.01)
        if bridge.poll() is None:bridge.terminate();bridge.wait(timeout=10)
        code=bridge.returncode
    except (RuntimeError,TimeoutError) as error:
        fault=repr(error);code=bridge.poll() if bridge else None
    finally:
        services.close()
        with (directory/"policy.jsonl").open("w") as stream:
            for row in rows:stream.write(json.dumps(row,allow_nan=False)+"\n")
    physics=list(csv.DictReader((directory/"physics.csv").open())) if (directory/"physics.csv").exists() else []
    result={"status":"passed" if len(rows)==plan["nominal_duration_s"]*50 and not fault and code==0 else "failed",
        "policy_ticks":len(rows),"native_status":final,"fault":fault,"bridge_returncode":code,
        "model_contract":contract,
        "physics_samples":len(physics),"inference_s":percentiles([(r["inference_end_ns"]-r["inference_start_ns"])/1e9 for r in rows]),
        "max_tilt_rad":max((float(r["tilt_rad"]) for r in physics),default=None),"simulation_qualified":False}
    write_json(directory/"summary.json",result);return result


def fault_matrix(output, plan, plan_path, *, watchdog_executable="b2w_sdk2_watchdog", source_executable="b2w_dds_fault_source"):
    runtime=warm_runtime();directory=output/"faults";services=Services(directory,plan_path)
    results=[]
    try:
        client,name=services.service(watchdog_executable)
        source,_=services.service(source_executable)
        wait_for(lambda:client.state().get("count",0)>=3)
        for repeat in range(plan["repeats"]):
            for case in plan["cases"]:
                key=case["id"]
                source.call("MODE","normal");time.sleep(.014)
                client.recover();runtime.reset()
                first=policy_tick(client,runtime,[0,0,0]);client.arm()
                assert first["observation"][41:]==[0.0]*16
                wait_for(lambda:not source.state()["last_disabled"])
                baseline=client.state();injected=time.monotonic_ns();origin=injected;extra={};observed=None
                motors=first["motors"]
                if key=="sparse_packet_loss":
                    source.call("MODE","sparse")
                    deadline=time.monotonic();end=deadline+.3;count=0
                    while time.monotonic()<end:
                        policy_tick(client,runtime,[0,0,0]);count+=1
                        deadline+=.02;time.sleep(max(0,deadline-time.monotonic()))
                    observed=client.state();passed=not observed["fault"] and observed["count"]>baseline["count"]
                    extra={"policy_ticks":count,"state_progress":observed["count"]-baseline["count"]}
                elif key in {"state_disconnect","duplicate_tick","state_reorder","bad_crc","nan_state","inf_state","bad_quaternion","state_restart_recovery"}:
                    mode={"state_disconnect":"pause","duplicate_tick":"duplicate","state_reorder":"reorder","bad_crc":"bad_crc","nan_state":"nan","inf_state":"inf","bad_quaternion":"bad_quat","state_restart_recovery":"restart"}[key]
                    injected=source.call("MODE",mode)["applied_ns"];origin=injected
                    observed=wait_for(lambda:(s if (s:=client.state())["fault"] else None),timeout=.25)
                elif key=="stale_command":
                    origin=baseline["command_ns"]
                    deadline=time.monotonic();end=deadline+.15
                    while time.monotonic()<end:
                        try:policy_tick(client,runtime,[0,0,0],refresh_command=False)
                        except RuntimeError:break
                        deadline+=.02;time.sleep(max(0,deadline-time.monotonic()))
                    observed=wait_for(lambda:(s if (s:=client.state())["fault"] else None),timeout=.1)
                elif key=="expired_target":
                    origin=baseline["target_ns"]
                    end=time.monotonic()+.12
                    while time.monotonic()<end and not client.state()["fault"]:
                        client.command([0,0,0]);time.sleep(.01)
                    observed=client.state()
                elif key in {"gil_inference_hang","late_target"}:
                    client.command([0,0,0]);begin=client.begin(client.state());origin=begin["inference_ns"]
                    # PyDLL keeps the GIL during this blocking libc call.
                    sleep_with_gil=ctypes.PyDLL(None).usleep
                    sleep_with_gil.argtypes=[ctypes.c_uint];sleep_with_gil.restype=ctypes.c_int
                    sleep_with_gil(100000)
                    observed=client.state()
                    if key=="late_target":
                        before=observed["target_generation"];reply=client.target(motors,require_ok=False)
                        extra={"late_target_rejected":not reply["ok"],"target_generation_unchanged":reply["target_generation"]==before}
                elif key=="actor_process_exit":
                    client.recover();runtime.reset()
                    ready=directory/f"actor_exit_{repeat}.json"
                    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--actor-exit-helper",name,str(ready)],cwd=ROOT,
                        stdout=subprocess.DEVNULL,stderr=(directory/f"actor_exit_{repeat}.stderr.log").open("w"))
                    services.processes.append(process)
                    wait_for(lambda:read_json(ready) if ready.exists() else None)
                    killed=time.monotonic_ns();process.kill();process.wait(timeout=5)
                    baseline=client.state();origin=baseline["target_ns"];injected=killed
                    observed=wait_for(lambda:(s if (s:=client.state())["fault"] else None),timeout=.15)
                    extra={"actor_returncode":process.returncode,"actor_killed_ns":killed}
                elif key=="operator_stop":
                    injected=time.monotonic_ns();origin=injected;client.stop();observed=client.state()
                elif key=="target_saturation":
                    client.command([0,0,0]);client.begin(client.state())
                    invalid=[list(m) for m in motors];invalid[12][2]=plan.get("target_saturation_probe_rad_s",51.0)
                    injected=time.monotonic_ns();origin=injected
                    reply=client.target(invalid,require_ok=False);observed=client.state()
                    extra={"target_rejected":not reply["ok"],"target_generation_unchanged":observed["target_generation"]==baseline["target_generation"]}
                else:raise ValueError("Unimplemented frozen case: "+key)
                if key!="sparse_packet_loss":
                    expected=case["expected"].split(";")[0]
                    expected="inference_timeout" if key=="late_target" else "state_reordered" if key=="state_restart_recovery" else expected
                    budget=0 if case["deadline"]=="immediate" else plan["deadlines_ns"][case["deadline"]]
                    # Source/controller shutdown affects test state; receive LowCmd independently.
                    observation=wait_for(lambda:(s if (s:=source.state())["last_disabled"] and s["first_disabled_ns"]>=injected else None),timeout=.15)
                    # The fault can precede the next publisher tick. Refresh after
                    # the independent DDS observer, rather than using a zero timestamp.
                    observed=wait_for(lambda:(s if (s:=client.state())["first_disabled_ns"]>=injected else None),timeout=.15)
                    latency=observed["fault_ns"]-origin;publish_latency=observed["first_disabled_ns"]-origin
                    observer_latency=observation["first_disabled_ns"]-origin
                    passed=(observed["fault"]==expected and 0<=latency<=budget+plan["detection_slack_ns"]
                        and 0<=publish_latency<=budget+plan["detection_slack_ns"]
                        and 0<=observer_latency<=budget+plan["detection_slack_ns"] and observation["crc_valid"])
                    extra.update({"latency_ns":latency,"disabled_publish_latency_ns":publish_latency,
                        "disabled_observer_latency_ns":observer_latency,"observer":observation})
                    if key=="late_target":passed &= extra["late_target_rejected"] and extra["target_generation_unchanged"]
                    if key=="target_saturation":passed &= extra["target_rejected"] and extra["target_generation_unchanged"]
                    source.call("MODE","normal");time.sleep(.014)
                    no_resume=client.state();passed &= bool(no_resume["fault"]) and no_resume["last_disabled"]
                    extra["automatic_resume_blocked"]=bool(no_resume["fault"]) and no_resume["last_disabled"]
                    if key=="state_restart_recovery":
                        old_epoch=client.epoch;old_token=client.inference_seq
                        recovered=client.recover();runtime.reset()
                        stale=client.call("TARGET",old_epoch,old_token,*(v for m in motors for v in m),require_ok=False)
                        fresh=policy_tick(client,runtime,[0,0,0]);client.arm()
                        extra.update({"recovery_epoch_incremented":recovered["epoch"]==old_epoch+1,
                            "recovery_disarmed_and_cleared":not recovered["armed"] and not recovered["pending"]
                                and all(recovered[x]==0 for x in ("command_seq","inference_seq","command_ns","target_ns","inference_ns")),
                            "old_epoch_rejected":not stale["ok"] and stale["error"]=="stale_epoch" and not stale["fault"],
                            "history_reset":fresh["observation"][41:]==[0.0]*16,"fresh_target_accepted":fresh["accepted"]["ok"]})
                        passed &= all(extra[x] for x in ("recovery_epoch_incremented","recovery_disarmed_and_cleared","old_epoch_rejected","history_reset","fresh_target_accepted"))
                result={"case":key,"repeat":repeat,"passed":bool(passed),"injected_ns":injected,
                    "origin_ns":origin,"observed":observed,**extra}
                results.append(result);write_json(directory/"progress.json",{"completed":len(results),"results":results})
        client.stop();time.sleep(.01)
    finally:
        services.close()
        write_json(directory/"result.json",{"cases":results,"passed":len(results)==len(plan["cases"])*plan["repeats"] and all(r["passed"] for r in results)})
    return results


def publishing_gate(path, plan):
    from run_sim2sim import percentiles
    rows=list(csv.DictReader(path.open()))
    starts=[int(r["start_ns"]) for r in rows];intervals=[b-a for a,b in zip(starts,starts[1:])]
    hz=(len(starts)-1)*1e9/(starts[-1]-starts[0]) if len(starts)>1 else 0
    return {"samples":len(rows),"hz":hz,"interval_ns":percentiles(intervals),
        "passed":bool(intervals) and max(intervals)<=plan["max_publish_interval_ns"] and hz>=plan["minimum_publish_hz"]
                    and all(r["ok"]=="1" for r in rows)}


def main():
    if len(sys.argv)>1 and sys.argv[1]=="--actor-exit-helper":
        actor_exit_helper(sys.argv[2],Path(sys.argv[3]));return
    managed_entrypoint()
    def cancelled(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    import torch
    torch.set_num_threads(1)
    output=Path(os.environ["B2W_JOB_DIR"])/"sim2sim_faults";output.mkdir(parents=True,exist_ok=True)
    sources=["configs/sim2sim_fault_plan_20261012.json","sim2sim/sdk2_io.hpp","sim2sim/unix_rpc.hpp",
        "sim2sim/watchdog.cpp","sim2sim/fault_source.cpp","sim2sim/sdk2_transport.cpp","sim2sim/bridge.cpp",
        "sim2sim/CMakeLists.txt","scripts/run_sim2sim_faults.py","scripts/run_sim2sim.py",
        "scripts/sdk2_watchdog_client.py","scripts/sdk2_policy_runtime.py","scripts/run_support.py",
        "scripts/job_manager.py","scripts/job_worker.py","scripts/check_policy_contract.py",
        "scripts/evaluation_policy.py","scripts/mujoco_model.py","tests/test_sdk2_policy_runtime.py"]
    hashes={name:sha256(ROOT/name) for name in sources}
    for name in sources:
        target=output/"sources"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    plan_path=output/"sources/configs/sim2sim_fault_plan_20261012.json";plan=read_json(plan_path)
    native_binding=list(BUILD.glob("b2w_sdk2_native*.so"))
    if len(native_binding)!=1:raise RuntimeError("Expected one built native SDK2 binding")
    artifacts=[POLICY,POLICY.with_name("manifest.json"),ROOT/"policies/local/core_24650/model_24650.pt",
        ROOT/"policies/server/upstream_19999/export/policy.pt",ROOT/"vendor/manifest.json",
        BUILD/"b2w_sdk2_watchdog",BUILD/"b2w_dds_fault_source",BUILD/"b2w_mujoco_bridge",native_binding[0]]
    manifest={"created_utc":utc_now(),"frozen_plan_sha256":sha256(plan_path),"executed_sha256":hashes,
        "artifact_sha256":{str(p.relative_to(ROOT)):sha256(p) for p in artifacts},"hardware_enabled":False,
        "python":sys.version,"torch":torch.__version__,"cpu_affinity":sorted(os.sched_getaffinity(0))}
    write_json(output/"preflight_manifest.json",manifest)
    sys.path.insert(0,str(BUILD));import b2w_sdk2_native as native
    from run_sim2sim import offline
    for pattern in ("test_sdk2_policy_runtime.py","test_dashboard_jobs.py","test_policy_contract.py","test_evaluation_policy.py","test_mujoco_model.py"):
        subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-q"],cwd=ROOT,check=True)
    subprocess.run([sys.executable,"scripts/vendor_materials.py","verify"],cwd=ROOT,check=True)
    offline(native,output)
    loads=[];gc_enabled=gc.isenabled();gc.disable();nominal_result=None;matrix=[];error=None
    try:
        for _ in range(plan["load"]["workers"]):
            loads.append(subprocess.Popen([sys.executable,"-c","x=1\nwhile True: x=(x*1664525+1013904223)&4294967295"],cwd=ROOT))
        nominal_result=nominal(output,plan,plan_path)
        matrix=fault_matrix(output,plan,plan_path)
    except BaseException as failure:
        error=repr(failure);raise
    finally:
        for process in loads:stop_process_tree(process)
        if gc_enabled:gc.enable()
        # Keep completed case evidence visible if a later case aborted the matrix.
        partial=output/"faults/result.json"
        if partial.exists():matrix=read_json(partial)["cases"]
        gates={folder:publishing_gate(output/folder/"publish.csv",plan) for folder in ("nominal","faults") if (output/folder/"publish.csv").exists()}
        result={"nominal":nominal_result,"fault_matrix_count":len(matrix),"fault_matrix_passed":bool(matrix) and all(r["passed"] for r in matrix),
            "publication_gates":gates,"error":error,"simulation_qualified":False,"hardware_enabled":False}
        result["passed"]=(not error and nominal_result and nominal_result["status"]=="passed" and len(matrix)==len(plan["cases"])*plan["repeats"]
                          and result["fault_matrix_passed"] and len(gates)==2 and all(g["passed"] for g in gates.values()))
        write_json(output/"summary.json",result)
        manifest["raw_sha256"]={p.relative_to(output).as_posix():sha256(p) for p in output.rglob("*") if p.is_file() and p.name!="manifest.json"}
        write_json(output/"manifest.json",manifest)
    print(json.dumps(result,indent=2))
    if not result["passed"]:raise SystemExit(2)


if __name__=="__main__":main()
