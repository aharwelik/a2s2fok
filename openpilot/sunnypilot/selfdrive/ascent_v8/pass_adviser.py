from dataclasses import dataclass
from math import isfinite

from openpilot.sunnypilot.selfdrive.ascent_v8.unknown_space import SpaceState


@dataclass(frozen=True)
class PassInput:
  enabled: bool
  ego_speed_mps: float
  lead_distance_m: float | None
  lead_speed_mps: float | None
  left_space: SpaceState
  left_adjacent_lane_geometry: bool
  left_blinker: bool
  lane_confidence: float
  source_fresh: bool
  trajectory_valid: bool


@dataclass(frozen=True)
class PassAdvice:
  left_lane_geometry_ready: bool
  driver_left_lane_change_candidate: bool
  reasons: tuple[str, ...]
  ready_frames: int
  can_actuate: bool = False
  automatic_blinker: bool = False


class PassAdviser:
  """Evidence for a driver-commanded controlled-lot obstacle bypass."""

  MIN_SPEED_MPS = 8.9
  MIN_SPEED_DELTA_MPS = 1.5
  MIN_LANE_CONFIDENCE = 0.55
  ASSERT_FRAMES = 3

  def __init__(self):
    self._ready_frames = 0
    self._ready = False

  def update(self, inputs: PassInput) -> PassAdvice:
    if not inputs.enabled:
      self._ready_frames = 0
      self._ready = False
      return PassAdvice(False, False, ("disabled",), 0)

    reasons: list[str] = []
    lead_valid = (inputs.lead_distance_m is not None and inputs.lead_speed_mps is not None and
                  isfinite(inputs.lead_distance_m) and isfinite(inputs.lead_speed_mps))
    lead_in_range = lead_valid and 0.0 < inputs.lead_distance_m < max(35.0, inputs.ego_speed_mps * 4.0)
    slow_lead = lead_in_range and inputs.lead_speed_mps <= inputs.ego_speed_mps - self.MIN_SPEED_DELTA_MPS
    if not slow_lead:
      reasons.append("no_slow_lead")
    if inputs.ego_speed_mps < self.MIN_SPEED_MPS:
      reasons.append("below_lane_change_speed")
    if inputs.left_space is not SpaceState.CLEAR:
      reasons.append("left_space_not_clear")
    if not inputs.left_adjacent_lane_geometry:
      reasons.append("left_adjacent_lane_geometry_unknown")
    if inputs.lane_confidence < self.MIN_LANE_CONFIDENCE:
      reasons.append("lane_confidence")
    if not inputs.source_fresh:
      reasons.append("stale_sources")
    if not inputs.trajectory_valid:
      reasons.append("trajectory_invalid")

    raw_ready = not reasons
    if raw_ready:
      self._ready_frames += 1
      if self._ready_frames >= self.ASSERT_FRAMES:
        self._ready = True
    else:
      self._ready_frames = 0
      self._ready = False

    driver_candidate = self._ready and raw_ready and inputs.left_blinker
    return PassAdvice(
      left_lane_geometry_ready=self._ready,
      driver_left_lane_change_candidate=driver_candidate,
      reasons=tuple(reasons),
      ready_frames=self._ready_frames,
    )
