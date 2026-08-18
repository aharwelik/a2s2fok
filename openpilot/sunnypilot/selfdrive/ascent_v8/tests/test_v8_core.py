from openpilot.sunnypilot.selfdrive.ascent_v8.adaptive_curve import CurveEnvelope
from openpilot.sunnypilot.selfdrive.ascent_v8.closed_course_planners import ClosedCoursePlanner, PlannerAction, PlannerInputs
from openpilot.sunnypilot.selfdrive.ascent_v8.direct_long_workbench import DirectLongEvidence, SpeedDependentEnvelope, SpeedEnvelopePoint
from openpilot.sunnypilot.selfdrive.ascent_v8.lab_gate import GateState, LabGateEvaluator, LabInputs
from openpilot.sunnypilot.selfdrive.ascent_v8.lane_position_shadow import LanePositionInput, LanePositionShadow
from openpilot.sunnypilot.selfdrive.ascent_v8.model_runtime_policy import BigModelPolicy
from openpilot.sunnypilot.selfdrive.ascent_v8.policy import V8ReleaseBoundary
from openpilot.sunnypilot.selfdrive.ascent_v8.safety_guard import FinalCommandShadowGuard, GuardInput
from openpilot.sunnypilot.selfdrive.ascent_v8.speed_limit_evidence import SpeedLimitEvidence, same_way_for_revalidation
from openpilot.sunnypilot.selfdrive.ascent_v8.stop_sign_lab import StopSignLabPolicy
from openpilot.sunnypilot.selfdrive.ascent_v8.trajectory_supervisor import TrajectoryPoint, TrajectorySupervisor, TrajectoryVerdict
from openpilot.sunnypilot.selfdrive.ascent_v8.unknown_space import RegionEvidence, SpaceState, UnknownSpaceClassifier


def test_release_boundary():
  boundary = V8ReleaseBoundary()
  assert boundary.direct_long is False
  assert boundary.panda_long is True
  assert boundary.traffic_control is True
  assert not boundary.fail_closed


def test_lab_gate():
  good = LabInputs(True, True, True, True, True, True, True, True, True, True, True, True)
  assert LabGateEvaluator().evaluate(good).state is GateState.READY
  bad = LabInputs(True, True, True, True, True, True, True, True, True, True, False, True)
  assert LabGateEvaluator().evaluate(bad).state is GateState.BLOCKED


def test_closed_course_planner_has_no_live_connector():
  gate = LabGateEvaluator().evaluate(LabInputs(True, True, True, True, True, True, True, True, True, True, True, True))
  decision = ClosedCoursePlanner().evaluate(PlannerInputs(gate, SpaceState.CLEAR, True, True, True))
  assert decision.action is PlannerAction.PASS_CANDIDATE
  assert decision.simulation_request
  assert decision.can_actuate is False


def test_unknown_not_clear():
  evidence = RegionEvidence(False, False, None, False, False, False, 0.1)
  assert UnknownSpaceClassifier().classify(evidence) is SpaceState.UNKNOWN


def test_clear_positive_evidence():
  evidence = RegionEvidence(True, False, False, True, False, False, 0.1)
  assert UnknownSpaceClassifier().classify(evidence) is SpaceState.CLEAR


def test_bsm_blocks():
  evidence = RegionEvidence(True, False, True, True, False, False, 0.1)
  assert UnknownSpaceClassifier().classify(evidence) is SpaceState.OCCUPIED


def test_curve_backoff():
  envelope = CurveEnvelope(steering_capability=1.8)
  envelope.observe_controller(True, True, 1.8, True)
  assert envelope.steering_capability < 1.8


def test_curve_target():
  assert CurveEnvelope().target_speed(0.01) is not None


def test_supervisor_valid():
  points = [TrajectoryPoint(0, 0, 0, 5, 0, 0.01), TrajectoryPoint(1, 5, 0, 5, 0, 0.01)]
  assert TrajectorySupervisor().evaluate(points, True, True, True).verdict is TrajectoryVerdict.VALID


def test_supervisor_unknown_fallback():
  points = [TrajectoryPoint(0, 0, 0, 5, 0, 0.01), TrajectoryPoint(1, 5, 0, 5, 0, 0.01)]
  assert TrajectorySupervisor().evaluate(points, True, False, True).verdict is TrajectoryVerdict.FALLBACK_REQUIRED


def test_no_phantom_accel():
  output = FinalCommandShadowGuard().project(GuardInput(1.0, 0.0, -0.5, speed_limit_accel_cap=0.2))
  assert output.corrected_accel == -0.5


def test_direct_long_defaults_block():
  assert not DirectLongEvidence().panda_long_ready


def test_direct_long_all_ready_is_evidence_only():
  assert DirectLongEvidence(True, True, True, True, True, True, True, True).panda_long_ready
  assert V8ReleaseBoundary().direct_long is False


def test_speed_envelope():
  points = [SpeedEnvelopePoint(0, 1, 1, 1000), SpeedEnvelopePoint(10, 2, 2, 2000)]
  assert SpeedDependentEnvelope(points).structurally_valid()


def test_big_model_policy():
  assert BigModelPolicy().safe_defaults()


def test_lane_position_is_shadow_only_and_road_edge_vetoed():
  result = LanePositionShadow().evaluate(LanePositionInput(0.1, 1.8, -1.6, 0.9, 0.9, False, 0.1))
  assert result.can_actuate is False
  assert result.blended_path_y_m == 0.1
  assert result.reasons == ("road_edge_veto",)


def test_stop_sign_lab_has_no_runtime_braking_path():
  assert StopSignLabPolicy().fail_closed()


def test_speed_limit_evidence():
  evidence = SpeedLimitEvidence(123, 15, "dashboard", 27, -82, 90, 1, 0.9)
  assert evidence.valid()
  assert same_way_for_revalidation(123, 123)
  assert not same_way_for_revalidation(123, 124)
