#!/usr/bin/env bash
# Combined offline release checks on one revision (REL-01). Writes logs to $1 (default
# runs/release-checks/<short-rev>/). Live, no-mock browser checks need a running
# serve-demo.sh and are listed at the end of docs/lanes/completion-claude-1.md.
set -uo pipefail
cd "$(dirname "$0")/.."
rev="$(git rev-parse HEAD)"
out="${1:-runs/release-checks/${rev:0:7}}"
mkdir -p "$out"
python_bin="${AETHER_PYTHON:-$PWD/backend/.venv/bin/python}"
ruff_bin="${AETHER_RUFF:-$(dirname "$python_bin")/ruff}"
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
status=0
step() {
  local name="$1"; shift
  local started; started=$(date +%s)
  if "$@" >"$out/$name.log" 2>&1; then result=PASS; else result=FAIL; status=1; fi
  printf '%s %s %ss\n' "$result" "$name" "$(( $(date +%s) - started ))" | tee -a "$out/summary.txt"
}
{ echo "revision $rev"; echo "dirty: $(git status --porcelain | wc -l) paths"; date -u +%FT%TZ; } > "$out/summary.txt"
step ruff-check bash -c "cd backend && '$ruff_bin' check ."
step ruff-format bash -c "cd backend && '$ruff_bin' format --check ."
step pytest bash -c "cd backend && '$python_bin' -m pytest -q -p no:cacheprovider -W ignore::DeprecationWarning --junitxml='$PWD/$out/pytest-junit.xml'"
step validate-base "$python_bin" -m aether.cli validate --config configs/base.yaml
step validate-demo "$python_bin" -m aether.cli validate --config configs/demo.yaml
step frontend-build npm --prefix frontend run build
step browser-mocked bash -c "cd frontend && CI=1 AETHER_TEST_PORT=${AETHER_TEST_PORT:-4273} npx playwright test"
"$python_bin" - "$out/pytest-junit.xml" <<'PY' | tee -a "$out/summary.txt"
import sys, xml.etree.ElementTree as ET
try:
    root = ET.parse(sys.argv[1]).getroot()
except (OSError, ET.ParseError) as exc:
    print(f"pytest junit unavailable: {exc}")
    raise SystemExit(0)
suites = [root] if root.tag == "testsuite" else list(root)
tot = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
print("pytest", tot)
PY
exit $status
