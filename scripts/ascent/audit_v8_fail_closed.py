#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def require(violations: list[str], condition: bool, message: str) -> None:
  if not condition:
    violations.append(message)


def main() -> None:
  violations: list[str] = []
  gitmodules = (ROOT / ".gitmodules").read_text()
  policy = (ROOT / "openpilot/sunnypilot/selfdrive/ascent_v8/policy.py").read_text()
  controls = (ROOT / "openpilot/selfdrive/controls/controlsd.py").read_text()
  controls_ext = (ROOT / "openpilot/sunnypilot/selfdrive/controls/controlsd_ext.py").read_text()
  long_planner = (ROOT / "openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_planner.py").read_text()
  maintenance = (ROOT / "openpilot/sunnypilot/system/ascent_maintenance/policy.py").read_text()
  maintenance_client = (ROOT / "tools/ascent_v8_ssh.py").read_text()
  mads = (ROOT / "openpilot/sunnypilot/mads/mads.py").read_text()
  process_config = (ROOT / "openpilot/system/manager/process_config.py").read_text()
  params_keys = (ROOT / "openpilot/common/params_keys.h").read_text()
  shadowd = (ROOT / "openpilot/sunnypilot/selfdrive/ascent_v8/shadowd.py").read_text()
  subaru_safety = (ROOT / "opendbc_repo/opendbc/safety/modes/subaru.h").read_text()
  subaru_interface = (ROOT / "opendbc_repo/opendbc/car/subaru/interface.py").read_text()
  subaru_controller = (ROOT / "opendbc_repo/opendbc/car/subaru/carcontroller.py").read_text()
  subaru_values = (ROOT / "opendbc_repo/opendbc/car/subaru/values.py").read_text()

  require(violations, "https://github.com/aharwelik/sunnyopendbc.git" in gitmodules, "OpenDBC URL is not the public V8 fork")
  require(violations, "branch = v8" in gitmodules, "OpenDBC branch is not locked to V8")
  require(violations, "DIRECT_LONG_ALPHA_DEFAULT = False" in policy, "direct longitudinal default is not literal False")
  require(violations, "PANDA_LONG_RUNTIME_COMPILED = True" in policy, "Panda longitudinal runtime is not compiled")
  require(violations, "TRAFFIC_CONTROL_RUNTIME_COMPILED = True" in policy, "model-stop actuation runtime is not compiled")
  require(violations, "TRAFFIC_CONTROL_EVIDENCE_DEFAULT = False" in policy, "traffic-control evidence is not default-off")
  require(violations, "LANE_CHANGE_EVIDENCE_DEFAULT = False" in policy, "lane-change evidence is not default-off")
  require(violations, all(f'{{"{name}", {{PERSISTENT | DEVELOPMENT_ONLY | BACKUP, BOOL, "0"}}}}' in params_keys for name in (
    "AscentV8TrafficControlShadowEnabled", "AscentV8LaneChangeEvidenceEnabled")),
          "V8 feature toggles are not development-only and default-off")
  require(violations, "CAR.SUBARU_ASCENT_2023" in shadowd and "_is_exact_ascent_2023" in shadowd,
          "V8 evidence runtime is not exact-vehicle gated")
  require(violations, "candidate == CAR.SUBARU_ASCENT_2023" in subaru_interface,
          "alpha longitudinal is not exact-Ascent gated")
  require(violations, "SUBARU_LKAS_ANGLE_GEN2_LONG_TX_MSGS" in subaru_safety,
          "combined Gen2 angle longitudinal TX list is missing")
  require(violations, "MSG_SUBARU_ES_UDS_Response" in subaru_safety and "0x30112203U" in subaru_safety,
          "DID 0x1130 button path is missing")
  require(violations, "long_bus = CanBus.alt" in subaru_controller,
          "Gen2 longitudinal bus-1 routing is missing")
  require(violations, "MSG_SUBARU_ES_LKAS_ANGLE" in subaru_safety, "LKAS angle safety is missing")
  require(violations, "SUBARU_BASE_TX_MSGS(SUBARU_MAIN_BUS, MSG_SUBARU_ES_LKAS_ANGLE)" in subaru_safety,
          "bus-0 LKAS angle TX lock is missing")
  require(violations, "non_tester_present_ecus=[Ecu.fwdCamera]" in subaru_values, "EyeSight diagnostic-safe query exclusion is missing")
  require(violations, "BOOT_CANCEL_GRACE_S = 10.0" in controls, "boot-time ACC cancel grace is missing")
  require(violations, "ALTERNATIVE_EXPERIENCE.ENABLE_MADS" in controls_ext, "Panda MADS authorization check is missing")
  require(violations, "clamp_speed_cap_accel" in long_planner, "no-phantom-acceleration clamp is missing")
  require(violations, "restrict,command=" in maintenance and "ssh-ed25519" in maintenance,
          "restricted maintenance transport is missing")
  require(violations, "OPERATOR_PUBLIC_KEY" in maintenance and "AUTHORIZED_KEYS" in maintenance,
          "MacBook operator key is missing")
  require(violations, "PRIVATE KEY" not in maintenance, "private SSH material is embedded")
  require(violations, "ascentmaintenanced" in process_config and "enabled=COMMA_HARDWARE" in process_config,
          "device-only maintenance daemon is not registered")
  require(violations, "ascentv8shadowd" in process_config and "enabled=COMMA_HARDWARE" in process_config,
          "device-only V8 shadow evaluator is not registered")
  require(violations, "PasswordAuthentication=no" in maintenance_client and "KbdInteractiveAuthentication=no" in maintenance_client,
          "maintenance client does not explicitly reject password login")
  require(violations, "CS.gearShifter == GearShifter.park" in mads and "EventNameSP.lkasDisable" in mads,
          "MADS Park disengagement guard is missing")
  private_key_candidates = [path for path in ROOT.rglob("*") if path.is_file() and path.name in {"id_rsa", "id_ed25519"}]
  require(violations, not private_key_candidates, f"private key files present: {private_key_candidates}")

  result = {
    "passed": not violations,
    "violations": violations,
    "bus0_angle_steering": "SUBARU_BASE_TX_MSGS(SUBARU_MAIN_BUS, MSG_SUBARU_ES_LKAS_ANGLE)" in subaru_safety,
    "exact_ascent_alpha_longitudinal": "candidate == CAR.SUBARU_ASCENT_2023" in subaru_interface,
    "restricted_maintenance_key": "restrict,command=" in maintenance,
    "macbook_operator_key": "OPERATOR_PUBLIC_KEY" in maintenance,
    "maintenance_client_password_login_disabled": "PasswordAuthentication=no" in maintenance_client,
    "macbook_operator_shell": "OPERATOR_PUBLIC_KEY" in maintenance,
  }
  print(json.dumps(result, indent=2))
  raise SystemExit(1 if violations else 0)


if __name__ == "__main__":
  main()
