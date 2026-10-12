"""Cache one SHA-checked upstream Isaac Lab method source; no package install."""
from pathlib import Path
import urllib.request
import hashlib

from sim2sim_physics_audit import REFERENCE, REFERENCE_COMMIT, REFERENCE_SHA256
from run_support import sha256


def main():
    if REFERENCE.exists():
        if sha256(REFERENCE)!=REFERENCE_SHA256:raise ValueError("Existing reference SHA mismatch")
    else:
        url=f"https://raw.githubusercontent.com/isaac-sim/IsaacLab/{REFERENCE_COMMIT}/source/isaaclab/isaaclab/actuators/actuator_pd.py"
        content=urllib.request.urlopen(url,timeout=30).read()
        if hashlib.sha256(content).hexdigest()!=REFERENCE_SHA256:raise ValueError("Downloaded reference SHA mismatch")
        REFERENCE.parent.mkdir(parents=True,exist_ok=True)
        temporary=REFERENCE.with_suffix(".partial");temporary.write_bytes(content);temporary.replace(REFERENCE)
    print(REFERENCE,REFERENCE_SHA256)


if __name__=="__main__":main()
