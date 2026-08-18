DEVELOPMENT_LABEL = "ALPHA / LIVE EVIDENCE / STOCK EYESIGHT LONG"


def _live_status_lines(shadow_status: dict | None) -> tuple[str, ...]:
  if not shadow_status or not isinstance(shadow_status.get("last"), dict) or not shadow_status["last"]:
    return ("Live V8 telemetry: waiting for the first on-road model sample.",)

  last = shadow_status["last"]
  model_mode = "Chestnut" if last.get("model_big") else "native"
  curve_target = last.get("curve_target_speed_mps")
  curve_text = "straight road" if curve_target is None else f"{float(curve_target) * 2.23694:.1f} mph"
  lane_trim = last.get("lane_trim_m")
  lane_text = "unknown" if lane_trim is None else f"{float(lane_trim):+.2f} m"
  model_stop = ("disabled" if not last.get("model_stop_enabled") else
                "ACTIVE" if last.get("model_stop_prediction") else "clear")
  lane_change_state = ("disabled" if not last.get("lane_change_evidence_enabled") else
                       "driver-requested" if last.get("driver_left_lane_change_candidate") else
                       "left geometry clear" if last.get("left_lane_geometry_ready") else "not ready")
  return (
    f"Live model: {model_mode}; sources {'fresh' if last.get('source_fresh') else 'stale'}.",
    f"Trajectory: {last.get('trajectory', 'unknown')}; space: {last.get('space', 'unknown')}.",
    f"Curve target: {curve_text}; lane candidate trim: {lane_text}.",
    f"Model stop prediction: {model_stop}; left lane-change evidence: {lane_change_state}.",
    f"This drive: {int(shadow_status.get('evaluations', 0))} evaluations; {int(shadow_status.get('errors', 0))} errors.",
  )


def status_summary(shadow_status: dict | None = None) -> str:
  if shadow_status is None:
    try:
      from openpilot.common.params import Params
      shadow_status = Params().get("AscentV8ShadowStatus")
    except Exception:
      shadow_status = None
  return "\n".join((
    "2023 Subaru Ascent V8 Alpha",
    "Bus 0 angle steering; V6 planner and MADS guards preserved.",
    "Stock EyeSight retains acceleration, braking, AEB, and FCW.",
    "V8 trajectory, curve, lane-position, and command guards are live telemetry.",
    "Model-stop and lane-change evidence are development toggles and default OFF.",
    "Driver-confirmed lane changes remain available; automatic pass/blinkers and direct longitudinal remain OFF.",
    "Model-stop evidence does not claim whether the cause is a red light, stop sign, or another road condition.",
    "Maintenance SSH is key-only and restricted to status, parked updates, and parked log bundles.",
    *_live_status_lines(shadow_status),
  ))
