#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${AETHER_PYTHON:-${repo_root}/backend/.venv/bin/python}"
if [[ ! -x "${python_bin}" ]]; then
  python_bin="python3"
fi

cd "${repo_root}/backend"
exec "${python_bin}" -m aether.orbit.ephemeris "$@"
