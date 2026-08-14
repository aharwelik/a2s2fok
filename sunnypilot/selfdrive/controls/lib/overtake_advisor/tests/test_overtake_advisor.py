import pytest

from openpilot.sunnypilot.selfdrive.controls.lib.overtake_advisor.advisor import (
  OvertakeAdvisor,
  OvertakeInputs,
  OvertakeMode,
  OvertakeState,
  RuntimeContext,
)
from openpilot.sunnypilot.selfdrive.controls.lib.overtake_advisor.telemetry import shadow_status


def slow_lead(**kwargs):
  values = dict(
    lead_present=True,
    lead_distance_m=30.0,
    ego_speed_mps=28.0,
    lead_speed_mps=20.0,
    set_speed_mps=30.0,
  )
  values.update(kwargs)
  return OvertakeInputs(**values)


def test_no_lead_returns_following():
  result = OvertakeAdvisor().update(OvertakeInputs(lead_present=False))
  assert result.state == OvertakeState.FOLLOWING
  assert not result.simulated_lane_change_request


def test_slow_lead_is_live_shadow_advisory_only():
  result = OvertakeAdvisor().update(slow_lead())
  assert result.state == OvertakeState.PASS_POSSIBLE
  assert result.advisory_text == "PASS POSSIBLE — SIGNAL REQUIRED"
  assert not result.simulated_lane_change_request
  assert shadow_status(result)["state"] == "PASS_POSSIBLE"


@pytest.mark.parametrize(
  "kwargs,reason",
  [
    ({"left_blind_spot": True}, "BLIND_SPOT"),
    ({"lane_available": False}, "LANE_UNAVAILABLE"),
    ({"driver_brake": True}, "DRIVER_BRAKE"),
    ({"driver_gas": True}, "DRIVER_OVERRIDE"),
    ({"steering_fault": True}, "STEERING_FAULT"),
    ({"stale_model": True}, "STALE_MODEL"),
    ({"road_edge_detected": True}, "ROAD_EDGE"),
    ({"occupancy_known": False}, "OCCUPANCY_UNKNOWN"),
    ({"navigation_contradiction": True}, "NAVIGATION_CONTRADICTION"),
    ({"driver_monitoring_valid": False}, "DRIVER_MONITORING_INVALID"),
  ],
)
def test_rejection_gates(kwargs, reason):
  result = OvertakeAdvisor().update(slow_lead(**kwargs))
  assert result.state == OvertakeState.CANCELLED
  assert result.rejection_reason == reason


def test_driver_signal_does_not_create_live_simulation_request():
  result = OvertakeAdvisor().update(slow_lead(left_blinker=True))
  assert result.state == OvertakeState.DRIVER_REQUESTED
  assert not result.simulated_lane_change_request


def test_simulation_request_requires_non_live_runtime_proof():
  advisor = OvertakeAdvisor(OvertakeMode.REPLAY_SIMULATION)
  with pytest.raises(RuntimeError):
    advisor.update(slow_lead(left_blinker=True), RuntimeContext(replay_or_simulation=True, runtime_reports_no_vehicle=False, live_vehicle_attached=False))

  result = advisor.update(
    slow_lead(left_blinker=True),
    RuntimeContext(replay_or_simulation=True, runtime_reports_no_vehicle=True, live_vehicle_attached=False),
  )
  assert result.state == OvertakeState.DRIVER_REQUESTED
  assert result.simulated_lane_change_request
