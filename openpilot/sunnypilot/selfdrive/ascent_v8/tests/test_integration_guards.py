from openpilot.selfdrive.controls.controlsd import cruise_cancel_allowed
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import clamp_speed_cap_accel
from openpilot.system.manager.process_config import managed_processes


def test_boot_cancel_grace_is_bounded():
  assert not cruise_cancel_allowed(False, 999)
  assert cruise_cancel_allowed(False, 1000)
  assert cruise_cancel_allowed(True, 0)


def test_speed_cap_cannot_add_acceleration():
  assert clamp_speed_cap_accel(0.2, -0.5) == -0.5
  assert clamp_speed_cap_accel(-1.0, -0.5) == -1.0


def test_maintenance_daemon_is_registered():
  process = managed_processes["ascentmaintenanced"]
  assert process.module == "openpilot.sunnypilot.system.ascent_maintenance.daemon"
  shadow = managed_processes["ascentv8shadowd"]
  assert shadow.module == "openpilot.sunnypilot.selfdrive.ascent_v8.shadowd"
