from openpilot.sunnypilot.selfdrive.ascent_v7.shadow_monitors import (
  EPS_CONFLICT_MONITOR_CAN_ACTUATE,
  SUBARU_DYNAMIC_FWD_HOOK_ACTIVE,
  EPSConflictMonitor,
  EPSConflictSample,
  OwnershipObservation,
  analyze_steering_ownership,
)


def test_eps_conflict_monitor_is_bounded_and_passive():
  monitor = EPSConflictMonitor(window_frames=2)
  for i in range(3):
    snapshot = monitor.update(EPSConflictSample(
      driver_torque=-10.0 - i,
      eps_torque=20.0,
      steering_rate_deg_s=5.0,
      measured_angle_deg=0.0,
      commanded_angle_deg=10.0,
      lkas_request=True,
      steer_error=i == 2,
    ))
  assert snapshot.sample_count == 2
  assert snapshot.directional_driver_conflict_debt > 0.0
  assert snapshot.steer_error_count == 1
  assert snapshot.can_actuate is False
  assert EPS_CONFLICT_MONITOR_CAN_ACTUATE is False


def test_ownership_analyzer_records_overlap_without_forwarding():
  result = analyze_steering_ownership(OwnershipObservation(
    stock_camera_0x124_present=True,
    openpilot_0x124_transmitted=True,
    panda_forwarding_camera_to_main=False,
    handoff_gap_frames=2,
  ))
  assert result["overlap_observed"] is True
  assert result["handoff_gap_observed"] is True
  assert result["dynamic_forwarding_active"] is False
  assert result["can_actuate"] is False
  assert SUBARU_DYNAMIC_FWD_HOOK_ACTIVE is False
