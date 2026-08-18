from __future__ import annotations

import datetime
import json
from math import isfinite
from pathlib import Path
import re
import time

from opendbc.car.subaru.values import CarControllerParams


CALIBRATION_ROOT = Path("/data/ascent_maintenance/calibration")
MAX_FILES = 8
MAX_TOTAL_BYTES = 256 * 1024 * 1024
RECORD_INTERVAL_NS = 100_000_000
STATUS_INTERVAL_NS = 1_000_000_000


def _finite(value) -> float | None:
  try:
    result = float(value)
  except (TypeError, ValueError):
    return None
  return round(result, 6) if isfinite(result) else None


def _first(values) -> float | None:
  return _finite(values[0]) if len(values) else None


def _last(values) -> float | None:
  return _finite(values[len(values) - 1]) if len(values) else None


def _enum(value) -> str:
  return str(value).rsplit(".", 1)[-1]


def _text(value) -> str | None:
  if isinstance(value, bytes):
    return value.decode(errors="replace")
  return str(value) if value is not None else None


def _interpolate(value: float, x: tuple[float, float] | list[float], y: tuple[float, float] | list[float]) -> float:
  if value <= x[0]:
    return y[0]
  if value >= x[1]:
    return y[1]
  return y[0] + (value - x[0]) * (y[1] - y[0]) / (x[1] - x[0])


def subaru_longitudinal_command(applied_accel: float, long_active: bool) -> dict:
  if not long_active:
    return {"throttle": CarControllerParams.THROTTLE_INACTIVE, "rpm": CarControllerParams.RPM_MIN,
            "brake": CarControllerParams.BRAKE_MIN}
  throttle = round(_interpolate(applied_accel, CarControllerParams.THROTTLE_LOOKUP_BP,
                                CarControllerParams.THROTTLE_LOOKUP_V))
  rpm = round(_interpolate(applied_accel, CarControllerParams.RPM_LOOKUP_BP, CarControllerParams.RPM_LOOKUP_V))
  brake = round(_interpolate(applied_accel, CarControllerParams.BRAKE_LOOKUP_BP, CarControllerParams.BRAKE_LOOKUP_V))
  return {
    "throttle": max(CarControllerParams.THROTTLE_MIN, min(CarControllerParams.THROTTLE_MAX, throttle)),
    "rpm": max(CarControllerParams.RPM_MIN, min(CarControllerParams.RPM_MAX, rpm)),
    "brake": max(CarControllerParams.BRAKE_MIN, min(CarControllerParams.BRAKE_MAX, brake)),
  }


def build_calibration_sample(car_state, model, car_control, car_output, longitudinal_plan, *,
                             shadow: dict, monotonic_ns: int) -> dict:
  action = model.action
  actuators = car_control.actuators
  output = car_output.actuatorsOutput
  cruise = car_state.cruiseState
  pitch = _finite(car_control.orientationNED[1]) if len(car_control.orientationNED) == 3 else None
  applied_accel = float(output.accel)
  return {
    "mono_ns": monotonic_ns,
    "vehicle": {
      "v_ego": _finite(car_state.vEgo), "v_ego_raw": _finite(car_state.vEgoRaw), "a_ego": _finite(car_state.aEgo),
      "standstill": bool(car_state.standstill), "gas_pressed": bool(car_state.gasPressed),
      "brake_pressed": bool(car_state.brakePressed), "brake_hold": bool(car_state.brakeHoldActive),
      "cruise_available": bool(cruise.available), "cruise_enabled": bool(cruise.enabled),
      "cruise_standstill": bool(cruise.standstill), "pitch_rad": pitch,
      "wheel_speeds": [_finite(value) for value in (car_state.wheelSpeeds.fl, car_state.wheelSpeeds.fr,
                                                      car_state.wheelSpeeds.rl, car_state.wheelSpeeds.rr)],
      "buttons": [{"type": _enum(event.type), "pressed": bool(event.pressed)} for event in car_state.buttonEvents],
    },
    "model": {
      "frame_id": int(model.frameId), "big": bool(model.big), "should_stop": bool(action.shouldStop),
      "desired_accel": _finite(action.desiredAcceleration), "desired_curvature": _finite(action.desiredCurvature),
      "path_end_m": _last(model.position.x), "terminal_speed": _last(model.velocity.x),
    },
    "plan": {
      "source": _enum(longitudinal_plan.longitudinalPlanSource), "a_target": _finite(longitudinal_plan.aTarget),
      "should_stop": bool(longitudinal_plan.shouldStop), "has_lead": bool(longitudinal_plan.hasLead),
      "allow_throttle": bool(longitudinal_plan.allowThrottle), "allow_brake": bool(longitudinal_plan.allowBrake),
      "speed_0": _first(longitudinal_plan.speeds), "accel_0": _first(longitudinal_plan.accels),
      "jerk_0": _first(longitudinal_plan.jerks),
    },
    "control": {
      "enabled": bool(car_control.enabled), "long_active": bool(car_control.longActive),
      "requested_accel": _finite(actuators.accel), "state": _enum(actuators.longControlState),
      "output_accel": _finite(output.accel), "output_gas": _finite(output.gas), "output_brake": _finite(output.brake),
    },
    "subaru_command": subaru_longitudinal_command(applied_accel, bool(car_control.longActive)),
    "evidence": {
      "model_stop": bool(shadow.get("model_stop_prediction")),
      "model_stop_raw": bool(shadow.get("model_stop_raw_candidate")),
      "lead_distance_m": _finite(shadow.get("lead_distance_m")),
      "lead_speed_mps": _finite(shadow.get("lead_speed_mps")),
      "trajectory": shadow.get("trajectory"),
    },
  }


class CalibrationRecorder:
  def __init__(self, params, root: Path = CALIBRATION_ROOT):
    self.params = params
    self.root = root
    self.root.mkdir(parents=True, exist_ok=True)
    self.route = ""
    self.path: Path | None = None
    self.samples = 0
    self.last_record_ns = 0
    self.last_status_ns = -STATUS_INTERVAL_NS

  def _route_value(self) -> str:
    route = self.params.get("CurrentRoute") or "route-starting"
    if isinstance(route, bytes):
      route = route.decode(errors="replace")
    return str(route)

  def _mark_route_for_upload(self, route: str) -> None:
    if route == "route-starting":
      return
    viewed = _text(self.params.get("AthenadRecentlyViewedRoutes")) or ""
    routes = [item for item in viewed.split(",") if item]
    if route not in routes:
      self.params.put("AthenadRecentlyViewedRoutes", ",".join([*routes, route][-10:]))

  def _open_route(self, monotonic_ns: int) -> None:
    route = self._route_value()
    if route == self.route and self.path is not None:
      return
    self.route = route
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", route)[:120]
    self.path = self.root / f"{filename}.jsonl"
    new_file = not self.path.exists()
    if new_file:
      header = {
        "schema": 1, "kind": "ascent_v8_calibration", "route": route,
        "started_utc": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": _text(self.params.get("GitCommit")), "git_branch": _text(self.params.get("GitBranch")),
      }
      self.path.write_text(json.dumps(header, separators=(",", ":")) + "\n")
    self._mark_route_for_upload(route)
    self._prune()
    self.last_record_ns = monotonic_ns - RECORD_INTERVAL_NS

  def _prune(self) -> None:
    files = sorted(self.root.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    total = 0
    for index, path in enumerate(files):
      total += path.stat().st_size
      if index >= MAX_FILES or (index > 0 and total > MAX_TOTAL_BYTES):
        path.unlink(missing_ok=True)

  def record(self, sample: dict, monotonic_ns: int | None = None) -> bool:
    now_ns = monotonic_ns if monotonic_ns is not None else time.monotonic_ns()
    self._open_route(now_ns)
    if now_ns - self.last_record_ns < RECORD_INTERVAL_NS or self.path is None:
      return False
    with self.path.open("a") as output:
      output.write(json.dumps(sample, separators=(",", ":"), allow_nan=False) + "\n")
    self.samples += 1
    self.last_record_ns = now_ns
    if now_ns - self.last_status_ns >= STATUS_INTERVAL_NS:
      self.params.put("AscentV8CalibrationStatus", self.status(now_ns))
      self.last_status_ns = now_ns
    return True

  def status(self, monotonic_ns: int | None = None) -> dict:
    return {
      "schema": 1, "recording": self.path is not None, "route": self.route,
      "file": self.path.name if self.path is not None else None,
      "bytes": self.path.stat().st_size if self.path is not None and self.path.exists() else 0,
      "samples": self.samples, "updated_monotonic_ns": monotonic_ns if monotonic_ns is not None else time.monotonic_ns(),
      "full_route_data": "loggerd rlog plus road-camera video",
    }
