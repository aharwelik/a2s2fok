from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum, auto


class OvertakeMode(IntEnum):
  OFF = 0
  LIVE_SHADOW = 1
  REPLAY_SIMULATION = 2


class OvertakeState(Enum):
  OFF = auto()
  FOLLOWING = auto()
  PASS_POSSIBLE = auto()
  DRIVER_REQUESTED = auto()
  LANE_CHANGE_ACTIVE = auto()
  PASSING = auto()
  RETURN_POSSIBLE = auto()
  COMPLETE = auto()
  CANCELLED = auto()


@dataclass(frozen=True)
class RuntimeContext:
  replay_or_simulation: bool = False
  runtime_reports_no_vehicle: bool = False
  live_vehicle_attached: bool = True

  @property
  def simulation_requests_allowed(self) -> bool:
    return self.replay_or_simulation and self.runtime_reports_no_vehicle and not self.live_vehicle_attached


@dataclass(frozen=True)
class OvertakeInputs:
  lead_present: bool
  lead_distance_m: float = 0.0
  ego_speed_mps: float = 0.0
  lead_speed_mps: float = 0.0
  set_speed_mps: float = 0.0
  left_blinker: bool = False
  right_blinker: bool = False
  left_blind_spot: bool = False
  right_blind_spot: bool = False
  lane_available: bool = True
  lane_change_active: bool = False
  road_edge_detected: bool = False
  occupancy_known: bool = True
  navigation_contradiction: bool = False
  driver_monitoring_valid: bool = True
  stale_model: bool = False
  driver_brake: bool = False
  driver_gas: bool = False
  steering_fault: bool = False
  stock_longitudinal_owner: bool = True


@dataclass(frozen=True)
class OvertakeRecommendation:
  state: OvertakeState
  advisory_text: str
  simulated_lane_change_request: bool
  rejection_reason: str = ""


class OvertakeAdvisor:
  def __init__(self, mode: OvertakeMode = OvertakeMode.LIVE_SHADOW, slow_lead_delta_mps: float = 2.0) -> None:
    self.mode = mode
    self.slow_lead_delta_mps = slow_lead_delta_mps
    self.state = OvertakeState.OFF if mode == OvertakeMode.OFF else OvertakeState.FOLLOWING
    self._completed_pass_waiting_for_new_edge = False

  def update(self, inputs: OvertakeInputs, runtime: RuntimeContext | None = None) -> OvertakeRecommendation:
    runtime = runtime or RuntimeContext()
    if self.mode == OvertakeMode.OFF:
      self.state = OvertakeState.OFF
      return OvertakeRecommendation(self.state, "", False, "mode_off")

    rejection = self._reject(inputs)
    if rejection:
      self.state = OvertakeState.CANCELLED
      return OvertakeRecommendation(self.state, "", False, rejection)

    if not inputs.lead_present:
      self.state = OvertakeState.FOLLOWING
      self._completed_pass_waiting_for_new_edge = False
      return OvertakeRecommendation(self.state, "", False)

    if inputs.lane_change_active:
      self.state = OvertakeState.LANE_CHANGE_ACTIVE
      return OvertakeRecommendation(self.state, "", False)

    driver_requested = inputs.left_blinker or inputs.right_blinker
    if driver_requested:
      self.state = OvertakeState.DRIVER_REQUESTED
      simulated = self.mode == OvertakeMode.REPLAY_SIMULATION and runtime.simulation_requests_allowed
      if self.mode == OvertakeMode.REPLAY_SIMULATION and not runtime.simulation_requests_allowed:
        raise RuntimeError("overtake simulation requested without non-live runtime proof")
      return OvertakeRecommendation(self.state, "DRIVER SIGNAL RECEIVED", simulated)

    if self._slow_lead(inputs):
      self.state = OvertakeState.PASS_POSSIBLE
      return OvertakeRecommendation(self.state, "PASS POSSIBLE — SIGNAL REQUIRED", False)

    self.state = OvertakeState.FOLLOWING
    return OvertakeRecommendation(self.state, "", False)

  def _slow_lead(self, inputs: OvertakeInputs) -> bool:
    return (
      inputs.lead_present
      and inputs.lead_distance_m > 8.0
      and inputs.ego_speed_mps > inputs.lead_speed_mps + self.slow_lead_delta_mps
      and inputs.set_speed_mps > inputs.lead_speed_mps + self.slow_lead_delta_mps
    )

  @staticmethod
  def _reject(inputs: OvertakeInputs) -> str:
    if inputs.stale_model:
      return "STALE_MODEL"
    if inputs.driver_brake:
      return "DRIVER_BRAKE"
    if inputs.driver_gas:
      return "DRIVER_OVERRIDE"
    if inputs.steering_fault:
      return "STEERING_FAULT"
    if inputs.road_edge_detected:
      return "ROAD_EDGE"
    if not inputs.occupancy_known:
      return "OCCUPANCY_UNKNOWN"
    if inputs.navigation_contradiction:
      return "NAVIGATION_CONTRADICTION"
    if not inputs.driver_monitoring_valid:
      return "DRIVER_MONITORING_INVALID"
    if not inputs.lane_available:
      return "LANE_UNAVAILABLE"
    if inputs.left_blind_spot or inputs.right_blind_spot:
      return "BLIND_SPOT"
    if not inputs.stock_longitudinal_owner:
      return "LONGITUDINAL_OWNER_UNEXPECTED"
    return ""
