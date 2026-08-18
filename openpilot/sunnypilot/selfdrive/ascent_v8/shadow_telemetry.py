from collections import Counter
from math import isfinite
import time


def _json_safe(value):
  if isinstance(value, float):
    return round(value, 5) if isfinite(value) else None
  if isinstance(value, dict):
    return {key: _json_safe(item) for key, item in value.items()}
  if isinstance(value, (list, tuple)):
    return [_json_safe(item) for item in value]
  return value


class ShadowTelemetry:
  def __init__(self, started_monotonic_s: float | None = None):
    self.started_monotonic_s = started_monotonic_s if started_monotonic_s is not None else time.monotonic()
    self.evaluations = 0
    self.errors = 0
    self.trajectory_counts: Counter[str] = Counter()
    self.space_counts: Counter[str] = Counter()
    self.reason_counts: Counter[str] = Counter()
    self.model_stop_predictions = 0
    self.model_stop_raw_candidates = 0
    self.left_lane_geometry_ready_samples = 0
    self.driver_left_lane_change_candidates = 0
    self.last: dict = {}
    self.last_error: str | None = None

  def observe(self, result: dict) -> None:
    self.evaluations += 1
    self.trajectory_counts[str(result["trajectory"])] += 1
    self.space_counts[str(result["space"])] += 1
    for key in ("trajectory_reasons", "lane_reasons", "guard_reasons", "model_stop_reasons", "lane_change_evidence_reasons"):
      self.reason_counts.update(str(reason) for reason in result.get(key, ()))
    self.model_stop_predictions += int(bool(result.get("model_stop_prediction")))
    self.model_stop_raw_candidates += int(bool(result.get("model_stop_raw_candidate")))
    self.left_lane_geometry_ready_samples += int(bool(result.get("left_lane_geometry_ready")))
    self.driver_left_lane_change_candidates += int(bool(result.get("driver_left_lane_change_candidate")))
    self.last = _json_safe(result)

  def observe_error(self, error: Exception) -> None:
    self.errors += 1
    self.last_error = f"{type(error).__name__}: {error}"[:240]

  def snapshot(self, updated_monotonic_s: float | None = None) -> dict:
    updated = updated_monotonic_s if updated_monotonic_s is not None else time.monotonic()
    return {
      "schema": 2,
      "started_monotonic_s": round(self.started_monotonic_s, 3),
      "updated_monotonic_s": round(updated, 3),
      "runtime_s": round(max(0.0, updated - self.started_monotonic_s), 3),
      "evaluations": self.evaluations,
      "errors": self.errors,
      "trajectory_counts": dict(self.trajectory_counts),
      "space_counts": dict(self.space_counts),
      "reason_counts": dict(self.reason_counts.most_common(12)),
      "model_stop_predictions": self.model_stop_predictions,
      "model_stop_raw_candidates": self.model_stop_raw_candidates,
      "left_lane_geometry_ready_samples": self.left_lane_geometry_ready_samples,
      "driver_left_lane_change_candidates": self.driver_left_lane_change_candidates,
      "last_error": self.last_error,
      "last": self.last,
    }
