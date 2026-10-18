#!/usr/bin/env bash
# Generate, replay, validate, export, and compare actual offline simulations.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${AETHER_PYTHON:-$PWD/backend/.venv/bin/python}"
out_dir="${1:-runs/demo}"
if [[ ! -x "$python_bin" ]]; then
  echo 'Create backend/.venv and install .[dev,geo,api]; see docs/demo-console.md.' >&2
  exit 1
fi
printf '%s\n' 'SIMULATED MISSION · offline replay · configs/demo.yaml · seed 1000 · sources placed from pinned EMIT V002 history'
"$python_bin" -m aether.cli simulate --config configs/demo.yaml \
  --policies largest_first,adaptive_eig --seed 1000 --output-dir "$out_dir"
printf '%s\n' 'Repeating both policies to verify byte-identical replay…'
"$python_bin" -m aether.cli simulate --config configs/demo.yaml \
  --policies largest_first,adaptive_eig --seed 1000 --output-dir "$out_dir/replay"
for run_file in "$out_dir"/*/run.json; do
  run_id="$(basename "$(dirname "$run_file")")"
  "$python_bin" -m aether.cli export --run-dir "$out_dir" --run-id "$run_id" \
    --output "$out_dir/$run_id.zip"
  # Reload the archive and re-check every input hash against the record and repository.
  "$python_bin" -m aether.cli verify-export --archive "$out_dir/$run_id.zip"
done
"$python_bin" scripts/verify_demo.py "$out_dir"
printf '%s\n' 'Preliminary development comparison · configs/base.yaml · seeds 1000,1001 · insufficient samples'
"$python_bin" -m aether.evaluation.development --output-dir "$out_dir/benchmark" --seeds 1000,1001
printf 'Artifacts ready: %s\nStart console: bash scripts/serve-demo.sh %s\n' "$out_dir" "$out_dir"
