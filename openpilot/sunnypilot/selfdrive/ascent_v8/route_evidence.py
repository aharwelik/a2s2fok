from __future__ import annotations

import json
from pathlib import Path


APPROACH_SPEED_MPS = 5.0
STOPPED_SPEED_MPS = 0.3
PRE_STOP_WINDOW_NS = 20_000_000_000
POST_STOP_WINDOW_NS = 3_000_000_000


def load_calibration(path: Path) -> tuple[str, list[dict]]:
  route = path.stem
  samples: list[dict] = []
  with path.open() as source:
    for line in source:
      item = json.loads(line)
      if item.get("kind") == "ascent_v8_calibration":
        route = str(item.get("route") or route)
      elif "mono_ns" in item:
        samples.append(item)
  samples.sort(key=lambda item: int(item["mono_ns"]))
  return route, samples


def _bool_any(samples: list[dict], *keys: str) -> bool:
  return any(bool(_value(sample, *keys)) for sample in samples)


def _value(sample: dict, *keys: str):
  value = sample
  for key in keys:
    if not isinstance(value, dict):
      return None
    value = value.get(key)
  return value


def stop_candidates(route: str, samples: list[dict]) -> list[dict]:
  stop_indices: list[int] = []
  approach_armed = False
  stopped = True
  for index, sample in enumerate(samples):
    speed = abs(float(_value(sample, "vehicle", "v_ego") or 0.0))
    if speed >= APPROACH_SPEED_MPS:
      approach_armed = True
      stopped = False
    elif speed <= STOPPED_SPEED_MPS and approach_armed and not stopped:
      stop_indices.append(index)
      approach_armed = False
      stopped = True

  events: list[dict] = []
  for stop_index in stop_indices:
    stop_ns = int(samples[stop_index]["mono_ns"])
    before = [sample for sample in samples if stop_ns - PRE_STOP_WINDOW_NS <= int(sample["mono_ns"]) <= stop_ns]
    around = [sample for sample in samples if stop_ns - PRE_STOP_WINDOW_NS <= int(sample["mono_ns"]) <= stop_ns + POST_STOP_WINDOW_NS]
    lead_samples = [sample for sample in before if _value(sample, "evidence", "lead_distance_m") is not None]
    last_lead_ns = int(lead_samples[-1]["mono_ns"]) if lead_samples else None
    model_stop_samples = [sample for sample in around if _value(sample, "model", "should_stop")]
    first_model_stop_ns = int(model_stop_samples[0]["mono_ns"]) if model_stop_samples else None

    events.append({
      "route": route,
      "stopped_mono_ns": stop_ns,
      "approach_speed_mps": round(max(abs(float(_value(sample, "vehicle", "v_ego") or 0.0)) for sample in before), 3),
      "driver_braked": _bool_any(before, "vehicle", "brake_pressed"),
      "lead_seen": bool(lead_samples),
      "lead_lost_before_stop_s": None if last_lead_ns is None else round((stop_ns - last_lead_ns) / 1e9, 3),
      "model_stop_while_moving": any(
        bool(_value(sample, "model", "should_stop")) and abs(float(_value(sample, "vehicle", "v_ego") or 0.0)) > STOPPED_SPEED_MPS
        for sample in around
      ),
      "first_model_stop_relative_s": None if first_model_stop_ns is None else round((first_model_stop_ns - stop_ns) / 1e9, 3),
      "planner_stop": _bool_any(around, "plan", "should_stop"),
      "comma_longitudinal_active": _bool_any(before, "control", "long_active"),
      "comma_brake_output": _bool_any(before, "control", "output_brake"),
      "label": "unreviewed",
    })
  return events


def analyze_files(paths: list[Path]) -> dict:
  routes = []
  events = []
  for path in paths:
    route, samples = load_calibration(path)
    route_events = stop_candidates(route, samples)
    routes.append({"route": route, "samples": len(samples), "candidate_stops": len(route_events)})
    events.extend(route_events)
  return {
    "routes": routes,
    "candidate_stops": events,
    "coverage": {
      "recorded_journals": len(routes),
      "unreviewed_stop_candidates": len(events),
      "qualified_routes": 0,
      "labeled_stop_sign_approaches": 0,
      "labeled_signal_approaches": 0,
      "required_validation_routes": 25,
      "required_stop_sign_approaches": 300,
      "required_signal_approaches": 300,
    },
  }
