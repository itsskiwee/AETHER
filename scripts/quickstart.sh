#!/usr/bin/env bash
# AETHER quickstart for macOS and Linux. Run from anywhere:
#   bash scripts/quickstart.sh            # refresh real data
#   bash scripts/quickstart.sh --offline  # use the bundled snapshot
# Installs the backend and console, refreshes the real-data bundle (CelesTrak elements, NASA CMR),
# builds the console and serves it with the API on http://127.0.0.1:${PORT:-8080}.
set -euo pipefail
cd "$(dirname "$0")/.."
offline=''
[[ "${1:-}" == "--offline" ]] && offline='--offline'
port="${PORT:-8080}"

python_bin="$(command -v python3 || command -v python || true)"
[[ -n "$python_bin" ]] || { echo 'Install Python 3.12 or newer.' >&2; exit 1; }
"$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
  || { echo "Python 3.12 or newer is required (found $("$python_bin" --version))." >&2; exit 1; }
command -v npm >/dev/null || { echo 'Install Node.js 20 or newer.' >&2; exit 1; }

venv_python=backend/.venv/bin/python
if [[ ! -x "$venv_python" ]]; then
  echo 'Creating the Python environment (backend/.venv)...'
  "$python_bin" -m venv backend/.venv
fi
echo 'Installing the backend...'
"$venv_python" -m pip install --quiet --disable-pip-version-check -e './backend[geo,api]'
if [[ ! -d frontend/node_modules ]]; then
  echo 'Installing the console...'
  npm --prefix frontend ci --no-audit --no-fund
fi

# Byte-identical replay needs a fixed BLAS thread count (docs/validation-report.md section 7).
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$PWD/backend:$PWD"
if [[ -n "$offline" ]]; then echo 'Using the bundled real-data snapshot...'; else echo 'Refreshing real data (falls back to the bundled snapshot if offline)...'; fi
"$venv_python" -m scripts.build_globe_data $offline

echo 'Building the console...'
npm --prefix frontend run build

url="http://127.0.0.1:$port/?view=globe"
echo "Starting AETHER on $url (Ctrl+C to stop)"
( sleep 4; command -v open >/dev/null && open "$url" || command -v xdg-open >/dev/null && xdg-open "$url" ) >/dev/null 2>&1 &
exec "$venv_python" -m uvicorn scripts.hosted_app:app --host 127.0.0.1 --port "$port"
