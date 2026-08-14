from __future__ import annotations

import numpy as np

from openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.estimator import RuntimeContext, StopObstacleMode, StopTarget


def constant_distance_vector(distance_m: float, count: int = 13) -> np.ndarray:
  return np.full(count, float(distance_m))


def select_shadow_or_simulation_obstacle(
  mode: StopObstacleMode,
  runtime: RuntimeContext,
  target: StopTarget,
  existing_obstacles: list[np.ndarray],
) -> tuple[np.ndarray | None, bool]:
  if not target.valid:
    return None, False

  obstacle_count = len(existing_obstacles[0]) if existing_obstacles else 13
  stop_obstacle = constant_distance_vector(target.distance_m, obstacle_count)
  if mode == StopObstacleMode.LIVE_SHADOW:
    return stop_obstacle, False

  if mode == StopObstacleMode.REPLAY_SIMULATION:
    if not runtime.simulation_actuation_allowed:
      raise RuntimeError("stop obstacle simulation requested without non-live runtime proof")
    if not existing_obstacles:
      return stop_obstacle, True
    return np.minimum.reduce([*existing_obstacles, stop_obstacle]), True

  return None, False
