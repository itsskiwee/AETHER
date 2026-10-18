#!/usr/bin/env bash
# Serve actual offline run artifacts and the production console. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
repo_root="$PWD"
demo_root="${1:-runs/demo}"
if [[ ! -d "$demo_root" ]]; then
  echo "Run archive not found: $demo_root. Generate it with bash scripts/demo.sh first." >&2
  exit 1
fi
export AETHER_RUNS_DIR="$(cd "$demo_root" && pwd)"
export AETHER_BENCHMARK_DIR="${AETHER_BENCHMARK_DIR:-$AETHER_RUNS_DIR/benchmark}"
export PYTHONPATH="$repo_root/backend${PYTHONPATH:+:$PYTHONPATH}"
export AETHER_API_PORT="${AETHER_API_PORT:-8000}"
console_port="${AETHER_CONSOLE_PORT:-4173}"
python_bin="${AETHER_PYTHON:-$repo_root/backend/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "Python environment missing. See docs/demo-console.md for setup, or set AETHER_PYTHON." >&2
  exit 1
fi
if [[ ! -x frontend/node_modules/.bin/vite ]]; then
  echo "Frontend dependencies missing. Run: cd frontend && npm ci" >&2
  exit 1
fi
"$python_bin" -c 'import aether.api, uvicorn'
"$python_bin" - <<'PY'
import os
from pathlib import Path

from aether.contracts import RunRecord

root = Path(os.environ["AETHER_RUNS_DIR"])
runs = [RunRecord.model_validate_json(path.read_text()) for path in sorted(root.glob("*/run.json"))]
if not runs:
    raise SystemExit("No actual run.json artifacts found. Generate the demo before serving it.")
for run in runs:
    if len(run.validations) != len(run.plans) or any(not record.ok for record in run.validations):
        raise SystemExit(f"Independent validation is incomplete or failed: {run.run_id}")
print(f"Reloaded {len(runs)} run artifacts with independent schedule validations.")
PY
npm --prefix frontend run build

api_pid=''
console_pid=''
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$console_pid" ]] || kill "$console_pid" 2>/dev/null || true
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
"$python_bin" -m uvicorn aether.api:app --host 127.0.0.1 --port "$AETHER_API_PORT" &
api_pid=$!
# Call Vite directly so cleanup owns the server process, not an npm wrapper.
(cd frontend && exec node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port "$console_port" --strictPort) &
console_pid=$!
echo "SIMULATED MISSION · offline replay"
echo "Console: http://127.0.0.1:$console_port · API: http://127.0.0.1:$AETHER_API_PORT/api/docs"
echo "Run archive: $AETHER_RUNS_DIR"
echo "Evaluator output: $AETHER_BENCHMARK_DIR"
echo "Press Ctrl-C to stop both servers."
wait -n "$api_pid" "$console_pid"
