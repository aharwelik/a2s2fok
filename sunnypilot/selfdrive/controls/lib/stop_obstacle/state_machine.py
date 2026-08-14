from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.estimator import RejectionReason, StopTarget


class StopState(Enum):
  OFF = auto()
  MONITORING = auto()
  CANDIDATE = auto()
  STOPPING = auto()
  STOPPED = auto()
  RELEASING = auto()
  CANCELLED = auto()


@dataclass(frozen=True)
class StopTransition:
  state: StopState
  reason: str


class StopObstacleStateMachine:
  def __init__(self, persistence_frames: int = 3, release_frames: int = 2) -> None:
    self.state = StopState.MONITORING
    self.persistence_frames = persistence_frames
    self.release_frames = release_frames
    self._valid_frames = 0
    self._release_frames = 0

  def update(self, target: StopTarget, ego_speed_mps: float, release_signal_valid: bool = False) -> StopTransition:
    if target.rejection_reason == RejectionReason.MODE_OFF:
      self.state = StopState.OFF
      self._valid_frames = 0
      return StopTransition(self.state, "mode_off")

    if not target.valid:
      self._valid_frames = 0
      if self.state not in (StopState.MONITORING, StopState.OFF):
        self.state = StopState.CANCELLED
        return StopTransition(self.state, target.rejection_reason.name)
      self.state = StopState.MONITORING
      return StopTransition(self.state, target.rejection_reason.name)

    self._valid_frames += 1
    if self._valid_frames < self.persistence_frames:
      self.state = StopState.CANDIDATE
      return StopTransition(self.state, "persistence")

    if ego_speed_mps <= 0.2:
      self.state = StopState.STOPPED
    elif target.time_to_stop_s <= 7.0:
      self.state = StopState.STOPPING
    else:
      self.state = StopState.CANDIDATE

    if self.state == StopState.STOPPED and release_signal_valid:
      self._release_frames += 1
      if self._release_frames >= self.release_frames:
        self.state = StopState.RELEASING
        self._valid_frames = 0
        self._release_frames = 0
        return StopTransition(self.state, "release_signal")
    else:
      self._release_frames = 0

    return StopTransition(self.state, "valid")
