from dataclasses import dataclass


DIRECT_LONG_ALPHA_DEFAULT = False
PANDA_LONG_RUNTIME_COMPILED = False
TRAFFIC_CONTROL_RUNTIME_COMPILED = False
AUTOMATIC_PASS_RUNTIME_COMPILED = False
AUTOMATIC_BLINKER_RUNTIME_COMPILED = False
AUTOMATIC_LANE_SELECTION_RUNTIME_COMPILED = False
LIVE_LANE_POSITION_TRIM_ACTIVE = False
LIVE_ADAPTIVE_CURVE_CONTROL = False
BIG_MODEL_LAB_DEFAULT = False


@dataclass(frozen=True)
class V8ReleaseBoundary:
  direct_long: bool = DIRECT_LONG_ALPHA_DEFAULT
  panda_long: bool = PANDA_LONG_RUNTIME_COMPILED
  traffic_control: bool = TRAFFIC_CONTROL_RUNTIME_COMPILED
  automatic_pass: bool = AUTOMATIC_PASS_RUNTIME_COMPILED
  automatic_blinker: bool = AUTOMATIC_BLINKER_RUNTIME_COMPILED
  automatic_lane_selection: bool = AUTOMATIC_LANE_SELECTION_RUNTIME_COMPILED

  @property
  def fail_closed(self) -> bool:
    return not any((self.direct_long, self.panda_long, self.traffic_control, self.automatic_pass,
                    self.automatic_blinker, self.automatic_lane_selection))
