from dataclasses import dataclass


@dataclass(frozen=True)
class DirectLongEvidence:
  exact_firmware_allowed: bool = False
  pre_engine_disable_confirmed: bool = False
  crank_survival_confirmed: bool = False
  replacement_messages_validated: bool = False
  actuation_api_characterized: bool = False
  speed_dependent_long_safety_passed: bool = False
  longitudinal_maneuver_report_passed: bool = False
  panda_long_tests_passed: bool = False

  @property
  def panda_long_ready(self) -> bool:
    return all((self.exact_firmware_allowed, self.pre_engine_disable_confirmed, self.crank_survival_confirmed,
                self.replacement_messages_validated, self.actuation_api_characterized,
                self.speed_dependent_long_safety_passed, self.longitudinal_maneuver_report_passed,
                self.panda_long_tests_passed))


@dataclass(frozen=True)
class SpeedEnvelopePoint:
  speed_mps: float
  gas_max: float
  brake_max: float
  rpm_max: float


class SpeedDependentEnvelope:
  def __init__(self, points: list[SpeedEnvelopePoint]):
    self.points = sorted(points, key=lambda point: point.speed_mps)

  def structurally_valid(self) -> bool:
    if len(self.points) < 2:
      return False
    previous: SpeedEnvelopePoint | None = None
    for point in self.points:
      if min(point.speed_mps, point.gas_max, point.brake_max, point.rpm_max) < 0:
        return False
      if previous is not None and point.speed_mps <= previous.speed_mps:
        return False
      previous = point
    return True
