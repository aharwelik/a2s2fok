#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
pythonpath = [Path(entry).resolve() for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep) if entry]
if pythonpath != [ROOT]:
  raise SystemExit(f"PYTHONPATH must contain only the repository root, got {pythonpath!r}")
if str(ROOT) not in sys.path:
  raise SystemExit("repository root is missing from sys.path")

MODULES = (
  "openpilot.system.manager.manager",
  "openpilot.system.manager.process_config",
  "openpilot.selfdrive.selfdrived.selfdrived",
  "openpilot.selfdrive.controls.plannerd",
  "openpilot.selfdrive.modeld.helpers",
  "openpilot.selfdrive.controls.lib.longitudinal_planner",
  "openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner",
  "openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.estimator",
  "openpilot.sunnypilot.selfdrive.controls.lib.overtake_advisor.advisor",
  "openpilot.sunnypilot.selfdrive.controls.controlsd_ext",
  "openpilot.sunnypilot.selfdrive.ascent_v7.direct_long_alpha",
  "openpilot.sunnypilot.selfdrive.ascent_v7.shadow_monitors",
  "opendbc.car.subaru.interface",
  "opendbc.car.subaru.carstate",
  "opendbc.car.subaru.carcontroller",
)


def main() -> int:
  imported = []
  for name in MODULES:
    importlib.import_module(name)
    imported.append(name)

  process_config = importlib.import_module("openpilot.system.manager.process_config")
  required_processes = {"selfdrived", "plannerd", "controlsd", "card"}
  missing = sorted(required_processes - process_config.managed_processes.keys())
  if missing:
    raise SystemExit(f"manager process configuration missing: {missing}")

  print(json.dumps({"passed": True, "imports": imported, "manager_processes": sorted(required_processes)}, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
