from dataclasses import dataclass
from math import isfinite, sqrt


@dataclass
class CurveEnvelope:
  standard_lat_accel: float = 1.6
  gentle_lat_accel: float = 1.25
  steering_capability: float = 1.6
  driver_profile: float = 1.6
  hard_cap: float = 2.5
  saturation_backoff: float = 0.03
  growth_rate: float = 0.002

  def observe_controller(self, active: bool, saturated: bool, lateral_accel: float, learning_allowed: bool) -> None:
    if not active or not learning_allowed or not isfinite(lateral_accel):
      return
    if saturated:
      self.steering_capability = max(self.gentle_lat_accel, self.steering_capability - self.saturation_backoff)
    elif lateral_accel > 0.5:
      target = min(self.hard_cap, max(self.steering_capability, lateral_accel))
      self.steering_capability = min(target, self.steering_capability + self.growth_rate)

  def set_driver_profile(self, value: float) -> None:
    if isfinite(value):
      self.driver_profile = min(self.hard_cap, max(0.8, value))

  def budget(self, profile: str) -> float:
    profile = profile.upper()
    desired = (self.gentle_lat_accel if profile == "GENTLE" else
               self.steering_capability if profile == "SPORT" else
               self.driver_profile if profile == "AUTO" else self.standard_lat_accel)
    return min(desired, self.steering_capability, self.hard_cap)

  def target_speed(self, curvature: float, profile: str = "STANDARD") -> float | None:
    if not isfinite(curvature) or abs(curvature) < 1e-6:
      return None
    return sqrt(max(0.0, self.budget(profile) / abs(curvature)))
