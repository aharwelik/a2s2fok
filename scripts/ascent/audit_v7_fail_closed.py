#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V7_ROOT = ROOT / "sunnypilot/selfdrive/ascent_v7"
OPENDBC_ROOT = ROOT / "opendbc_repo/opendbc"

PROHIBITED_V7_TOKENS = (
  "CANPacker",
  "disable_ecu",
  "make_can_msg",
  "sendcan",
  "can_send",
  "set_safety_hooks",
  "set_alternative_experience",
)


def literal_assignments(path: Path) -> dict[str, object]:
  assignments: dict[str, object] = {}
  for node in ast.parse(path.read_text()).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
      try:
        assignments[node.targets[0].id] = ast.literal_eval(node.value)
      except (ValueError, TypeError):
        pass
  return assignments


def main() -> int:
  violations: list[dict[str, str]] = []
  for path in V7_ROOT.rglob("*.py"):
    if "tests" in path.parts:
      continue
    text = path.read_text()
    for token in PROHIBITED_V7_TOKENS:
      if token in text:
        violations.append({"file": str(path.relative_to(ROOT)), "reason": f"actuation token: {token}"})

  direct_long = literal_assignments(V7_ROOT / "direct_long_alpha.py")
  shadows = literal_assignments(V7_ROOT / "shadow_monitors.py")
  required_false = {
    "DIRECT_LONG_ALPHA_DEFAULT": direct_long.get("DIRECT_LONG_ALPHA_DEFAULT"),
    "TRAFFIC_CONTROL_ALPHA_DEFAULT": direct_long.get("TRAFFIC_CONTROL_ALPHA_DEFAULT"),
    "PANDA_LONG_RUNTIME_COMPILED": direct_long.get("PANDA_LONG_RUNTIME_COMPILED"),
    "TRAFFIC_CONTROL_RUNTIME_COMPILED": direct_long.get("TRAFFIC_CONTROL_RUNTIME_COMPILED"),
    "EPS_CONFLICT_MONITOR_CAN_ACTUATE": shadows.get("EPS_CONFLICT_MONITOR_CAN_ACTUATE"),
    "SUBARU_DYNAMIC_FWD_HOOK_ACTIVE": shadows.get("SUBARU_DYNAMIC_FWD_HOOK_ACTIVE"),
  }
  for name, value in required_false.items():
    if value is not False:
      violations.append({"file": "sunnypilot/selfdrive/ascent_v7", "reason": f"{name} must be literal False"})

  gitmodules = (ROOT / ".gitmodules").read_text()
  if "branch = ascent-2023-v7-alpha-opendbc" not in gitmodules:
    violations.append({"file": ".gitmodules", "reason": "V7 OpenDBC branch is not pinned"})

  interface = (OPENDBC_ROOT / "car/subaru/interface.py").read_text()
  if "SubaruFlags.GLOBAL_GEN2 | SubaruFlags.PREGLOBAL |" not in interface or "SubaruFlags.LKAS_ANGLE" not in interface:
    violations.append({"file": "opendbc_repo/opendbc/car/subaru/interface.py", "reason": "angle Gen2 long block missing"})

  safety = (OPENDBC_ROOT / "safety/modes/subaru.h").read_text()
  for token in ("SUBARU_MAIN_BUS 0U", "{lkas_msg,                     SUBARU_MAIN_BUS"):
    if token not in safety:
      violations.append({"file": "opendbc_repo/opendbc/safety/modes/subaru.h", "reason": f"bus-0 invariant missing: {token}"})

  result = {
    "passed": not violations,
    "stock_eyesight_longitudinal": True,
    "live_steering_bus": 0,
    "dual_bus_steering": False,
    "required_false": required_false,
    "violations": violations,
  }
  print(json.dumps(result, indent=2, sort_keys=True))
  return 1 if violations else 0


if __name__ == "__main__":
  raise SystemExit(main())
