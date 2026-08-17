from dataclasses import dataclass
from enum import StrEnum

from openpilot.sunnypilot.selfdrive.ascent_v8.lab_gate import GateState, LabDecision
from openpilot.sunnypilot.selfdrive.ascent_v8.unknown_space import SpaceState


class PlannerAction(StrEnum):
  HOLD = "HOLD"
  PASS_CANDIDATE = "PASS_CANDIDATE"
  RETURN_CANDIDATE = "RETURN_CANDIDATE"
  STOP_CANDIDATE = "STOP_CANDIDATE"


@dataclass(frozen=True)
class PlannerInputs:
  lab_gate: LabDecision
  target_space: SpaceState
  lead_present: bool = False
  slow_lead: bool = False
  driver_lane_change_requested: bool = False
  pass_complete: bool = False
  traffic_control_stop: bool = False
  blind_spot_fresh_occupied: bool = False
  road_edge: bool = False


@dataclass(frozen=True)
class PlannerDecision:
  action: PlannerAction
  reasons: tuple[str, ...]
  simulation_request: bool
  can_actuate: bool = False


class ClosedCoursePlanner:
  """High-level simulation planner. V8 Alpha contains no live connector."""
  def evaluate(self, inputs: PlannerInputs) -> PlannerDecision:
    reasons: list[str] = []
    if inputs.lab_gate.state is not GateState.READY:
      reasons.append("lab_gate_blocked")
    if inputs.target_space is not SpaceState.CLEAR:
      reasons.append("target_space_not_clear")
    if inputs.blind_spot_fresh_occupied:
      reasons.append("blind_spot")
    if inputs.road_edge:
      reasons.append("road_edge")
    if reasons:
      return PlannerDecision(PlannerAction.HOLD, tuple(reasons), False)
    if inputs.traffic_control_stop:
      return PlannerDecision(PlannerAction.STOP_CANDIDATE, (), True)
    if inputs.pass_complete:
      return PlannerDecision(PlannerAction.RETURN_CANDIDATE, (), True)
    if inputs.lead_present and inputs.slow_lead and inputs.driver_lane_change_requested:
      return PlannerDecision(PlannerAction.PASS_CANDIDATE, (), True)
    return PlannerDecision(PlannerAction.HOLD, ("no_candidate",), False)
