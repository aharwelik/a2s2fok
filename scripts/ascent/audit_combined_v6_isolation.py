#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [
  ROOT / "sunnypilot/selfdrive/controls/lib/stop_obstacle",
  ROOT / "sunnypilot/selfdrive/controls/lib/overtake_advisor",
]

PROHIBITED = [
  "CANPacker",
  "Panda",
  "disable_ecu",
  "subarucan",
  "sendcan",
  "ES_Brake",
  "ES_Status",
  "DISABLE_EYESIGHT",
  "openpilotLongitudinalControl = True",
  "CarController",
]


def iter_python_files():
  for scan_dir in SCAN_DIRS:
    yield from scan_dir.rglob("*.py")


def main() -> int:
  violations = []
  for path in iter_python_files():
    text = path.read_text()
    for token in PROHIBITED:
      if token in text:
        violations.append({"file": str(path.relative_to(ROOT)), "token": token})

  result = {"passed": not violations, "violations": violations}
  print(json.dumps(result, indent=2, sort_keys=True))
  return 1 if violations else 0


if __name__ == "__main__":
  raise SystemExit(main())
