"""Managed Ubuntu S1 parity plus a bounded native SDK2/MuJoCo DDS diagnostic."""
from __future__ import annotations

import csv
import gc
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import threading
import time

from run_support import ROOT, managed_entrypoint, sha256, write_json, utc_now

BUILD = ROOT / ".runtime/sim2sim-build"
POLICY = ROOT / "policies/local/core_24650/export/policy.pt"


def percentiles(values):
    import numpy as np
    return dict(zip(("p50", "p95", "p99", "max"),
                    map(float, np.percentile(values, [50, 95, 99, 100])))) if values else None


def offline(native, output):
    import torch
    from check_policy_contract import fixtures, make_observation, action_targets
    from sdk2_policy_runtime import PolicyRuntime
    runtime = PolicyRuntime(POLICY)
    # Compare the retained actual training actor against its unchanged export.
    eager = torch.nn.Sequential(torch.nn.Linear(57, 512), torch.nn.ELU(),
        torch.nn.Linear(512, 256), torch.nn.ELU(), torch.nn.Linear(256, 128),
        torch.nn.ELU(), torch.nn.Linear(128, 16)).eval()
    checkpoint = torch.load(POLICY.parents[1] / "model_24650.pt", map_location="cpu", weights_only=True)
    eager.load_state_dict({k.removeprefix("actor."): v for k,v in
                          checkpoint["model_state_dict"].items() if k.startswith("actor.")})
    cfg = runtime.cfg
    records = []
    for label, state in fixtures(cfg).items():
        runtime.reset()
        runtime.previous_action = torch.tensor(state["previous_action"])
        result = runtime.step(state, state["commands"])
        observation = make_observation(state, cfg, isaac_semantics=True)
        torch.testing.assert_close(torch.tensor(result["observation"]), observation, atol=0, rtol=0)
        with torch.inference_mode():
            expected = eager(observation[None]).squeeze(0)
        torch.testing.assert_close(torch.tensor(result["raw_action"]), expected, atol=1e-5, rtol=0)
        targets = action_targets(expected, cfg, isaac_semantics=True)
        torch.testing.assert_close(torch.tensor(result["targets"]), targets, atol=1e-5, rtol=0)
        echo = native.echo(result["motors"])
        torch.testing.assert_close(torch.tensor(echo["motors"]), torch.tensor(result["motors"]), atol=0, rtol=0)
        assert echo["crc_valid"] and echo["head"] == [254, 239] and echo["level_flag"] == 255
        checksum=0xffffffff
        for word in echo["crc_words"]:
            for bit in range(31,-1,-1):
                high=bool(checksum & 0x80000000)
                checksum=(checksum<<1)&0xffffffff
                if high:checksum^=0x04c11db7
                if word & (1<<bit):checksum^=0x04c11db7
        assert checksum==echo["crc"]
        records.append({"name": label, "state": state, **result, "native_lowcmd": echo})
    generator = torch.Generator().manual_seed(20261012)
    observations = torch.rand((256, 57), generator=generator)*4-2
    with torch.inference_mode():
        error = (eager(observations)-runtime.policy(observations)).abs().max().item()
    assert error <= 1e-5
    # Deliberately exceed action clip: preserve raw history and clip targets.
    runtime.policy = lambda obs: torch.full((1,16), 200.0)
    neutral = fixtures(cfg)["neutral_reset"]
    runtime.reset(); clipped = runtime.step(neutral, [0,0,0])
    assert clipped["targets"][12:] == [100.0]*4 and runtime.previous_action.tolist()==[200.0]*16
    stopped = runtime.step(neutral, [0,0,0])
    assert stopped["observation"][41:] == [100.0]*16  # observation clip, not history mutation
    runtime.reset(); assert runtime.previous_action.tolist()==[0.0]*16
    write_json(output / "sdk2_io_parity.json", {
        "status":"passed", "scope":"actual checkpoint/export plus native SDK2 LowCmd fields/CRC",
        "hardware_enabled":False, "created_utc":utc_now(), "fixture_count":len(records),
        "random_count":256, "max_actor_error":error, "tolerance":1e-5,
        "clipping_raw_history_reset_stop":"passed", "fixtures":records})


def scene(output, cfg):
    import mujoco
    from mujoco_model import DEFAULT_XML, initialize, validate_model_contract
    model = mujoco.MjModel.from_xml_path(str(DEFAULT_XML))
    contract = validate_model_contract(model,cfg)
    data=mujoco.MjData(model); initialize(model,data,cfg,{"kind":"flat"})
    spec=mujoco.MjSpec.from_file(str(DEFAULT_XML))
    spec.meshdir=str((DEFAULT_XML.parent/spec.meshdir).resolve())
    spec.add_key(name="policy_reset", qpos=data.qpos.tolist(), qvel=data.qvel.tolist())
    spec.add_numeric(name="policy_velocity_limits", data=cfg["isaac_velocity_limits"])
    # MjSpec saves asset paths relative to the original asset directory.
    path=output/"scene.xml"; path.write_text(spec.to_xml())
    return path,contract


def dds_run(native, output, duration=20.0):
    import torch
    from sdk2_policy_runtime import PolicyRuntime, disabled_motors
    runtime=PolicyRuntime(POLICY)
    from check_policy_contract import fixtures
    neutral=fixtures(runtime.cfg)["neutral_reset"]
    for _ in range(8):runtime.step(neutral,[0,0,0])
    runtime.reset()
    xml,model_contract=scene(output,runtime.cfg)
    transport=native.Transport(1,"lo")
    samples=[]; publishes=[]; fault_events=[]
    lock=threading.Lock(); stop=threading.Event()
    target=disabled_motors(); target_time=None; command_time=None; tick=None; tick_time=None
    activated=False
    failed_steps=[]
    fault_tests=[]; nominal_fault=None; nominal_returncode=None
    # DDS already discovered before physics begins; initial LowCmd holds reset pose.
    from sdk2_policy_runtime import lowcmd_motors
    initial=lowcmd_motors(runtime.cfg["default_dof_pos"],runtime.cfg)
    for _ in range(20): transport.publish(initial); time.sleep(.002)

    def publisher():
        nonlocal tick,tick_time
        deadline=time.monotonic()
        while not stop.is_set():
            now=time.monotonic(); state=transport.state()
            with lock:
                if activated:
                    if not state.get("crc_valid", True):runtime.latch("invalid_state_crc")
                    if state.get("count") and (tick is None or state["tick"]>tick):
                        tick=state["tick"]; tick_time=now
                    state_age=max(state.get("age_s",math.inf), now-(tick_time or now))
                    runtime.guard(state_age, now-command_time, now-target_time)
                    if runtime.fault and not fault_events:
                        fault_events.append({"reason":runtime.fault,"detected_monotonic":now})
                    motors=disabled_motors() if runtime.fault else target
                else:
                    motors=initial
                start=time.monotonic(); ok=transport.publish(motors)
                publishes.append({"start":start,"end":time.monotonic(),"ok":ok,"fault":runtime.fault})
                if not ok: runtime.latch("publish_failed")
            deadline+=.002
            stop.wait(max(0,deadline-time.monotonic()))

    # Bounded traces contain no reference cycles. Keep cyclic collection out of
    # the deadline interval; refcount reclamation remains active.
    gc_was_enabled=gc.isenabled();gc.disable()
    thread=threading.Thread(target=publisher,daemon=True); thread.start()
    bridge=None
    try:
        with (output/"bridge.stdout.log").open("w") as stdout, (output/"bridge.stderr.log").open("w") as stderr:
            bridge=subprocess.Popen([str(BUILD/"b2w_mujoco_bridge"),str(xml),str(duration+1),
                str(output/"physics.csv")],stdout=stdout,stderr=stderr,cwd=ROOT)
            startup=time.monotonic()+5
            while transport.state().get("count",0)==0:
                if bridge.poll() is not None: raise RuntimeError("Bridge exited during discovery")
                if time.monotonic()>startup: raise RuntimeError("DDS discovery timeout")
                time.sleep(.01)
            origin=time.monotonic(); deadline=origin
            while time.monotonic()-origin<duration and bridge.poll() is None:
                now=time.monotonic(); elapsed=now-origin
                # zero -> vx -> zero -> lateral -> zero -> yaw -> continuous zero.
                command = ([.2,0,0] if 2<=elapsed<4 else [0,.2,0] if 5<=elapsed<6
                           else [0,0,.2] if 7<=elapsed<8 else [0,0,0])
                state=transport.state()
                with lock:
                    command_time=now
                    if runtime.fault: break
                start=time.monotonic()
                try:
                    result=runtime.step(state,command)
                except (ValueError,RuntimeError) as error:
                    with lock:
                        runtime.latch(error)
                        failed_steps.append({"elapsed_s":elapsed,"inference_start":start,
                            "inference_end":time.monotonic(),"reason":runtime.fault})
                    break
                end=time.monotonic()
                with lock:
                    if end-start>runtime.inference_budget: runtime.latch("inference_timeout")
                    if runtime.fault:
                        failed_steps.append({"elapsed_s":elapsed,"inference_start":start,
                            "inference_end":end,"reason":runtime.fault})
                        if not fault_events:fault_events.append({"reason":runtime.fault,"detected_monotonic":end})
                        break
                    target=result["motors"]; target_time=end; activated=True
                samples.append({"elapsed_s":elapsed,"received_state":state,"command":command,
                    "inference_start":start,"inference_end":end,**result})
                deadline+=.02
                time.sleep(max(0,deadline-time.monotonic()))
            nominal_fault=runtime.fault
            # A real publisher disconnect, rather than modifying a state-age fixture.
            if len(samples)>=duration*45 and not nominal_fault and bridge.poll() is None:
                refreshed=runtime.step(transport.state(),[0,0,0])
                with lock:
                    command_time=time.monotonic()
                    target=refreshed["motors"];target_time=command_time
                write_json(output/"disconnect_setup.json",refreshed)
                injected=time.monotonic();bridge.terminate();bridge.wait(timeout=10)
                nominal_returncode=bridge.returncode
                while not runtime.fault and time.monotonic()-injected<.2:time.sleep(.001)
                detected=time.monotonic()
                with lock:
                    event=fault_events[-1] if fault_events else {}
                    disabled=any(p["fault"]=="stale_state" for p in publishes)
                fault_tests.append({"case":"DDS publisher disconnect", "expected":"stale_state",
                    "observed":runtime.fault,"latency_s":event.get("detected_monotonic",detected)-injected,
                    "disabled_command_published":disabled,"passed":runtime.fault=="stale_state" and disabled})
                old_count=transport.state()["count"]
                bridge=subprocess.Popen([str(BUILD/"b2w_mujoco_bridge"),str(xml),"1",
                    str(output/"restart_physics.csv")],stdout=stdout,stderr=stderr,cwd=ROOT)
                restart=time.monotonic()
                while transport.state()["count"]==old_count and bridge.poll() is None and time.monotonic()-restart<5:
                    time.sleep(.005)
                restarted=transport.state()["count"]>old_count
                fault_tests.append({"case":"publisher restart without explicit recovery",
                    "state_received":restarted,"fault_remains_latched":runtime.fault=="stale_state",
                    "passed":restarted and runtime.fault=="stale_state"})
    finally:
        stop.set();thread.join(timeout=2)
        transport.publish(disabled_motors())
        if bridge is not None and bridge.poll() is None:
            bridge.terminate();bridge.wait(timeout=10)
        if gc_was_enabled:gc.enable()
    with (output/"policy.jsonl").open("w") as stream:
        for item in samples:stream.write(json.dumps(item,allow_nan=False)+"\n")
    with (output/"publish.jsonl").open("w") as stream:
        for item in publishes:stream.write(json.dumps(item,allow_nan=False)+"\n")
    rows=list(csv.DictReader((output/"physics.csv").open()))
    # Actual tilt comes from the body Z axis and excludes yaw.
    tilt=[math.acos(max(-1,min(1,1-2*(float(row["qx"])**2+float(row["qy"])**2)))) for row in rows]
    returncode=nominal_returncode if nominal_returncode is not None else bridge.returncode
    result={"status":"transport_smoke_passed" if len(samples)>=duration*45 and not nominal_fault and returncode==0 and all(f["passed"] for f in fault_tests) else "diagnostic_failed",
        "policy_steps":len(samples),"publish_count":len(publishes),"fault":nominal_fault,
        "fault_events":fault_events,"bridge_returncode":returncode,"model_contract":model_contract,
        "fault_tests":fault_tests,"fault_after_injection":runtime.fault,
        "failed_steps":failed_steps,"cyclic_gc_disabled_in_bounded_loop":True,
        "inference_s":percentiles([x["inference_end"]-x["inference_start"] for x in samples+failed_steps]),
        "state_age_s":percentiles([x["received_state"]["age_s"] for x in samples]),
        "publish_interval_s":percentiles([b["start"]-a["start"] for a,b in zip(publishes,publishes[1:])]),
        "max_tilt_rad":max(tilt,default=0),"min_height_m":min((float(r["z"]) for r in rows),default=0),
        "physics_samples":len(rows),"forbidden_contact_peak_n":max((float(r["forbidden_force_n"]) for r in rows),default=0),
        "min_joint_margin_rad":min((float(r["joint_margin_rad"]) for r in rows),default=0),
        "velocity_util_peak":max((float(r["velocity_util"]) for r in rows),default=0),
        "simulation_qualified":False,"hardware_enabled":False,
        "open_gates":["full-rate safety and joint/drive gates", "fault injection DDS matrix",
                      "nominal/variation envelope", "Isaac comparison on this host", "actuator physics parity"]}
    write_json(output/"dds_smoke.json",result)
    write_json(output/"dds_fault_injection.json",{"live_dds":fault_tests,
        "offline_fault_tests":"tests/test_sdk2_policy_runtime.py",
        "open":["packet loss/reorder", "native watchdog under load", "inference hangs", "operator stop",
                 "saturation handling", "NaN/Inf over DDS"],"hardware_enabled":False})
    return result


def main():
    managed_entrypoint()
    def cancelled(signum, frame):
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled)
    signal.signal(signal.SIGINT,cancelled)
    output=Path(os.environ["B2W_JOB_DIR"])/"sim2sim";output.mkdir(parents=True,exist_ok=True)
    import torch
    torch.set_num_threads(1)
    sys.path.insert(0,str(BUILD))
    import b2w_sdk2_native as native
    for name in ("test_sdk2_policy_runtime.py","test_dashboard_jobs.py",
                 "test_policy_contract.py","test_evaluation_policy.py","test_mujoco_model.py"):
        subprocess.run([sys.executable,"-m","unittest","discover","-s","tests",
            "-p",name,"-q"],cwd=ROOT,check=True)
    offline(native,output)
    result=dds_run(native,output)
    paths=[POLICY,ROOT/"policies/server/upstream_19999/export/policy.pt",
        ROOT/"policies/local/core_24650/model_24650.pt",BUILD/"b2w_mujoco_bridge",Path(native.__file__),
        ROOT/"vendor/manifest.json",ROOT/"scripts/sdk2_policy_runtime.py",ROOT/"scripts/run_sim2sim.py",
        ROOT/"sim2sim/bridge.cpp",ROOT/"sim2sim/sdk2_transport.cpp",ROOT/"sim2sim/CMakeLists.txt"]
    paths.extend(ROOT/p for p in ("scripts/run_support.py","scripts/job_worker.py",
        "scripts/job_manager.py","scripts/check_policy_contract.py","scripts/evaluation_policy.py",
        "scripts/mujoco_model.py","tests/test_sdk2_policy_runtime.py",
        "vendor/unitree_mujoco/simulate/src/unitree_sdk2_bridge.h",
        "vendor/unitree_sdk2/lib/x86_64/libunitree_sdk2.a",
        "vendor/unitree_sdk2/thirdparty/lib/x86_64/libddsc.so",
        "vendor/unitree_sdk2/thirdparty/lib/x86_64/libddscxx.so"))
    write_json(output/"manifest.json",{"created_utc":utc_now(),"platform":platform.platform(),
        "python":sys.version,"torch":torch.__version__,"dds_domain":1,"interface":"lo",
        "hardware_enabled":False,"policy_id":"core_24650", "status":result["status"],
        "executed_sha256":{str(p.relative_to(ROOT)):sha256(p) for p in paths},
        "raw_sha256":{p.name:sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(result,indent=2))
    if result["status"]!="transport_smoke_passed":raise SystemExit(2)


if __name__=="__main__":main()
