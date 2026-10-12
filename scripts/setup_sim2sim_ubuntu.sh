#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v uv >/dev/null
if [[ ! -x .venv/bin/python ]]; then uv venv --python 3.11 .venv; fi
uv pip install --python .venv/bin/python torch==2.8.0+cpu --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r requirements/sim2sim-ubuntu.lock.txt
.venv/bin/python scripts/cache_sim2sim_reference.py
.venv/bin/python scripts/vendor_materials.py verify
cmake -S sim2sim -B .runtime/sim2sim-build -G Ninja \
  -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DCMAKE_BUILD_TYPE=Release
cmake --build .runtime/sim2sim-build -j 4
