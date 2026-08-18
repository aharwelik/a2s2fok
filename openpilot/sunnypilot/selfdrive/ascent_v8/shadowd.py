#!/usr/bin/env python3
from __future__ import annotations

import json
from math import isfinite
import time

import openpilot.cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from opendbc.car.subaru.values import CAR
from opendbc.car.structs import car
from openpilot.sunnypilot.selfdrive.ascent_v8.adaptive_curve import CurveEnvelope
from openpilot.sunnypilot.selfdrive.ascent_v8.calibration_recorder import (
  CalibrationRecorder,
  build_calibration_sample,
)
from openpilot.sunnypilot.selfdrive.ascent_v8.lane_position_shadow import LanePositionInput, LanePositionShadow
from openpilot.sunnypilot.selfdrive.ascent_v8.pass_adviser import PassAdviser, PassInput
from openpilot.sunnypilot.selfdrive.ascent_v8.safety_guard import FinalCommandShadowGuard, GuardInput
from openpilot.sunnypilot.selfdrive.ascent_v8.shadow_telemetry import ShadowTelemetry
from openpilot.sunnypilot.selfdrive.ascent_v8.traffic_control_shadow import TrafficControlInput, TrafficControlShadow
from openpilot.sunnypilot.selfdrive.ascent_v8.trajectory_supervisor import TrajectoryPoint, TrajectorySupervisor
from openpilot.sunnypilot.selfdrive.ascent_v8.unknown_space import RegionEvidence, UnknownSpaceClassifier


STATUS_INTERVAL_S = 1.0
LOG_HEARTBEAT_S = 5.0
LOG_TRANSITION_MIN_S = 1.0
SOURCE_FRESH_S = 0.5
LEAD_PROBABILITY_THRESHOLD = 0.5
ADJACENT_LANE_PROBABILITY_THRESHOLD = 0.5
ADJACENT_LANE_WIDTH_MIN_M = 2.5
ADJACENT_LANE_WIDTH_MAX_M = 4.8


def _float_list(values) -> list[float]:
  return [float(value) for value in values]


def _value(values: list[float], index: int, default: float = float("nan")) -> float:
  return values[index] if index < len(values) else default


def _controller_saturated(controls_state) -> bool:
  if controls_state is None:
    return False
  try:
    state = getattr(controls_state.lateralControlState, controls_state.lateralControlState.which())
    return bool(state.saturated)
  except Exception:
    return False


def _lead_observation(model, v_ego: float, radar_state=None) -> tuple[float, float | None, float | None, bool]:
  probability = 0.0
  closest: float | None = None
  closest_speed: float | None = None
  for lead in model.leadsV3:
    lead_probability = float(lead.prob)
    if not isfinite(lead_probability):
      continue
    probability = max(probability, lead_probability)
    if lead_probability < LEAD_PROBABILITY_THRESHOLD or not len(lead.x):
      continue
    distance = float(lead.x[0])
    if isfinite(distance) and distance > 0:
      if closest is None or distance < closest:
        closest = distance
        velocity = float(lead.v[0]) if hasattr(lead, "v") and len(lead.v) else float("nan")
        closest_speed = velocity if isfinite(velocity) else None
  if radar_state is not None:
    radar_lead = radar_state.leadOne
    if bool(getattr(radar_lead, "status", False)):
      distance = float(getattr(radar_lead, "dRel", float("nan")))
      velocity = float(getattr(radar_lead, "vLead", float("nan")))
      if not isfinite(velocity):
        relative_velocity = float(getattr(radar_lead, "vRel", float("nan")))
        velocity = v_ego + relative_velocity if isfinite(relative_velocity) else float("nan")
      if isfinite(distance) and distance > 0 and (closest is None or distance < closest):
        probability = 1.0
        closest = distance
        closest_speed = velocity if isfinite(velocity) else None
  close_horizon_m = max(10.0, max(0.0, v_ego) * 3.0)
  return probability, closest, closest_speed, closest is not None and closest <= close_horizon_m


def _message_age_s(now_ns: int, log_mono_time: int) -> float:
  return max(0.0, (now_ns - log_mono_time) / 1e9) if log_mono_time > 0 else float("inf")


def _adjacent_lane_available(inner_y: float | None, outer_y: float | None, inner_probability: float,
                             outer_probability: float) -> bool:
  if inner_y is None or outer_y is None or not all(isfinite(value) for value in (inner_y, outer_y)):
    return False
  width = abs(outer_y - inner_y)
  return (inner_probability >= ADJACENT_LANE_PROBABILITY_THRESHOLD and
          outer_probability >= ADJACENT_LANE_PROBABILITY_THRESHOLD and
          ADJACENT_LANE_WIDTH_MIN_M <= width <= ADJACENT_LANE_WIDTH_MAX_M)


def _is_exact_ascent_2023(params: Params) -> bool:
  raw = params.get("CarParams")
  if not raw:
    return False
  try:
    with car.CarParams.from_bytes(raw) as car_params:
      return car_params.carFingerprint == str(CAR.SUBARU_ASCENT_2023)
  except Exception:
    return False


def evaluate_shadow(car_state, model, *, controls_state=None, car_control=None,
                    radar_state=None,
                    model_age_s: float = 0.0, car_state_age_s: float = 0.0,
                    controls_age_s: float = 0.0, radar_age_s: float = 0.0,
                    curve_envelope: CurveEnvelope | None = None,
                    traffic_control_shadow: TrafficControlShadow | None = None,
                    pass_adviser: PassAdviser | None = None,
                    traffic_control_enabled: bool = True, pass_adviser_enabled: bool = True) -> dict:
  x = _float_list(model.position.x)
  y = _float_list(model.position.y)
  velocity = _float_list(model.velocity.x)
  acceleration = _float_list(model.acceleration.x)
  times = _float_list(model.position.t)
  yaw_rates = _float_list(model.orientationRate.z)
  count = min(len(x), len(y), len(velocity), len(acceleration))
  curvatures = [(float("nan") if not isfinite(_value(yaw_rates, i)) or not isfinite(velocity[i]) else
                 _value(yaw_rates, i) / velocity[i] if abs(velocity[i]) > 0.5 else 0.0) for i in range(count)]
  points = [TrajectoryPoint(_value(times, i), x[i], y[i], velocity[i], acceleration[i], curvatures[i]) for i in range(count)]

  road_edge_stds = _float_list(model.roadEdgeStds)
  road_edges = model.roadEdges
  edge_y = [(float(road_edges[index].y[0]) if index < len(road_edges) and len(road_edges[index].y) else float("nan"))
            for index in range(2)]
  edge_geometry_present = all(isfinite(value) for value in edge_y)
  left_road_edge = isfinite(edge_y[0]) and abs(edge_y[0]) < 1.5
  right_road_edge = isfinite(edge_y[1]) and abs(edge_y[1]) < 1.5
  road_edge = left_road_edge or right_road_edge
  edge_confident = len(road_edge_stds) >= 2 and all(isfinite(value) for value in road_edge_stds[:2]) and max(road_edge_stds[:2]) < 0.7
  road_clear = edge_geometry_present and edge_confident and not road_edge
  bsm_fresh = car_state_age_s <= SOURCE_FRESH_S
  lead_probability, lead_distance_m, lead_speed_mps, close_object = _lead_observation(model, float(car_state.vEgo), radar_state)
  classifier = UnknownSpaceClassifier()
  space = classifier.classify(RegionEvidence(
    visible_recently=edge_geometry_present,
    object_present=close_object,
    bsm_occupied=bool(car_state.leftBlindspot or car_state.rightBlindspot),
    bsm_fresh=bsm_fresh,
    road_edge=road_edge,
    contradictory=False,
    age_s=max(model_age_s, car_state_age_s),
  ))
  left_space = classifier.classify(RegionEvidence(edge_geometry_present, False, bool(car_state.leftBlindspot),
                                                   bsm_fresh, left_road_edge, False, max(model_age_s, car_state_age_s)))
  right_space = classifier.classify(RegionEvidence(edge_geometry_present, False, bool(car_state.rightBlindspot),
                                                    bsm_fresh, right_road_edge, False, max(model_age_s, car_state_age_s)))

  lane_lines = model.laneLines
  lane_probs = _float_list(model.laneLineProbs)
  left_y = float(lane_lines[1].y[0]) if len(lane_lines) > 2 and len(lane_lines[1].y) else None
  right_y = float(lane_lines[2].y[0]) if len(lane_lines) > 2 and len(lane_lines[2].y) else None
  left_outer_y = float(lane_lines[0].y[0]) if len(lane_lines) > 3 and len(lane_lines[0].y) else None
  right_outer_y = float(lane_lines[3].y[0]) if len(lane_lines) > 3 and len(lane_lines[3].y) else None
  left_adjacent_lane = _adjacent_lane_available(left_y, left_outer_y, _value(lane_probs, 1, 0.0),
                                                _value(lane_probs, 0, 0.0))
  right_adjacent_lane = _adjacent_lane_available(right_y, right_outer_y, _value(lane_probs, 2, 0.0),
                                                 _value(lane_probs, 3, 0.0))
  model_path_y = y[0] if y and isfinite(y[0]) else 0.0
  lane = LanePositionShadow().evaluate(LanePositionInput(
    model_path_y_m=model_path_y,
    left_lane_y_m=left_y,
    right_lane_y_m=right_y,
    left_lane_probability=_value(lane_probs, 1, 0.0),
    right_lane_probability=_value(lane_probs, 2, 0.0),
    road_edge_clear=road_clear,
    source_age_s=model_age_s,
  ))
  sources_fresh = max(model_age_s, car_state_age_s, controls_age_s) <= SOURCE_FRESH_S
  supervisor = TrajectorySupervisor()
  trajectory = supervisor.evaluate(points, road_clear, classifier.trajectory_allowed([space]), sources_fresh)
  trajectory_geometry_valid = (trajectory.verdict.value == "VALID" or
                               (trajectory.verdict.value == "FALLBACK_REQUIRED" and
                                set(trajectory.reasons) == {"occupancy_not_clear"}))

  envelope = curve_envelope or CurveEnvelope()
  controller_curvature = float(controls_state.curvature) if controls_state is not None else 0.0
  lateral_accel = abs(controller_curvature) * float(car_state.vEgo) ** 2
  envelope.observe_controller(bool(car_control is not None and car_control.latActive), _controller_saturated(controls_state),
                              lateral_accel, sources_fresh)
  finite_curvatures = [abs(value) for value in curvatures if isfinite(value)]
  peak_curvature = max(finite_curvatures, default=0.0)
  predicted_max_lateral_accel = max((abs(curvature) * velocity[index] ** 2 for index, curvature in enumerate(curvatures)
                                     if isfinite(curvature) and isfinite(velocity[index])), default=0.0)
  curve_target_speed = envelope.target_speed(peak_curvature, "AUTO")

  action = model.action
  candidate_accel = float(action.desiredAcceleration)
  candidate_curvature = float(action.desiredCurvature)
  guard = FinalCommandShadowGuard().project(GuardInput(candidate_accel, candidate_curvature, float(car_state.aEgo),
                                                       curvature_abs_cap=supervisor.limits.max_abs_curvature))
  finite_x = [value for value in x if isfinite(value)]
  finite_velocity = [value for value in velocity if isfinite(value)]
  model_path_length_m = max(0.0, finite_x[-1] - finite_x[0]) if len(finite_x) >= 2 else float("nan")
  model_terminal_speed_mps = finite_velocity[-1] if finite_velocity else float("nan")
  traffic = (traffic_control_shadow or TrafficControlShadow()).update(TrafficControlInput(
    enabled=traffic_control_enabled,
    model_should_stop=bool(getattr(action, "shouldStop", False)),
    desired_accel_mps2=candidate_accel,
    ego_speed_mps=float(car_state.vEgo),
    model_path_length_m=model_path_length_m,
    model_terminal_speed_mps=model_terminal_speed_mps,
    lead_probability=lead_probability,
    lead_distance_m=lead_distance_m,
    peak_curvature=peak_curvature,
    source_fresh=sources_fresh,
    trajectory_valid=trajectory_geometry_valid,
  ))
  lead_source_fresh = model_age_s <= SOURCE_FRESH_S and (radar_state is None or radar_age_s <= SOURCE_FRESH_S)
  pass_advice = (pass_adviser or PassAdviser()).update(PassInput(
    enabled=pass_adviser_enabled,
    ego_speed_mps=float(car_state.vEgo),
    lead_distance_m=lead_distance_m,
    lead_speed_mps=lead_speed_mps,
    left_space=left_space,
    left_adjacent_lane_geometry=left_adjacent_lane,
    left_blinker=bool(getattr(car_state, "leftBlinker", False)),
    lane_confidence=lane.lane_confidence,
    source_fresh=sources_fresh and lead_source_fresh,
    trajectory_valid=trajectory_geometry_valid,
  ))
  return {
    "can_actuate": False,
    "model_frame_id": int(model.frameId),
    "model_big": bool(model.big),
    "model_age_s": model_age_s,
    "car_state_age_s": car_state_age_s,
    "controls_age_s": controls_age_s,
    "source_fresh": sources_fresh,
    "space": space.value,
    "left_space": left_space.value,
    "right_space": right_space.value,
    "left_adjacent_lane_geometry": left_adjacent_lane,
    "right_adjacent_lane_geometry": right_adjacent_lane,
    "lead_probability": lead_probability,
    "lead_distance_m": lead_distance_m,
    "lead_speed_mps": lead_speed_mps,
    "trajectory": trajectory.verdict.value,
    "trajectory_reasons": list(trajectory.reasons),
    "lane_candidate_y_m": lane.blended_path_y_m,
    "lane_trim_m": lane.blended_path_y_m - model_path_y,
    "lane_confidence": lane.lane_confidence,
    "lane_reasons": list(lane.reasons),
    "peak_curvature": peak_curvature,
    "predicted_max_lateral_accel": predicted_max_lateral_accel,
    "curve_capability": envelope.steering_capability,
    "curve_target_speed_mps": curve_target_speed,
    "guard_accel": guard.corrected_accel,
    "guard_curvature": guard.corrected_curvature,
    "guard_reasons": list(guard.reasons),
    "model_stop_prediction": traffic.model_stop_prediction,
    "model_stop_enabled": traffic_control_enabled,
    "model_stop_raw_candidate": traffic.raw_candidate,
    "model_stop_confidence": traffic.confidence,
    "model_stop_reasons": list(traffic.reasons),
    "model_path_length_m": model_path_length_m,
    "model_terminal_speed_mps": model_terminal_speed_mps,
    "left_lane_geometry_ready": pass_advice.left_lane_geometry_ready,
    "lane_change_evidence_enabled": pass_adviser_enabled,
    "driver_left_lane_change_candidate": pass_advice.driver_left_lane_change_candidate,
    "lane_change_evidence_reasons": list(pass_advice.reasons),
    "automatic_pass": False,
  }


def main() -> None:
  sm = messaging.SubMaster(["carState", "modelV2", "controlsState", "carControl", "carOutput", "radarState",
                            "longitudinalPlan"])
  params = Params()
  curve_envelope = CurveEnvelope()
  traffic_control_shadow = TrafficControlShadow()
  pass_adviser = PassAdviser()
  telemetry = ShadowTelemetry()
  last_status_s = 0.0
  last_log_s = 0.0
  last_fingerprint: tuple | None = None
  exact_vehicle = False
  calibration_recorder: CalibrationRecorder | None = None
  last_calibration_error_s = 0.0
  while True:
    sm.update(1000)
    if not exact_vehicle:
      exact_vehicle = _is_exact_ascent_2023(params)
      if not exact_vehicle:
        continue
      calibration_recorder = CalibrationRecorder(params)
    if sm.updated["modelV2"] and sm.alive["carState"] and sm.valid["carState"] and sm.valid["modelV2"]:
      now_ns = time.monotonic_ns()
      now_s = now_ns / 1e9
      try:
        result = evaluate_shadow(
          sm["carState"], sm["modelV2"],
          controls_state=sm["controlsState"] if sm.valid["controlsState"] else None,
          car_control=sm["carControl"] if sm.valid["carControl"] else None,
          radar_state=sm["radarState"] if sm.valid["radarState"] else None,
          model_age_s=_message_age_s(now_ns, sm.logMonoTime["modelV2"]),
          car_state_age_s=_message_age_s(now_ns, sm.logMonoTime["carState"]),
          controls_age_s=_message_age_s(now_ns, sm.logMonoTime["controlsState"]),
          radar_age_s=_message_age_s(now_ns, sm.logMonoTime["radarState"]),
          curve_envelope=curve_envelope,
          traffic_control_shadow=traffic_control_shadow,
          pass_adviser=pass_adviser,
          traffic_control_enabled=params.get_bool("AscentV8TrafficControlShadowEnabled"),
          pass_adviser_enabled=params.get_bool("AscentV8LaneChangeEvidenceEnabled"),
        )
        telemetry.observe(result)
        if (calibration_recorder is not None and sm.valid["carControl"] and sm.valid["carOutput"] and
            sm.valid["longitudinalPlan"]):
          try:
            sample = build_calibration_sample(
              sm["carState"], sm["modelV2"], sm["carControl"], sm["carOutput"], sm["longitudinalPlan"],
              shadow=result, monotonic_ns=now_ns,
            )
            calibration_recorder.record(sample, now_ns)
          except Exception:
            if now_s - last_calibration_error_s >= LOG_HEARTBEAT_S:
              cloudlog.exception("Ascent V8 calibration recorder failed")
              last_calibration_error_s = now_s
        fingerprint = (result["trajectory"], result["space"], tuple(result["trajectory_reasons"]),
                       tuple(result["lane_reasons"]), result["model_big"], result["model_stop_prediction"],
                       result["driver_left_lane_change_candidate"])
        transition_due = fingerprint != last_fingerprint and now_s - last_log_s >= LOG_TRANSITION_MIN_S
        if transition_due or now_s - last_log_s >= LOG_HEARTBEAT_S:
          cloudlog.info("Ascent V8 shadow: %s", json.dumps(result, sort_keys=True))
          last_log_s = now_s
          last_fingerprint = fingerprint
        if now_s - last_status_s >= STATUS_INTERVAL_S:
          params.put("AscentV8ShadowStatus", telemetry.snapshot())
          last_status_s = now_s
      except Exception as error:
        telemetry.observe_error(error)
        cloudlog.exception("Ascent V8 shadow evaluation failed closed")
        if now_s - last_status_s >= STATUS_INTERVAL_S:
          params.put("AscentV8ShadowStatus", telemetry.snapshot())
          last_status_s = now_s


if __name__ == "__main__":
  main()
