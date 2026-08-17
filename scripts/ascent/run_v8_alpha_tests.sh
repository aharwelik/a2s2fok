#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT"

uv run python scripts/ascent/audit_v8_package.py
uv run python scripts/ascent/audit_v8_fail_closed.py
uv run --with pytest --with pytest-mock python -m pytest -q \
  openpilot/sunnypilot/selfdrive/ascent_v8/tests \
  openpilot/sunnypilot/system/ascent_maintenance/tests \
  openpilot/sunnypilot/mads/tests/test_mads_steering_mode.py

(
  cd opendbc_repo
  uv run --with pytest python -m pytest -q \
    opendbc/car/subaru/tests/test_subaru.py \
    opendbc/car/subaru/tests/test_ascent_v6.py \
    opendbc/car/subaru/tests/test_ascent_v7_controller_panda_fuzz.py \
    opendbc/safety/tests/test_subaru.py
)

printf '%s\n' 'V8_ALPHA_TESTS=PASS'
