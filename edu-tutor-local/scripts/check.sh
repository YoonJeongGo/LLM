#!/usr/bin/env sh
# WSL/Linux route; not validated on this Windows host.
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src"
.venv/bin/python -m pytest -q
cd web
npm run build
npm test -- --run
