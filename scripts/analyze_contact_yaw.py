"""Offline matched-window diagnosis of completed contact-weight development experiment."""
import json
import numpy as np
from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import sha256,utc_now,write_json
from yaw_trace_analysis import load_trace,mesh_vertices,window_metrics

def read(p):return json.loads(p.read_text(encoding="utf-8"))
def stats(x):return dict(zip(("min","median","max"),map(float,(np.min(x),np.median(x),np.max(x)))))

def main():
    job_path=ROOT/"logs/diagnostics/contact3x_yaw_diagnostics_20260919/job.json"
    job=read(job_path)
    assert job["status"]=="completed" and len(job["stages"])==4
    assert all(s["original_results_exactly_reproduced"] and s["external_exit_code"]==0 for s in job["stages"].values())
    old=ROOT/"logs/qualification/staged_yaw_diagnostics_20260918"
    new=ROOT/"logs/qualification/contact3x_yaw_diagnostics_20260919"
    out={"created_utc":utc_now(),"trace_job":str(job_path.relative_to(ROOT)),"trace_job_sha256":sha256(job_path),"exactly_reproduced_replays":4,"profiles":{}}
    for profile,seed in (("nominal",20261201),("bounded_v1",20261202)):
        reports={a:read(old/f"{a}_{profile}_{seed}.json") for a in ("seed49","seed50","seed51","reference")}
        reports.update({a:read(new/f"{a}_{profile}_{seed}.json") for a in ("seed50_contact3x","seed51_contact3x")})
        traces={a:load_trace(r) for a,r in reports.items()}
        geometry={n:mesh_vertices(n)[0] for n in traces["reference"][1]["body_names"]}
        for r in reports.values():
            assert r["cases"]==reports["reference"]["cases"]
            assert r["physical_evidence"]["properties_sha256"]==reports["reference"]["physical_evidence"]["properties_sha256"]
        data={"report_sha256":{a:sha256((new if "contact3x" in a else old)/f"{a}_{profile}_{seed}.json") for a in reports},"yaw_height_quantiles_m":{},"matched_windows":[]}
        for a,(arr,meta) in traces.items():
            mask=arr["time_s"]>=2
            data["yaw_height_quantiles_m"][a]=dict(zip(("min","p05","median","p95","max"),np.quantile(arr["root_pos"][mask,:,2],[0,.05,.5,.95,1]).tolist()))
        for f in reports["seed50_contact3x"]["first_failures"]:
            end=f["time_s"];start=end-.5
            row={"failure":f,"window_s":[start,end],"policies":{}}
            for a,(arr,meta) in traces.items():
                e=meta["env_ids"].index(f["env"]);mask=(arr["time_s"]>=start)&(arr["time_s"]<end-1e-7)
                m=window_metrics(arr,meta,f["env"],start,end,geometry)
                m["root_height_m"]=stats(arr["root_pos"][mask,e,2])
                m["tilt_deg"]=stats(np.degrees(np.arccos(np.clip(-arr["projected_gravity"][mask,e,2],-1,1))))
                m["already_failed_before_window_end"]=any(x["env"]==f["env"] and x["time_s"]<end for x in reports[a]["first_failures"])
                low=(arr["time_s"]>=2)&(arr["time_s"]<end)&(arr["root_pos"][:,e,2]<.55)
                m["first_height_below_055_s_after_2s"]=float(arr["time_s"][low][0]) if low.any() else None
                row["policies"][a]=m
            data["matched_windows"].append(row)
        out["profiles"][profile]=data
    rows=[r for p in out["profiles"].values() for r in p["matched_windows"]];assert len(rows)==14
    out["findings"]={"remaining_failures":14,"prefailure_window_s":.5,
      "windows_with_leg_clipping":sum(r["policies"]["seed50_contact3x"]["any_leg_clipping_fraction"]>0 for r in rows),
      "prefailure_median_height_m":{a:stats([r["policies"][a]["root_height_m"]["median"] for r in rows]) for a in rows[0]["policies"]},
      "seconds_below_055_before_contact":stats([r["failure"]["time_s"]-r["policies"]["seed50_contact3x"]["first_height_below_055_s_after_2s"] for r in rows])}
    out["interpretation"]="Low root height precedes contact. Correlation supports a height-reward experiment, not unique causal attribution. No explicit leg clipping in the measured windows."
    out["limitations"]=["Disclosed development cases and selected failing training seeds; no independent acceptance.","Other policies may already have failed; per-window flag recorded.","Source-mesh clearance and bottom-point slip are proxies, not cooked PhysX collider/contact-point evidence.","Height quantiles include post-failure samples; matched windows isolate the half-second before first failure of seed50_contact3x."]
    out["next_experiment"]="contact3x_height_weight0_vs_minus10_target060"
    write_json(ROOT/"docs/results/2026-09-19-contact-yaw-diagnosis.json",out)
    print(json.dumps(out["findings"],indent=2))
if __name__=="__main__":main()
