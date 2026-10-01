"""Compatibility import; execution is owned by scripts/job_manager.py."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import job_manager as implementation
if __name__ == "__main__":
    implementation.main()
else:
    sys.modules[__name__] = implementation
