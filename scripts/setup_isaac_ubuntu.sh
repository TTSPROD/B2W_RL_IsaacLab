#!/usr/bin/env bash
# Project-local installation only; no simulation, training, or hardware actions.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ "${1:-}" != "--accept-eula" ]]; then
  echo 'Requires explicit --accept-eula for NVIDIA Omniverse license consent.' >&2
  exit 2
fi
export UV_CACHE_DIR="$PWD/.cache/uv-isaac"
export PIP_CACHE_DIR="$PWD/.cache/pip-isaac"
export TMPDIR="$PWD/.cache/tmp-isaac"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR" logs/setup/isaac-ubuntu .runtime/extensions
task_python="$PWD/.runtime/isaaclab-ubuntu-venv/bin/python"
task_lab="$PWD/.runtime/IsaacLab"
task_commit=37ddf626871758333d6ed89cf64ad702aef127d0
task_constraints=(--constraint requirements/isaac-ubuntu-constraints.txt)
if [[ -f requirements/isaac-ubuntu.lock.txt ]]; then
  task_constraints+=(--constraint requirements/isaac-ubuntu.lock.txt)
fi
if [[ ! -x "$task_python" ]]; then
  uv venv --python .venv/bin/python --seed .runtime/isaaclab-ubuntu-venv
fi
if [[ ! -d "$task_lab" ]]; then
  git clone --depth 1 --branch v2.3.2 https://github.com/isaac-sim/IsaacLab.git "$task_lab"
fi
[[ "$(git -C "$task_lab" rev-parse HEAD)" == "$task_commit" ]]
.venv/bin/python - <<'PY'
from pathlib import Path
import subprocess
path=Path('.runtime/IsaacLab/source/isaaclab/setup.py')
original=subprocess.check_output(['git','-C','.runtime/IsaacLab','show','HEAD:source/isaaclab/setup.py'])
patched=original.replace(b'"starlette==0.49.1"',b'"starlette==0.45.3"')
if path.read_bytes() not in (original,patched):raise ValueError('Unexpected Isaac Lab metadata edits')
path.write_bytes(patched)
PY
"$task_python" -m pip install "${task_constraints[@]}" \
  setuptools wheel toml packaging
"$task_python" -m pip install --no-build-isolation --disable-pip-version-check \
  "${task_constraints[@]}" \
  --extra-index-url https://pypi.nvidia.com --extra-index-url https://download.pytorch.org/whl/cu128 \
  'isaacsim[all,extscache]==5.1.0' 'torch==2.7.0+cu128' 'torchvision==0.22.0+cu128' \
  -e .runtime/IsaacLab/source/isaaclab -e .runtime/IsaacLab/source/isaaclab_assets \
  -e .runtime/IsaacLab/source/isaaclab_tasks -e '.runtime/IsaacLab/source/isaaclab_rl[rsl-rl]' \
  tensordict psutil colorama xacrodoc matplotlib \
  --log logs/setup/isaac-ubuntu/pip-install.log
"$task_python" -m pip check
.venv/bin/python scripts/prepare_isaac_native_libs.py
"$task_python" -m pip freeze --all > logs/setup/isaac-ubuntu/pip-freeze.txt
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0,'scripts')
from run_support import write_json,sha256,utc_now
write_json('.runtime/isaac-ubuntu-runtime.json',{
    'isaaclab_commit':'37ddf626871758333d6ed89cf64ad702aef127d0',
    'python':'.runtime/isaaclab-ubuntu-venv/bin/python',
    'metadata_patch':'requirements/isaaclab-sim51-metadata.patch',
    'runtime_setup_sha256':sha256('.runtime/IsaacLab/source/isaaclab/setup.py'),
    'constraints_sha256':sha256('requirements/isaac-ubuntu-constraints.txt'),
    'freeze_sha256':sha256('logs/setup/isaac-ubuntu/pip-freeze.txt'),
    'eula_accepted':True,'eula_authorization':'Explicit --accept-eula by operator',
    'installed_utc':utc_now(),'simulation_tested':False,'hardware_enabled':False})
PY
