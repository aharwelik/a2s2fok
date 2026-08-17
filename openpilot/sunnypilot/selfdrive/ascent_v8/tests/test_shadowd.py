from math import isclose
from types import SimpleNamespace

from openpilot.sunnypilot.selfdrive.ascent_v8.adaptive_curve import CurveEnvelope
from openpilot.sunnypilot.selfdrive.ascent_v8.shadow_telemetry import ShadowTelemetry
from openpilot.sunnypilot.selfdrive.ascent_v8.shadowd import evaluate_shadow
from openpilot.sunnypilot.selfdrive.ascent_v8.status import status_summary


def ns(**kwargs):
  return SimpleNamespace(**kwargs)


def model_message(*, times=(0.0, 0.2, 0.6), x=(0.0, 2.0, 6.0), velocity=(10.0, 10.0, 10.0),
                  acceleration=(0.0, 0.0, 0.0), yaw_rate=(0.1, 0.1, 0.1), lead_probability=0.0,
                  lead_distance=50.0, desired_accel=0.2, desired_curvature=0.01):
  return ns(
    position=ns(t=times, x=x, y=(0.0, 0.0, 0.0)),
    velocity=ns(x=velocity),
    acceleration=ns(x=acceleration),
    orientationRate=ns(z=yaw_rate),
    roadEdgeStds=(0.1, 0.1),
    roadEdges=(ns(y=(-3.0,)), ns(y=(3.0,))),
    laneLines=(ns(y=(3.5,)), ns(y=(1.8,)), ns(y=(-1.8,)), ns(y=(-3.5,))),
    laneLineProbs=(0.1, 0.9, 0.9, 0.1),
    leadsV3=(ns(prob=lead_probability, x=(lead_distance,)),),
    action=ns(desiredAcceleration=desired_accel, desiredCurvature=desired_curvature),
    frameId=123,
    big=True,
  )


def car_state(*, left_blindspot=False, right_blindspot=False):
  return ns(vEgo=10.0, aEgo=0.0, leftBlindspot=left_blindspot, rightBlindspot=right_blindspot)


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
