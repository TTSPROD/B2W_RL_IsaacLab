"""Minimal headless Isaac Sim startup check for the dedicated B2W runtime."""

import sys
from pathlib import Path

if any("B2W_RL_IsaacSim" in path for path in sys.path):
    raise RuntimeError("A previous B2W project is on sys.path")

from isaaclab.app import AppLauncher

portable_root = Path(__file__).resolve().parents[1] / ".cache" / "kit"
portable_root.mkdir(parents=True, exist_ok=True)
extensions = Path(__file__).resolve().parents[1] / ".runtime" / "extensions"
sys.argv.extend(["--portable-root", str(portable_root), "--ext-folder", str(extensions)])
launcher = AppLauncher({"headless": True})
print("ISAAC_SIM_HEADLESS_READY", flush=True)
launcher.app.close()
