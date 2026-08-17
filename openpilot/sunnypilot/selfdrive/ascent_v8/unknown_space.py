from dataclasses import dataclass
from enum import StrEnum


class SpaceState(StrEnum):
  CLEAR = "CLEAR"
  OCCUPIED = "OCCUPIED"
  UNKNOWN = "UNKNOWN"
  STALE = "STALE"
  CONTRADICTORY = "CONTRADICTORY"


@dataclass(frozen=True)
class RegionEvidence:
  visible_recently: bool
  object_present: bool
  bsm_occupied: bool | None
  bsm_fresh: bool
  road_edge: bool
  contradictory: bool
  age_s: float


class UnknownSpaceClassifier:
  def __init__(self, stale_after_s: float = 0.6):
    self.stale_after_s = stale_after_s

  def classify(self, evidence: RegionEvidence) -> SpaceState:
    if evidence.contradictory:
      return SpaceState.CONTRADICTORY
    if evidence.road_edge:
      return SpaceState.OCCUPIED
    if evidence.bsm_fresh and evidence.bsm_occupied is True:
      return SpaceState.OCCUPIED
    if evidence.age_s > self.stale_after_s:
      return SpaceState.STALE
    if evidence.object_present:
      return SpaceState.OCCUPIED
    if not evidence.visible_recently:
      return SpaceState.UNKNOWN
    if not evidence.bsm_fresh or evidence.bsm_occupied is None:
      return SpaceState.UNKNOWN
    return SpaceState.CLEAR

  @staticmethod
  def trajectory_allowed(states: list[SpaceState]) -> bool:
    return all(state is SpaceState.CLEAR for state in states)
