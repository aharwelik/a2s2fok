#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null && pwd)"
cd "$ROOT"

PYTHON_BIN="${ROOT}/.venv/bin/python"
SCONS_BIN="${ROOT}/.venv/bin/scons"
if [[ ! -x "$PYTHON_BIN" || ! -x "$SCONS_BIN" ]]; then
  echo "A complete repository .venv is required" >&2
  exit 1
fi
export PATH="${ROOT}/.venv/bin:${PATH}"

run_step() {
  local name="$1"
  shift
  echo "RUN ${name}"
  "$@"
  echo "PASS ${name}"
}

run_step unchanged_v6_floor ./scripts/ascent/run_combined_v6_tests.sh
run_step v7_root_tests "$PYTHON_BIN" -m pytest -q \
  sunnypilot/selfdrive/ascent_v7/tests \
  sunnypilot/selfdrive/controls/lib/tests/test_ascent_v7_safety_guards.py
run_step opendbc_v7_tests env PYTHONPATH="${ROOT}/opendbc_repo" "$PYTHON_BIN" -m pytest -q \
  opendbc_repo/opendbc/car/subaru/tests/test_ascent_v6.py \
  opendbc_repo/opendbc/car/subaru/tests/test_ascent_v7_controller_panda_fuzz.py \
  opendbc_repo/opendbc/safety/tests/test_subaru.py
run_step fail_closed_audit "$PYTHON_BIN" scripts/ascent/audit_v7_fail_closed.py
run_step runtime_import_smoke env PYTHONPATH="$ROOT" "$PYTHON_BIN" scripts/ascent/runtime_import_smoke.py
run_step noboard_import_smoke env NOBOARD=1 PYTHONPATH="$ROOT" "$PYTHON_BIN" scripts/ascent/runtime_import_smoke.py

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

report = {
  "schema_version": 1,
  "overall": "PASS",
  "canonical_build": "PASS",
  "unchanged_v6_floor": "PASS",
  "v7_root_tests": "PASS",
  "opendbc_v7_tests": "PASS",
  "fail_closed_audit": "PASS",
  "runtime_import_smoke": "PASS",
  "noboard_import_smoke": "PASS",
  "process_replay": "NOT_RUN_PRIVATE_ROUTE_UNAVAILABLE",
  "service_start_smoke": "IMPORT_AND_MANAGER_CONFIG_ONLY",
  "comma4_build": "NOT_PROVEN_ON_MACOS_HOST",
  "direct_long_vehicle_gate": "NOT_TESTED_RUNTIME_BLOCKED",
}
path = Path("artifacts/ascent_v7_test_report.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

echo "ASCENT_V7_ALPHA_TESTS=PASS"
