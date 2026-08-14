import numpy as np
import pytest

from openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.estimator import (
  LeadSnapshot,
  RejectionReason,
  RuntimeContext,
  StopInputs,
  StopObstacleMode,
  StopTargetEstimator,
)
from openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.obstacle_adapter import select_shadow_or_simulation_obstacle
from openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.state_machine import StopObstacleStateMachine, StopState
from openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.telemetry import shadow_status


def make_inputs(**kwargs):
  values = dict(
    should_stop=True,
    position_x=(40.0, 42.0, 44.0),
    velocity_x=(8.0, 2.0, 0.0),
    ego_speed_mps=12.0,
    confidence=0.8,
  )
  values.update(kwargs)
  return StopInputs(**values)


def test_valid_stop_target_shadow_label():
  target = StopTargetEstimator().estimate(make_inputs())
  assert target.valid
  assert target.rejection_reason == RejectionReason.NONE
  assert shadow_status(target)["label"] == "MODEL STOP 40 m — SHADOW"


@pytest.mark.parametrize(
  "kwargs,reason",
  [
    ({"should_stop": False}, RejectionReason.PROFILE_INCONSISTENT),
    ({"model_age_s": 1.0}, RejectionReason.MODEL_STALE),
    ({"position_x": (-2.0,), "velocity_x": (0.0,)}, RejectionReason.TARGET_BEHIND),
    ({"position_x": (3.0,), "velocity_x": (0.0,)}, RejectionReason.TARGET_TOO_CLOSE),
    ({"position_x": (200.0,), "velocity_x": (0.0,)}, RejectionReason.TARGET_TOO_FAR),
    ({"position_x": (10.0,), "velocity_x": (0.0,), "ego_speed_mps": 20.0}, RejectionReason.DECEL_OUT_OF_RANGE),
    ({"lead_0": LeadSnapshot(True, 20.0)}, RejectionReason.REAL_LEAD_CLOSER),
    ({"curve_slowdown": True}, RejectionReason.CURVE_SLOWDOWN),
    ({"driver_override": True}, RejectionReason.DRIVER_OVERRIDE),
    ({"vehicle_fault": True}, RejectionReason.VEHICLE_FAULT),
    ({"stock_aeb_active": True}, RejectionReason.VEHICLE_FAULT),
    ({"confidence": 0.1}, RejectionReason.LOW_CONFIDENCE),
  ],
)
def test_rejection_reasons(kwargs, reason):
  target = StopTargetEstimator().estimate(make_inputs(**kwargs))
  assert not target.valid
  assert target.rejection_reason == reason


def test_state_machine_persistence_stop_and_release():
  estimator = StopTargetEstimator()
  target = estimator.estimate(make_inputs())
  sm = StopObstacleStateMachine(persistence_frames=2, release_frames=2)
  assert sm.update(target, ego_speed_mps=8.0).state == StopState.CANDIDATE
  assert sm.update(target, ego_speed_mps=8.0).state == StopState.STOPPING
  assert sm.update(target, ego_speed_mps=0.0).state == StopState.STOPPED
  assert sm.update(target, ego_speed_mps=0.0, release_signal_valid=True).state == StopState.STOPPED
  assert sm.update(target, ego_speed_mps=0.0, release_signal_valid=True).state == StopState.RELEASING


def test_live_shadow_does_not_mutate_existing_obstacle_stack():
  target = StopTargetEstimator().estimate(make_inputs())
  existing = [np.array([20.0, 19.0, 18.0])]
  obstacle, mutates = select_shadow_or_simulation_obstacle(
    StopObstacleMode.LIVE_SHADOW,
    RuntimeContext(StopObstacleMode.LIVE_SHADOW),
    target,
    existing,
  )
  assert obstacle is not None
  assert not mutates
  assert existing[0].tolist() == [20.0, 19.0, 18.0]


def test_simulation_obstacle_requires_two_non_live_proofs():
  target = StopTargetEstimator(StopObstacleMode.REPLAY_SIMULATION).estimate(make_inputs())
  with pytest.raises(RuntimeError):
    select_shadow_or_simulation_obstacle(
      StopObstacleMode.REPLAY_SIMULATION,
      RuntimeContext(StopObstacleMode.REPLAY_SIMULATION, replay_or_simulation=True, runtime_reports_no_vehicle=False, live_vehicle_attached=False),
      target,
      [],
    )

  obstacle, mutates = select_shadow_or_simulation_obstacle(
    StopObstacleMode.REPLAY_SIMULATION,
    RuntimeContext(StopObstacleMode.REPLAY_SIMULATION, replay_or_simulation=True, runtime_reports_no_vehicle=True, live_vehicle_attached=False),
    target,
    [np.array([80.0, 80.0, 80.0])],
  )
  assert mutates
  assert obstacle is not None
  assert obstacle[0] == pytest.approx(40.0)

