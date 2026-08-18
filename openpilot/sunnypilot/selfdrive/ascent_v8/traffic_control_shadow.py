from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TrafficControlInput:
  enabled: bool
  model_should_stop: bool
  desired_accel_mps2: float
  ego_speed_mps: float
  model_path_length_m: float
  model_terminal_speed_mps: float
  lead_probability: float
  lead_distance_m: float | None
  peak_curvature: float
  source_fresh: bool
  trajectory_valid: bool


@dataclass(frozen=True)
class TrafficControlEvidence:
  model_stop_prediction: bool
  raw_candidate: bool
  confidence: float
  reasons: tuple[str, ...]
  asserted_frames: int
  clear_frames: int
  can_actuate: bool = False


class TrafficControlShadow:
  """Debounces model stopping intent without claiming sign or signal classification."""

  ASSERT_FRAMES = 7
  CLEAR_FRAMES = 5
  MAX_SPEED_MPS = 33.5
  MAX_CURVATURE = 0.045
  STOP_TIME_S = 6.0
  PATH_ON_MARGIN_M = 2.5
  PATH_OFF_MARGIN_M = 4.0
  TERMINAL_SPEED_MPS = 2.0
  LEAD_BLOCK_MARGIN_M = 15.0

  def __init__(self):
    self._asserted_frames = 0
    self._clear_frames = 0
    self._active = False
    self._confidence = 0.0

  def update(self, inputs: TrafficControlInput) -> TrafficControlEvidence:
    if not inputs.enabled:
      self._asserted_frames = 0
      self._clear_frames = 0
      self._active = False
      self._confidence = 0.0
      return TrafficControlEvidence(False, False, 0.0, ("disabled",), 0, 0)

    reasons: list[str] = []
    finite = all(isfinite(value) for value in (
      inputs.desired_accel_mps2, inputs.ego_speed_mps, inputs.model_path_length_m,
      inputs.model_terminal_speed_mps, inputs.lead_probability, inputs.peak_curvature,
    ))
    if not finite:
      reasons.append("nonfinite")
    if not inputs.source_fresh:
      reasons.append("stale_sources")
    if not inputs.trajectory_valid:
      reasons.append("trajectory_invalid")
    if inputs.ego_speed_mps < 0.5:
      reasons.append("standstill")
    if inputs.ego_speed_mps > self.MAX_SPEED_MPS:
      reasons.append("speed_veto")
    if inputs.peak_curvature > self.MAX_CURVATURE:
      reasons.append("curve_veto")

    stop_distance = max(0.0, inputs.ego_speed_mps) * self.STOP_TIME_S
    path_margin = self.PATH_OFF_MARGIN_M if self._active else -self.PATH_ON_MARGIN_M
    short_stopping_path = (inputs.model_path_length_m < max(0.0, stop_distance + path_margin) and
                           inputs.model_terminal_speed_mps <= self.TERMINAL_SPEED_MPS and
                           inputs.desired_accel_mps2 < -0.1)

    lead_relevant = (inputs.lead_distance_m is not None and inputs.lead_probability >= 0.5 and
                     inputs.lead_distance_m < stop_distance + self.LEAD_BLOCK_MARGIN_M)
    if lead_relevant:
      reasons.append("lead_veto")

    should_stop_corroborated = (inputs.model_should_stop and
                                (inputs.desired_accel_mps2 < -0.1 or
                                 inputs.model_terminal_speed_mps <= self.TERMINAL_SPEED_MPS or short_stopping_path))
    model_intent = should_stop_corroborated or short_stopping_path
    if not model_intent:
      reasons.append("uncorroborated_should_stop" if inputs.model_should_stop else "no_model_stop_intent")

    hard_veto = bool(reasons and any(reason in reasons for reason in (
      "nonfinite", "stale_sources", "trajectory_invalid", "standstill", "speed_veto", "curve_veto", "lead_veto",
    )))
    raw_candidate = bool(model_intent and not hard_veto)

    if hard_veto:
      self._asserted_frames = 0
      self._clear_frames += 1
      self._active = False
      self._confidence = 0.0
    elif raw_candidate:
      self._asserted_frames += 1
      self._clear_frames = 0
      if self._asserted_frames >= self.ASSERT_FRAMES:
        self._active = True
    else:
      self._asserted_frames = 0
      self._clear_frames += 1
      if self._clear_frames >= self.CLEAR_FRAMES:
        self._active = False
        self._confidence = 0.0

    confidence = 0.0
    if raw_candidate:
      confidence = 0.55
      confidence += 0.25 if should_stop_corroborated else 0.0
      confidence += 0.1 if short_stopping_path else 0.0
      confidence += 0.1 if inputs.desired_accel_mps2 <= -0.5 else 0.0
      self._confidence = min(confidence, 1.0)
    elif self._active:
      confidence = self._confidence
      reasons.append("debounce_hold")

    return TrafficControlEvidence(
      model_stop_prediction=self._active,
      raw_candidate=raw_candidate,
      confidence=min(confidence, 1.0),
      reasons=tuple(reasons),
      asserted_frames=self._asserted_frames,
      clear_frames=self._clear_frames,
    )
