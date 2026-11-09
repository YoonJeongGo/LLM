#!/usr/bin/env sh
# WSL/Linux route; not validated on this Windows host.
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src"
export HF_HUB_DISABLE_TELEMETRY=1
exec .venv/bin/python -m edu_tutor serve
