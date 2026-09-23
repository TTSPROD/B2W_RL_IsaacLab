#!/bin/bash
set -uo pipefail
exec timeout --signal=TERM --kill-after=60s 15h python /run-output/code/control.py > /run-output/controller.log 2>&1
