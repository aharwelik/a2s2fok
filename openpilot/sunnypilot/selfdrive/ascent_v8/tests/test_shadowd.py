from math import isclose
from types import SimpleNamespace

from opendbc.car.subaru.values import CAR
from opendbc.car.structs import car
from openpilot.sunnypilot.selfdrive.ascent_v8.adaptive_curve import CurveEnvelope
from openpilot.sunnypilot.selfdrive.ascent_v8.pass_adviser import PassAdviser
from openpilot.sunnypilot.selfdrive.ascent_v8.shadow_telemetry import ShadowTelemetry
from openpilot.sunnypilot.selfdrive.ascent_v8.shadowd import _is_exact_ascent_2023, evaluate_shadow
from openpilot.sunnypilot.selfdrive.ascent_v8.status import status_summary
from openpilot.sunnypilot.selfdrive.ascent_v8.traffic_control_shadow import TrafficControlShadow


def ns(**kwargs):
  return SimpleNamespace(**kwargs)


def model_message(*, times=(0.0, 0.2, 0.6), x=(0.0, 2.0, 6.0), velocity=(10.0, 10.0, 10.0),
                  acceleration=(0.0, 0.0, 0.0), yaw_rate=(0.1, 0.1, 0.1), lead_probability=0.0,
                  lead_distance=50.0, lead_speed=10.0, desired_accel=0.2, desired_curvature=0.01,
                  should_stop=False, adjacent_lanes=True):
  outer_probability = 0.8 if adjacent_lanes else 0.1
  return ns(
    position=ns(t=times, x=x, y=(0.0, 0.0, 0.0)),
    velocity=ns(x=velocity),
    acceleration=ns(x=acceleration),
    orientationRate=ns(z=yaw_rate),
    roadEdgeStds=(0.1, 0.1),
    roadEdges=(ns(y=(-3.0,)), ns(y=(3.0,))),
    laneLines=(ns(y=(5.4,)), ns(y=(1.8,)), ns(y=(-1.8,)), ns(y=(-5.4,))),
    laneLineProbs=(outer_probability, 0.9, 0.9, outer_probability),
    leadsV3=(ns(prob=lead_probability, x=(lead_distance,), v=(lead_speed,)),),
    action=ns(desiredAcceleration=desired_accel, desiredCurvature=desired_curvature, shouldStop=should_stop),
    frameId=123,
    big=True,
  )


def car_state(*, left_blindspot=False, right_blindspot=False, left_blinker=False, right_blinker=False):
  return ns(vEgo=10.0, aEgo=0.0, leftBlindspot=left_blindspot, rightBlindspot=right_blindspot,
            leftBlinker=left_blinker, rightBlinker=right_blinker)


def controls_state(*, saturated=False, curvature=0.01):
  lateral_state = ns(saturated=saturated)
  lateral_union = ns(which=lambda: "angleState", angleState=lateral_state)
  return ns(curvature=curvature, lateralControlState=lateral_union)


def test_real_model_time_curvature_and_curve_target_are_used():
  result = evaluate_shadow(car_state(), model_message(), controls_state=controls_state(), car_control=ns(latActive=True))

  assert result["trajectory"] == "VALID"
  assert isclose(result["peak_curvature"], 0.01)
  assert isclose(result["predicted_max_lateral_accel"], 1.0)
  assert isclose(result["curve_target_speed_mps"], 12.6491106407)
  assert result["left_space"] == "CLEAR"
  assert result["right_space"] == "CLEAR"


def test_nonuniform_model_time_drives_jerk_check():
  result = evaluate_shadow(car_state(), model_message(acceleration=(0.0, 2.0, 2.0)))

  assert result["trajectory"] == "REJECTED"
  assert "jerk_limit" in result["trajectory_reasons"]


def test_nonfinite_sample_stays_aligned_and_is_reported():
  result = evaluate_shadow(car_state(), model_message(x=(0.0, float("nan"), 6.0)))

  assert result["trajectory"] == "FALLBACK_REQUIRED"
  assert "nonfinite" in result["trajectory_reasons"]


def test_actual_source_age_and_side_specific_bsm_are_visible():
  stale = evaluate_shadow(car_state(), model_message(), model_age_s=0.8)
  occupied = evaluate_shadow(car_state(left_blindspot=True), model_message())

  assert stale["source_fresh"] is False
  assert stale["space"] == "STALE"
  assert "stale_sources" in stale["trajectory_reasons"]
  assert occupied["left_space"] == "OCCUPIED"
  assert occupied["right_space"] == "CLEAR"


def test_model_action_guard_and_adaptive_curve_state_are_live():
  envelope = CurveEnvelope(steering_capability=1.8)
  result = evaluate_shadow(
    car_state(), model_message(desired_curvature=0.3), controls_state=controls_state(saturated=True),
    car_control=ns(latActive=True), curve_envelope=envelope,
  )

  assert result["guard_curvature"] == 0.2
  assert "curvature" in result["guard_reasons"]
  assert result["curve_capability"] < 1.8


def test_model_stop_prediction_debounces_and_clears():
  detector = TrafficControlShadow()
  stopping_model = model_message(should_stop=True, desired_accel=-0.8)

  first = evaluate_shadow(car_state(), stopping_model, traffic_control_shadow=detector)
  second = evaluate_shadow(car_state(), stopping_model, traffic_control_shadow=detector)
  for _ in range(detector.ASSERT_FRAMES - 2):
    active = evaluate_shadow(car_state(), stopping_model, traffic_control_shadow=detector)

  assert first["model_stop_raw_candidate"] is True
  assert first["model_stop_prediction"] is False
  assert second["model_stop_prediction"] is False
  assert active["model_stop_prediction"] is True
  assert active["model_stop_confidence"] >= 0.8

  held = evaluate_shadow(car_state(), model_message(), traffic_control_shadow=detector)
  assert held["model_stop_prediction"] is True
  assert held["model_stop_confidence"] == active["model_stop_confidence"]
  assert "debounce_hold" in held["model_stop_reasons"]

  for _ in range(detector.CLEAR_FRAMES - 1):
    cleared = evaluate_shadow(car_state(), model_message(), traffic_control_shadow=detector)
  assert cleared["model_stop_prediction"] is False


def test_short_stopping_path_arms_but_lead_curve_and_stale_sources_veto():
  stopping_path = model_message(times=(0.0, 2.0, 6.0), x=(0.0, 14.0, 25.0), velocity=(10.0, 5.0, 0.0),
                                desired_accel=-0.6)
  raw = evaluate_shadow(car_state(), stopping_path)
  with_lead = evaluate_shadow(car_state(), model_message(should_stop=True, desired_accel=-0.8,
                                                          lead_probability=0.9, lead_distance=20.0))
  on_curve = evaluate_shadow(car_state(), model_message(should_stop=True, desired_accel=-0.8,
                                                         yaw_rate=(0.6, 0.6, 0.6)))
  stale = evaluate_shadow(car_state(), model_message(should_stop=True, desired_accel=-0.8), model_age_s=0.8)

  assert raw["model_stop_raw_candidate"] is True
  assert with_lead["model_stop_raw_candidate"] is False
  assert "lead_veto" in with_lead["model_stop_reasons"]
  assert on_curve["model_stop_raw_candidate"] is False
  assert "curve_veto" in on_curve["model_stop_reasons"]
  assert stale["model_stop_raw_candidate"] is False
  assert "stale_sources" in stale["model_stop_reasons"]


def test_driver_left_lane_change_candidate_uses_live_lead_and_left_space():
  adviser = PassAdviser()
  slow_lead = model_message(lead_probability=0.95, lead_distance=25.0, lead_speed=5.0)

  for _ in range(adviser.ASSERT_FRAMES):
    result = evaluate_shadow(car_state(left_blinker=True), slow_lead, pass_adviser=adviser)

  assert result["left_lane_geometry_ready"] is True
  assert result["driver_left_lane_change_candidate"] is True
  assert result["automatic_pass"] is False

  blocked = evaluate_shadow(car_state(left_blindspot=True, left_blinker=True), slow_lead, pass_adviser=PassAdviser())
  assert blocked["left_lane_geometry_ready"] is False
  assert "left_space_not_clear" in blocked["lane_change_evidence_reasons"]


def test_lane_change_candidate_clears_immediately_on_bsm_and_requires_adjacent_lane_geometry():
  adviser = PassAdviser()
  slow_lead = model_message(lead_probability=0.95, lead_distance=25.0, lead_speed=5.0)
  for _ in range(adviser.ASSERT_FRAMES):
    ready = evaluate_shadow(car_state(left_blinker=True), slow_lead, pass_adviser=adviser)
  assert ready["driver_left_lane_change_candidate"] is True

  occupied = evaluate_shadow(car_state(left_blindspot=True, left_blinker=True), slow_lead, pass_adviser=adviser)
  assert occupied["left_lane_geometry_ready"] is False
  assert occupied["driver_left_lane_change_candidate"] is False

  no_lane = evaluate_shadow(car_state(left_blinker=True),
                            model_message(lead_probability=0.95, lead_distance=25.0, lead_speed=5.0, adjacent_lanes=False),
                            pass_adviser=PassAdviser())
  assert no_lane["left_adjacent_lane_geometry"] is False
  assert "left_adjacent_lane_geometry_unknown" in no_lane["lane_change_evidence_reasons"]


def test_disabled_feature_toggles_reset_state_and_publish_disabled():
  detector = TrafficControlShadow()
  adviser = PassAdviser()
  stopping_model = model_message(should_stop=True, desired_accel=-0.8, lead_probability=0.95,
                                 lead_distance=25.0, lead_speed=5.0)
  for _ in range(detector.ASSERT_FRAMES):
    result = evaluate_shadow(car_state(left_blinker=True), stopping_model,
                             traffic_control_shadow=detector, pass_adviser=adviser)
  assert result["model_stop_prediction"] is False  # lead veto
  disabled = evaluate_shadow(car_state(left_blinker=True), stopping_model,
                             traffic_control_shadow=detector, pass_adviser=adviser,
                             traffic_control_enabled=False, pass_adviser_enabled=False)
  assert disabled["model_stop_enabled"] is False
  assert disabled["model_stop_reasons"] == ["disabled"]
  assert disabled["lane_change_evidence_enabled"] is False
  assert disabled["lane_change_evidence_reasons"] == ["disabled"]


def test_uncorroborated_should_stop_and_malformed_trajectories_do_not_arm():
  disagreement = evaluate_shadow(car_state(), model_message(should_stop=True, desired_accel=0.3))
  empty = evaluate_shadow(car_state(), model_message(times=(), x=(), velocity=(), acceleration=(), yaw_rate=()))
  backward = evaluate_shadow(car_state(), model_message(x=(0.0, 4.0, 3.0)))

  assert disagreement["model_stop_raw_candidate"] is False
  assert "uncorroborated_should_stop" in disagreement["model_stop_reasons"]
  assert empty["trajectory"] == "REJECTED"
  assert "short_trajectory" in empty["trajectory_reasons"]
  assert empty["model_stop_raw_candidate"] is False
  assert "x_order" in backward["trajectory_reasons"]
  assert backward["model_stop_raw_candidate"] is False


def test_shadow_is_gated_to_exact_2023_ascent_carparams():
  class ParamsStub:
    def __init__(self, fingerprint):
      cp = car.CarParams.new_message()
      cp.carFingerprint = fingerprint
      self.raw = cp.to_bytes()

    def get(self, _key):
      return self.raw

  assert _is_exact_ascent_2023(ParamsStub(str(CAR.SUBARU_ASCENT_2023)))
  assert not _is_exact_ascent_2023(ParamsStub("SUBARU_OUTBACK_2023"))


def test_telemetry_aggregates_feature_success_and_errors():
  telemetry = ShadowTelemetry(started_monotonic_s=10.0)
  telemetry.observe(evaluate_shadow(car_state(), model_message()))
  telemetry.observe_error(RuntimeError("sample failure"))
  snapshot = telemetry.snapshot(updated_monotonic_s=12.0)

  assert snapshot["runtime_s"] == 2.0
  assert snapshot["evaluations"] == 1
  assert snapshot["errors"] == 1
  assert snapshot["trajectory_counts"] == {"VALID": 1}
  assert snapshot["last"]["curve_target_speed_mps"] is not None

  summary = status_summary(snapshot)
  assert "Live model: Chestnut; sources fresh" in summary
  assert "Curve target:" in summary
  assert "1 evaluations; 1 errors" in summary
