DEVELOPMENT_LABEL = "ASCENT V6 TEST — STOCK EYESIGHT BRAKING"
LONGITUDINAL_OWNER = "STOCK_EYESIGHT"
MODEL_STOP_SHADOW_TEMPLATE = "MODEL STOP {distance_m:.0f} m — SHADOW"
OVERTAKE_SHADOW_LABEL = "PASS POSSIBLE — SIGNAL REQUIRED"
ANGLE_BASE_SHA = "3f5708b4445f2e39df4135b71c06fdbd88a6a143"
OPENDBC_SHA = "4e7bad36b655da342a773d4ad6ff799838ab4a55"
SOURCE_LOCK_SHA = ANGLE_BASE_SHA

STATUS_ROWS = (
  ("Ascent V6 Integration Status", "TEST"),
  ("Angle Controller Debug", "ANGLE LKAS"),
  ("Lane Change Mode", "NUDGE default"),
  ("Map Data Status", "OSM + road info"),
  ("Speed Limit Mode", "INFO default"),
  ("Stop Obstacle Mode", "LIVE_SHADOW"),
  ("Overtake Advisor Mode", "LIVE_SHADOW"),
  ("Longitudinal Owner", LONGITUDINAL_OWNER),
  ("Source Lock SHA", SOURCE_LOCK_SHA[:8]),
  ("OpenDBC SHA", OPENDBC_SHA[:8]),
)


def model_stop_label(distance_m: float) -> str:
  return MODEL_STOP_SHADOW_TEMPLATE.format(distance_m=distance_m)


def status_summary() -> str:
  return "\n".join(f"{name}: {value}" for name, value in STATUS_ROWS)
