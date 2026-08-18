from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class TrajectoryVerdict(StrEnum):
  VALID = "VALID"
  CORRECTED = "CORRECTED"
  REJECTED = "REJECTED"
  FALLBACK_REQUIRED = "FALLBACK_REQUIRED"


@dataclass(frozen=True)
class TrajectoryPoint:
  t: float
  x: float
  y: float
  v: float
  a: float
  curvature: float


@dataclass(frozen=True)
class SupervisorLimits:
  max_accel: float = 2.0
  min_accel: float = -3.5
  max_abs_curvature: float = 0.20
  max_abs_jerk: float = 4.0


@dataclass(frozen=True)
class SupervisorResult:
  verdict: TrajectoryVerdict
  reasons: tuple[str, ...]


class TrajectorySupervisor:
  def __init__(self, limits: SupervisorLimits | None = None):
    self.limits = limits or SupervisorLimits()

  def evaluate(self, points: list[TrajectoryPoint], road_ok: bool, occupancy_clear: bool, sources_fresh: bool) -> SupervisorResult:
    reasons: list[str] = []
    if not sources_fresh:
      reasons.append("stale_sources")
    if not road_ok:
      reasons.append("road_boundary")
    if not occupancy_clear:
      reasons.append("occupancy_not_clear")
    if len(points) < 2:
      reasons.append("short_trajectory")

    previous: TrajectoryPoint | None = None
    for point in points:
      if not all(isfinite(value) for value in (point.t, point.x, point.y, point.v, point.a, point.curvature)):
        reasons.append("nonfinite")
        break
      if point.a > self.limits.max_accel or point.a < self.limits.min_accel:
        reasons.append("accel_limit")
      if abs(point.curvature) > self.limits.max_abs_curvature:
        reasons.append("curvature_limit")
      if previous is not None:
        dt = point.t - previous.t
        if dt <= 0:
          reasons.append("time_order")
        elif abs((point.a - previous.a) / dt) > self.limits.max_abs_jerk:
          reasons.append("jerk_limit")
        if point.x < previous.x:
          reasons.append("x_order")
      previous = point

    unique_reasons = tuple(dict.fromkeys(reasons))
    if not unique_reasons:
      return SupervisorResult(TrajectoryVerdict.VALID, ())
    if any(reason in unique_reasons for reason in ("stale_sources", "road_boundary", "occupancy_not_clear", "nonfinite")):
      return SupervisorResult(TrajectoryVerdict.FALLBACK_REQUIRED, unique_reasons)
    return SupervisorResult(TrajectoryVerdict.REJECTED, unique_reasons)
