from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass


EPS_CONFLICT_MONITOR_CAN_ACTUATE = False
SUBARU_DYNAMIC_FWD_HOOK_ACTIVE = False


@dataclass(frozen=True)
class EPSConflictSample:
  driver_torque: float
  eps_torque: float
  steering_rate_deg_s: float
  measured_angle_deg: float
  commanded_angle_deg: float
  lkas_request: bool
  steer_error: bool


@dataclass(frozen=True)
class EPSConflictSnapshot:
  sample_count: int
  torque_mismatch_debt: float
  command_angle_debt: float
  wheel_rate_debt: float
  directional_driver_conflict_debt: float
  steer_error_count: int
  can_actuate: bool = EPS_CONFLICT_MONITOR_CAN_ACTUATE


class EPSConflictMonitor:
  """Passive rolling metrics for later route analysis; no control outputs."""
  def __init__(self, window_frames: int = 250):
    if window_frames < 1:
      raise ValueError("window_frames must be positive")
    self._samples: deque[EPSConflictSample] = deque(maxlen=window_frames)

  def update(self, sample: EPSConflictSample) -> EPSConflictSnapshot:
    self._samples.append(sample)
    samples = tuple(self._samples)
    count = len(samples)
    torque_debt = sum(abs(item.eps_torque - item.driver_torque) for item in samples) / count
    angle_debt = sum(abs(item.commanded_angle_deg - item.measured_angle_deg) for item in samples) / count
    wheel_rate_debt = sum(abs(item.steering_rate_deg_s) for item in samples) / count
    directional_conflict = sum(
      abs(item.driver_torque)
      for item in samples
      if item.lkas_request and item.driver_torque * (item.commanded_angle_deg - item.measured_angle_deg) < 0
    ) / count
    return EPSConflictSnapshot(
      sample_count=count,
      torque_mismatch_debt=torque_debt,
      command_angle_debt=angle_debt,
      wheel_rate_debt=wheel_rate_debt,
      directional_driver_conflict_debt=directional_conflict,
      steer_error_count=sum(item.steer_error for item in samples),
    )


@dataclass(frozen=True)
class OwnershipObservation:
  stock_camera_0x124_present: bool
  openpilot_0x124_transmitted: bool
  panda_forwarding_camera_to_main: bool
  handoff_gap_frames: int = 0


def analyze_steering_ownership(observation: OwnershipObservation) -> dict:
  """Describe observed ownership without installing a forwarding hook."""
  overlap = observation.stock_camera_0x124_present and observation.openpilot_0x124_transmitted
  return {
    **asdict(observation),
    "overlap_observed": overlap,
    "handoff_gap_observed": observation.handoff_gap_frames > 0,
    "dynamic_forwarding_active": SUBARU_DYNAMIC_FWD_HOOK_ACTIVE,
    "can_actuate": False,
  }
