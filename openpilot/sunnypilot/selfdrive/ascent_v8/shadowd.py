#!/usr/bin/env python3
from __future__ import annotations

import json
from math import isfinite
import time

import openpilot.cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.selfdrive.ascent_v8.adaptive_curve import CurveEnvelope
from openpilot.sunnypilot.selfdrive.ascent_v8.lane_position_shadow import LanePositionInput, LanePositionShadow
from openpilot.sunnypilot.selfdrive.ascent_v8.safety_guard import FinalCommandShadowGuard, GuardInput
from openpilot.sunnypilot.selfdrive.ascent_v8.shadow_telemetry import ShadowTelemetry
from openpilot.sunnypilot.selfdrive.ascent_v8.trajectory_supervisor import TrajectoryPoint, TrajectorySupervisor
from openpilot.sunnypilot.selfdrive.ascent_v8.unknown_space import RegionEvidence, UnknownSpaceClassifier


STATUS_INTERVAL_S = 1.0
LOG_HEARTBEAT_S = 5.0
LOG_TRANSITION_MIN_S = 1.0
SOURCE_FRESH_S = 0.5
LEAD_PROBABILITY_THRESHOLD = 0.5


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


def _lead_observation(model, v_ego: float) -> tuple[float, float | None, bool]:
  probability = 0.0
  closest: float | None = None
  for lead in model.leadsV3:
    lead_probability = float(lead.prob)
    if not isfinite(lead_probability):
      continue
    probability = max(probability, lead_probability)
    if lead_probability < LEAD_PROBABILITY_THRESHOLD or not len(lead.x):
      continue
    distance = float(lead.x[0])
    if isfinite(distance) and distance > 0:
      closest = distance if closest is None else min(closest, distance)
  close_horizon_m = max(10.0, max(0.0, v_ego) * 3.0)
  return probability, closest, closest is not None and closest <= close_horizon_m


def _message_age_s(now_ns: int, log_mono_time: int) -> float:
  return max(0.0, (now_ns - log_mono_time) / 1e9) if log_mono_time > 0 else float("inf")


def evaluate_shadow(car_state, model, *, controls_state=None, car_control=None,
                    model_age_s: float = 0.0, car_state_age_s: float = 0.0,
                    controls_age_s: float = 0.0, curve_envelope: CurveEnvelope | None = None) -> dict:
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
  lead_probability, lead_distance_m, close_object = _lead_observation(model, float(car_state.vEgo))
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
    "lead_probability": lead_probability,
    "lead_distance_m": lead_distance_m,
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
  }


def main() -> None:
  sm = messaging.SubMaster(["carState", "modelV2", "controlsState", "carControl"])
  params = Params()
  curve_envelope = CurveEnvelope()
  telemetry = ShadowTelemetry()
  last_status_s = 0.0
  last_log_s = 0.0
  last_fingerprint: tuple | None = None
  while True:
    sm.update(1000)
    if sm.updated["modelV2"] and sm.alive["carState"] and sm.valid["carState"] and sm.valid["modelV2"]:
      now_ns = time.monotonic_ns()
      now_s = now_ns / 1e9
      try:
        result = evaluate_shadow(
          sm["carState"], sm["modelV2"],
          controls_state=sm["controlsState"] if sm.valid["controlsState"] else None,
          car_control=sm["carControl"] if sm.valid["carControl"] else None,
          model_age_s=_message_age_s(now_ns, sm.logMonoTime["modelV2"]),
          car_state_age_s=_message_age_s(now_ns, sm.logMonoTime["carState"]),
          controls_age_s=_message_age_s(now_ns, sm.logMonoTime["controlsState"]),
          curve_envelope=curve_envelope,
        )
        telemetry.observe(result)
        fingerprint = (result["trajectory"], result["space"], tuple(result["trajectory_reasons"]),
                       tuple(result["lane_reasons"]), result["model_big"])
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
