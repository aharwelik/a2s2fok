DEVELOPMENT_LABEL = "ALPHA / STOCK EYESIGHT LONG"


def status_summary() -> str:
  return "\n".join((
    "2023 Subaru Ascent V8 Alpha",
    "Bus 0 angle steering; V6 planner and MADS guards preserved.",
    "Stock EyeSight retains acceleration, braking, AEB, and FCW.",
    "V8 trajectory, curve, lane-position, and command guards are shadow-only.",
    "Automatic pass, blinkers, lane selection, traffic control, and direct longitudinal remain OFF.",
    "Maintenance SSH is key-only and restricted to status, parked updates, and parked log bundles.",
  ))
