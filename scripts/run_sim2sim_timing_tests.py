"""Managed focused verification of GC scopes and timing instrumentation."""
import os,subprocess,sys,shutil
from pathlib import Path
from run_support import ROOT,managed_entrypoint,sha256,write_json,utc_now


def main():
    managed_entrypoint();out=Path(os.environ['B2W_JOB_DIR'])/'timing_tests';out.mkdir()
    files=['tests/test_sim2sim_timing.py','scripts/sim2sim_timing.py','scripts/sdk2_policy_runtime.py',
           'scripts/run_sim2sim_timing_tests.py','scripts/check_policy_contract.py']
    for name in files:
        p=out/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    process=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_sim2sim_timing.py','-v'],cwd=ROOT)
    write_json(out/'result.json',{'returncode':process.returncode,
                                  'pattern':'test_sim2sim_timing.py','passed':process.returncode==0})
    write_json(out/'manifest.json',{'created_utc':utc_now(),'executed_sha256':{n:sha256(ROOT/n) for n in files},
        'result_sha256':sha256(out/'result.json'),'hardware_enabled':False})
    raise SystemExit(process.returncode)


if __name__=='__main__':main()
