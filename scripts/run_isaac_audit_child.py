"""Isolated native Isaac runtime entrypoint for the allowlisted live audit only."""
from pathlib import Path
import os
import runpy
import sys

from run_support import ROOT,managed_entrypoint,read_json

managed_entrypoint()
runtime=read_json(ROOT/".runtime/isaac-ubuntu-runtime.json")
if not runtime.get("eula_accepted"):raise RuntimeError("Explicit NVIDIA EULA consent required")
if runtime.get("hardware_enabled") or runtime["isaaclab_commit"]!="37ddf626871758333d6ed89cf64ad702aef127d0":
    raise RuntimeError("Wrong native Isaac audit runtime")
if "--protocol-module" not in sys.argv or sys.argv[sys.argv.index("--protocol-module")+1]!="sim2sim_isaac_protocol":
    raise ValueError("Only the frozen live-audit protocol is allowed")
os.environ["OMNI_KIT_ACCEPT_EULA"]="YES"
libraries=ROOT/".runtime/isaac-native-libs/usr/lib/x86_64-linux-gnu"
if libraries.is_dir():
    # LD_LIBRARY_PATH must be present before the interpreter starts to affect
    # plugin dependencies; the parent supplies it. Fail rather than load globals.
    if str(libraries) not in os.environ.get("LD_LIBRARY_PATH","").split(":"):
        raise RuntimeError("Project-local native library path missing from child environment")
directory=Path(os.environ["B2W_JOB_DIR"])/"isaac_audit/kit-config"
directory.mkdir(parents=True,exist_ok=True)
roots={"cache_root":ROOT/".cache/isaac-kit", "data_root":ROOT/".cache/isaac-kit-data",
       "logs_root":Path(os.environ["B2W_JOB_DIR"])/"isaac_audit/kit-logs"}
for path in roots.values():path.mkdir(parents=True,exist_ok=True)
(directory/"omniverse.toml").write_text("[paths]\n"+"\n".join(f'{key} = "{value}"' for key,value in roots.items())+"\n")
os.environ["OMNI_CONFIG_PATH"]=str(directory)
sys.argv[0]=str(ROOT/"scripts/eval_fullcycle_terrain.py")
runpy.run_path(sys.argv[0],run_name="__main__")
