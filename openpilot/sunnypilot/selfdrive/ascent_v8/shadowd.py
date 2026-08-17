#!/usr/bin/env python3
from __future__ import annotations

import json
from math import isfinite

import openpilot.cereal.messaging as messaging
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.selfdrive.ascent_v8.lane_position_shadow import LanePositionInput, LanePositionShadow
from openpilot.sunnypilot.selfdrive.ascent_v8.safety_guard import FinalCommandShadowGuard, GuardInput
from openpilot.sunnypilot.selfdrive.ascent_v8.trajectory_supervisor import TrajectoryPoint, TrajectorySupervisor
from openpilot.sunnypilot.selfdrive.ascent_v8.unknown_space import RegionEvidence, UnknownSpaceClassifier


def _finite_list(values) -> list[float]:
  return [float(value) for value in values if isfinite(value)]


def evaluate_shadow(car_state, model) -> dict:
  x = _finite_list(model.position.x)
  y = _finite_list(model.position.y)
  velocity = _finite_list(model.velocity.x)
  acceleration = _finite_list(model.acceleration.x)
  count = min(len(x), len(y), len(velocity), len(acceleration))
  points = [TrajectoryPoint(i * 0.05, x[i], y[i], velocity[i], acceleration[i], 0.0) for i in range(count)]

  road_edge_stds = _finite_list(model.roadEdgeStds)
  road_edges = model.roadEdges
  edge_y = [float(road_edges[index].y[0]) for index in range(min(2, len(road_edges)))
            if len(road_edges[index].y) and isfinite(road_edges[index].y[0])]
  edge_geometry_present = len(edge_y) == 2
  road_edge = edge_geometry_present and min(abs(value) for value in edge_y) < 1.5
  road_clear = edge_geometry_present and len(road_edge_stds) >= 2 and max(road_edge_stds[:2]) < 0.7 and not road_edge
  bsm_occupied = bool(car_state.leftBlindspot or car_state.rightBlindspot)
  space = UnknownSpaceClassifier().classify(RegionEvidence(
    visible_recently=edge_geometry_present,
    object_present=False,
    bsm_occupied=bsm_occupied,
    bsm_fresh=True,
    road_edge=road_edge,
    contradictory=False,
    age_s=0.0,
  ))

  lane_lines = model.laneLines
  lane_probs = _finite_list(model.laneLineProbs)
  left_y = float(lane_lines[1].y[0]) if len(lane_lines) > 2 and len(lane_lines[1].y) else None
  right_y = float(lane_lines[2].y[0]) if len(lane_lines) > 2 and len(lane_lines[2].y) else None
  lane = LanePositionShadow().evaluate(LanePositionInput(
    model_path_y_m=y[0] if y else 0.0,
    left_lane_y_m=left_y,
    right_lane_y_m=right_y,
    left_lane_probability=lane_probs[1] if len(lane_probs) > 2 else 0.0,
    right_lane_probability=lane_probs[2] if len(lane_probs) > 2 else 0.0,
    road_edge_clear=road_clear,
    source_age_s=0.0,
  ))
  trajectory = TrajectorySupervisor().evaluate(points, road_clear, UnknownSpaceClassifier.trajectory_allowed([space]), True)
  candidate_accel = acceleration[0] if acceleration else 0.0
  guard = FinalCommandShadowGuard().project(GuardInput(candidate_accel, 0.0, float(car_state.aEgo)))
  return {
    "can_actuate": False,
    "space": space.value,
    "trajectory": trajectory.verdict.value,
    "trajectory_reasons": list(trajectory.reasons),
    "lane_candidate_y_m": lane.blended_path_y_m,
    "lane_reasons": list(lane.reasons),
    "guard_accel": guard.corrected_accel,
    "guard_reasons": list(guard.reasons),
  }


def main() -> None:
  sm = messaging.SubMaster(["carState", "modelV2"])
  while True:
    sm.update(1000)
    if sm.updated["modelV2"] and sm.alive["carState"] and sm.valid["carState"] and sm.valid["modelV2"]:
      try:
        cloudlog.info("Ascent V8 shadow: %s", json.dumps(evaluate_shadow(sm["carState"], sm["modelV2"]), sort_keys=True))
      except Exception:
        cloudlog.exception("Ascent V8 shadow evaluation failed closed")


if __name__ == "__main__":
  main()
