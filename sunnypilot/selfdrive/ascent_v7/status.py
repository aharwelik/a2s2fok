DEVELOPMENT_LABEL = "ASCENT V7 ALPHA — STOCK EYESIGHT BRAKING"
LONGITUDINAL_OWNER = "STOCK_EYESIGHT"
ROOT_BASE_SHA = "78965b9f8293fb290eda6abf17dd61f4b932c94e"
OPENDBC_BASE_SHA = "4e7bad36b655da342a773d4ad6ff799838ab4a55"

STATUS_ROWS = (
  ("Ascent V7 Integration Status", "ALPHA / CLOSED COURSE"),
  ("Angle Steering Bus", "BUS 0 ONLY"),
  ("Dual-Bus Steering", "OFF"),
  ("V6 AnglePlanner", "PRESERVED"),
  ("Lane Change", "DRIVER SIGNAL REQUIRED"),
  ("Automatic Blinker", "OFF"),
  ("Stop Assist", "ADVISORY / SHADOW"),
  ("Direct Long Alpha", "OFF / RUNTIME BLOCKED"),
  ("Traffic Control Alpha", "OFF / RUNTIME BLOCKED"),
  ("Longitudinal Owner", LONGITUDINAL_OWNER),
  ("Root Base", ROOT_BASE_SHA[:8]),
  ("OpenDBC Base", OPENDBC_BASE_SHA[:8]),
)


def status_summary() -> str:
  return "\n".join(f"{name}: {value}" for name, value in STATUS_ROWS)
