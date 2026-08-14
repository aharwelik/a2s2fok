#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null && pwd)"
cd "$ROOT"

PYTHON_BIN="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
SCONS_BIN="${ROOT}/.venv/bin/scons"
if [[ ! -x "$SCONS_BIN" ]]; then
  SCONS_BIN="scons"
fi

RESULT_DIR="${ROOT}/artifacts"
mkdir -p "$RESULT_DIR"

run_step() {
  local name="$1"
  shift
  echo "RUN ${name}"
  "$@"
  echo "PASS ${name}"
}

run_step static_isolation "$PYTHON_BIN" scripts/ascent/audit_combined_v6_isolation.py
run_step canonical_build "$SCONS_BIN" -j"${SCONS_JOBS:-8}"
run_step stop_obstacle_tests "$PYTHON_BIN" -m pytest -q sunnypilot/selfdrive/controls/lib/stop_obstacle/tests
run_step overtake_advisor_tests "$PYTHON_BIN" -m pytest -q sunnypilot/selfdrive/controls/lib/overtake_advisor/tests
run_step map_regression "$PYTHON_BIN" -m pytest -q sunnypilot/selfdrive/controls/lib/smart_cruise_control/tests/test_map_controller.py
run_step button_tracker "$PYTHON_BIN" -m pytest -q sunnypilot/selfdrive/selfdrived/tests/test_button_state_tracker.py
run_step speed_limit_button "$PYTHON_BIN" -m pytest -q sunnypilot/selfdrive/controls/lib/speed_limit/tests/test_speed_limit_assist.py
run_step lane_change_state "$PYTHON_BIN" -m pytest -q \
  sunnypilot/selfdrive/controls/lib/tests/test_auto_lane_change.py \
  sunnypilot/selfdrive/controls/lib/tests/test_lane_turn_desire.py
run_step ui_import "$PYTHON_BIN" - <<'PY'
from openpilot.sunnypilot.selfdrive.ascent_v6.status import DEVELOPMENT_LABEL, LONGITUDINAL_OWNER
assert DEVELOPMENT_LABEL == "ASCENT V6 TEST — STOCK EYESIGHT BRAKING"
assert LONGITUDINAL_OWNER == "STOCK_EYESIGHT"
PY
run_step comma4_mici_import "$PYTHON_BIN" - <<'PY'
import importlib

for module in (
  "openpilot.selfdrive.ui.mici.layouts.main",
  "openpilot.selfdrive.ui.sunnypilot.mici.onroad.hud_renderer",
  "openpilot.system.version",
):
  importlib.import_module(module)
PY

cat > "${RESULT_DIR}/ascent_v6_test_report.json" <<'JSON'
{
  "combined_v6_runner": "passed",
  "canonical_build": "passed",
  "comma4_mici_import": "passed",
  "deterministic_root_steps": [
    "static_isolation",
    "stop_obstacle_tests",
    "overtake_advisor_tests",
    "map_regression",
    "button_tracker",
    "speed_limit_button",
    "lane_change_state",
    "ui_import",
    "comma4_mici_import",
    "canonical_build"
  ],
  "route_replay": "NOT_RUN",
  "route_replay_reason": "private routes were not available in this local workspace"
}
JSON

echo "COMBINED_V6_TESTS=PASS"
