#!/usr/bin/env python3
import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "openpilot/sunnypilot/selfdrive/ascent_v8"
PROHIBITED = ("CANPacker", "sendcan", "disable_ecu", "make_can_msg", "set_safety_hooks")
REQUIRED_FALSE = {
  "DIRECT_LONG_ALPHA_DEFAULT",
  "PANDA_LONG_RUNTIME_COMPILED",
  "TRAFFIC_CONTROL_RUNTIME_COMPILED",
  "AUTOMATIC_PASS_RUNTIME_COMPILED",
  "AUTOMATIC_BLINKER_RUNTIME_COMPILED",
  "AUTOMATIC_LANE_SELECTION_RUNTIME_COMPILED",
  "LIVE_LANE_POSITION_TRIM_ACTIVE",
  "LIVE_ADAPTIVE_CURVE_CONTROL",
  "BIG_MODEL_LAB_DEFAULT",
}


def main() -> None:
  violations: list[str] = []
  for path in PACKAGE.rglob("*.py"):
    if "tests" in path.parts:
      continue
    text = path.read_text()
    for token in PROHIBITED:
      if token in text:
        violations.append(f"{path.name}: prohibited {token}")

  values = {}
  for node in ast.parse((PACKAGE / "policy.py").read_text()).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
      try:
        values[node.targets[0].id] = ast.literal_eval(node.value)
      except Exception:
        pass
  for name in REQUIRED_FALSE:
    if values.get(name) is not False:
      violations.append(f"{name} must be False")

  print(json.dumps({"passed": not violations, "violations": violations}, indent=2))
  raise SystemExit(1 if violations else 0)


if __name__ == "__main__":
  main()
