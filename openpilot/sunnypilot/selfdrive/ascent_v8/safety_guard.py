from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class GuardInput:
  candidate_accel: float
  candidate_curvature: float
  actual_accel: float
  speed_limit_accel_cap: float | None = None
  collision_accel_cap: float | None = None
  red_light_accel_cap: float | None = None
  curvature_abs_cap: float | None = None


@dataclass(frozen=True)
class GuardOutput:
  corrected_accel: float
  corrected_curvature: float
  reasons: tuple[str, ...]


class FinalCommandShadowGuard:
  def project(self, candidate: GuardInput) -> GuardOutput:
    if not all(isfinite(value) for value in (candidate.candidate_accel, candidate.candidate_curvature, candidate.actual_accel)):
      return GuardOutput(0.0, 0.0, ("nonfinite",))

    accel = candidate.candidate_accel
    reasons: list[str] = []
    caps = (("speed_limit", candidate.speed_limit_accel_cap),
            ("collision", candidate.collision_accel_cap),
            ("red_light", candidate.red_light_accel_cap))
    for name, cap in caps:
      if cap is not None:
        bounded = min(cap, candidate.actual_accel)
        if accel > bounded:
          accel = bounded
          reasons.append(name)

    curvature = candidate.candidate_curvature
    if candidate.curvature_abs_cap is not None and abs(curvature) > candidate.curvature_abs_cap:
      curvature = max(-candidate.curvature_abs_cap, min(candidate.curvature_abs_cap, curvature))
      reasons.append("curvature")
    return GuardOutput(accel, curvature, tuple(reasons))
