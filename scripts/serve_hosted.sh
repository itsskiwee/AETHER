#!/bin/sh
# Single-origin replay host; public feed refresh is explicitly enabled by the operator.
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${AETHER_PYTHON:-python}"
worker_pid=''
api_pid=''
cleanup() {
  trap - EXIT INT TERM
  [ -z "$api_pid" ] || kill "$api_pid" 2>/dev/null || true
  [ -z "$worker_pid" ] || kill "$worker_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
if [ "${AETHER_ENABLE_LIVE:-0}" = 1 ]; then
  "$python_bin" scripts/live_context.py --watch &
  worker_pid=$!
fi
"$python_bin" -m uvicorn scripts.hosted_app:app --host "${AETHER_HTTP_HOST:-127.0.0.1}" --port "${PORT:-8080}" &
api_pid=$!
wait "$api_pid"
