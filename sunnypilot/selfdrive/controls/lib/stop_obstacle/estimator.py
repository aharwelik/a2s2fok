from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum, auto


class StopObstacleMode(IntEnum):
  OFF = 0
  LIVE_SHADOW = 1
  REPLAY_SIMULATION = 2


class StopSource(Enum):
  MODEL_SHOULD_STOP = auto()
  MODEL_STOP_PROFILE = auto()
  EXPLICIT_RED_SIGNAL = auto()
  EXPLICIT_STOP_SIGN = auto()
  UNKNOWN_STOP_INTENT = auto()


class RejectionReason(Enum):
  NONE = auto()
  MODE_OFF = auto()
  MODEL_STALE = auto()
  PROFILE_INCONSISTENT = auto()
  TARGET_BEHIND = auto()
  TARGET_TOO_CLOSE = auto()
  TARGET_TOO_FAR = auto()
  DECEL_OUT_OF_RANGE = auto()
  REAL_LEAD_CLOSER = auto()
  CURVE_SLOWDOWN = auto()
  DRIVER_OVERRIDE = auto()
  VEHICLE_FAULT = auto()
  LOW_CONFIDENCE = auto()
  LIVE_RUNTIME = auto()


@dataclass(frozen=True)
class RuntimeContext:
  explicit_mode: StopObstacleMode
  replay_or_simulation: bool = False
  runtime_reports_no_vehicle: bool = False
  live_vehicle_attached: bool = True

  @property
  def simulation_actuation_allowed(self) -> bool:
    return (
      self.explicit_mode == StopObstacleMode.REPLAY_SIMULATION
      and self.replay_or_simulation
      and self.runtime_reports_no_vehicle
      and not self.live_vehicle_attached
    )


@dataclass(frozen=True)
class LeadSnapshot:
  status: bool = False
  distance_m: float = 0.0


@dataclass(frozen=True)
class StopInputs:
  should_stop: bool
  position_x: tuple[float, ...]
  velocity_x: tuple[float, ...]
  ego_speed_mps: float
  ego_accel_mps2: float = 0.0
  model_age_s: float = 0.0
  confidence: float = 0.0
  desired_accel_mps2: float = 0.0
  lead_0: LeadSnapshot = LeadSnapshot()
  lead_1: LeadSnapshot = LeadSnapshot()
  curve_slowdown: bool = False
  driver_override: bool = False
  vehicle_fault: bool = False
  stock_aeb_active: bool = False
  explicit_source: StopSource | None = None


@dataclass(frozen=True)
class StopTarget:
  valid: bool
  confidence: float
  distance_m: float
  stop_buffer_m: float
  time_to_stop_s: float
  minimum_predicted_speed_mps: float
  required_decel_mps2: float
  source: StopSource
  state: str
  age_s: float
  rejection_reason: RejectionReason


class StopTargetEstimator:
  def __init__(
    self,
    mode: StopObstacleMode = StopObstacleMode.LIVE_SHADOW,
    min_confidence: float = 0.62,
    max_age_s: float = 0.5,
    min_distance_m: float = 6.0,
    max_distance_m: float = 120.0,
    max_comfortable_decel_mps2: float = 3.2,
    stop_buffer_m: float = 4.0,
  ) -> None:
    self.mode = mode
    self.min_confidence = min_confidence
    self.max_age_s = max_age_s
    self.min_distance_m = min_distance_m
    self.max_distance_m = max_distance_m
    self.max_comfortable_decel_mps2 = max_comfortable_decel_mps2
    self.stop_buffer_m = stop_buffer_m

  def estimate(self, inputs: StopInputs) -> StopTarget:
    source = inputs.explicit_source or (StopSource.MODEL_SHOULD_STOP if inputs.should_stop else StopSource.UNKNOWN_STOP_INTENT)
    target_distance = self._target_distance(inputs)
    min_speed = min(inputs.velocity_x) if inputs.velocity_x else inputs.ego_speed_mps
    usable_distance = max(target_distance - self.stop_buffer_m, 0.01)
    required_decel = (inputs.ego_speed_mps ** 2) / (2.0 * usable_distance)
    time_to_stop = inputs.ego_speed_mps / max(required_decel, 0.01)

    rejection = self._reject(inputs, target_distance, min_speed, required_decel)
    return StopTarget(
      valid=rejection == RejectionReason.NONE,
      confidence=inputs.confidence,
      distance_m=target_distance,
      stop_buffer_m=self.stop_buffer_m,
      time_to_stop_s=time_to_stop,
      minimum_predicted_speed_mps=min_speed,
      required_decel_mps2=required_decel,
      source=source,
      state="CANDIDATE" if rejection == RejectionReason.NONE else "CANCELLED",
      age_s=inputs.model_age_s,
      rejection_reason=rejection,
    )

  def _target_distance(self, inputs: StopInputs) -> float:
    if inputs.position_x:
      forward = [x for x in inputs.position_x if x > 0.0]
      if forward:
        return min(forward)
    return 0.0

  def _reject(self, inputs: StopInputs, distance_m: float, min_speed: float, required_decel: float) -> RejectionReason:
    if self.mode == StopObstacleMode.OFF:
      return RejectionReason.MODE_OFF
    if inputs.model_age_s > self.max_age_s:
      return RejectionReason.MODEL_STALE
    if not inputs.should_stop and inputs.explicit_source is None:
      return RejectionReason.PROFILE_INCONSISTENT
    if not inputs.position_x or not inputs.velocity_x or min_speed > max(0.6, inputs.ego_speed_mps * 0.35):
      return RejectionReason.PROFILE_INCONSISTENT
    if distance_m <= 0.0:
      return RejectionReason.TARGET_BEHIND
    if distance_m < self.min_distance_m:
      return RejectionReason.TARGET_TOO_CLOSE
    if distance_m > self.max_distance_m:
      return RejectionReason.TARGET_TOO_FAR
    if required_decel > self.max_comfortable_decel_mps2:
      return RejectionReason.DECEL_OUT_OF_RANGE
    if self._real_lead_closer(inputs, distance_m):
      return RejectionReason.REAL_LEAD_CLOSER
    if inputs.curve_slowdown:
      return RejectionReason.CURVE_SLOWDOWN
    if inputs.driver_override:
      return RejectionReason.DRIVER_OVERRIDE
    if inputs.vehicle_fault or inputs.stock_aeb_active:
      return RejectionReason.VEHICLE_FAULT
    if inputs.confidence < self.min_confidence:
      return RejectionReason.LOW_CONFIDENCE
    return RejectionReason.NONE

  @staticmethod
  def _real_lead_closer(inputs: StopInputs, distance_m: float) -> bool:
    return any(lead.status and 0.0 < lead.distance_m <= distance_m for lead in (inputs.lead_0, inputs.lead_1))

