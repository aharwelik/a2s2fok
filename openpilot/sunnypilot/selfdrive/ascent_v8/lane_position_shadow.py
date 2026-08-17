from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class LanePositionInput:
  model_path_y_m: float
  left_lane_y_m: float | None
  right_lane_y_m: float | None
  left_lane_probability: float
  right_lane_probability: float
  road_edge_clear: bool
  source_age_s: float


@dataclass(frozen=True)
class LanePositionShadowResult:
  blended_path_y_m: float
  lane_confidence: float
  reasons: tuple[str, ...]
  can_actuate: bool = False


class LanePositionShadow:
  """Compute a bounded lane-position candidate without touching the live path."""
  def __init__(self, max_source_age_s: float = 0.5, max_trim_m: float = 0.35):
    self.max_source_age_s = max_source_age_s
    self.max_trim_m = max_trim_m

  def evaluate(self, inputs: LanePositionInput) -> LanePositionShadowResult:
    reasons: list[str] = []
    probabilities = (inputs.left_lane_probability, inputs.right_lane_probability)
    confidence = min(probabilities) if all(isfinite(value) for value in probabilities) else 0.0
    values = (inputs.model_path_y_m, inputs.left_lane_y_m, inputs.right_lane_y_m)
    if any(value is None or not isfinite(value) for value in values):
      reasons.append("lane_geometry_missing")
    if not all(isfinite(value) for value in probabilities):
      reasons.append("lane_confidence_invalid")
    if inputs.source_age_s > self.max_source_age_s:
      reasons.append("source_stale")
    if not inputs.road_edge_clear:
      reasons.append("road_edge_veto")
    if confidence < 0.5:
      reasons.append("lane_confidence_low")
    if reasons:
      return LanePositionShadowResult(inputs.model_path_y_m, confidence, tuple(reasons))

    lane_center = (float(inputs.left_lane_y_m) + float(inputs.right_lane_y_m)) / 2.0
    confidence_weight = min(1.0, max(0.0, (confidence - 0.5) / 0.5))
    trim = confidence_weight * (lane_center - inputs.model_path_y_m)
    trim = max(-self.max_trim_m, min(self.max_trim_m, trim))
    return LanePositionShadowResult(inputs.model_path_y_m + trim, confidence, ())
