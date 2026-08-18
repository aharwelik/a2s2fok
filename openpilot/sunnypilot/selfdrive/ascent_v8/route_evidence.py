from __future__ import annotations

import json
from math import isfinite, sqrt
from pathlib import Path
from statistics import median


APPROACH_SPEED_MPS = 5.0
STOPPED_SPEED_MPS = 0.3
PRE_STOP_WINDOW_NS = 20_000_000_000
POST_STOP_WINDOW_NS = 3_000_000_000
LABEL_MATCH_TOLERANCE_NS = 2_000_000_000
CURVE_ENTRY_SPEED_MPS = 3.0
CURVE_ENTER_ABS_CURVATURE = 0.003
CURVE_EXIT_ABS_CURVATURE = 0.002
CURVE_EXIT_GAP_NS = 500_000_000
CURVE_MIN_DURATION_NS = 1_000_000_000
STANDARD_LATERAL_ACCEL_MPS2 = 1.6
RESPONSE_SIGNALS = (
  "model_stop",
  "planner_stop",
  "planner_lead",
  "planner_decel",
  "driver_brake",
  "comma_longitudinal",
  "comma_brake",
)
CONFIRMED_LABEL_TYPES = (
  "stop_sign",
  "traffic_signal",
  "lead_stop",
  "cross_traffic_stop",
  "maneuver_stop",
)


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


def _distance_between(samples: list[dict], start_ns: int, stop_ns: int) -> float:
  points = [sample for sample in samples if start_ns <= int(sample["mono_ns"]) <= stop_ns]
  distance = 0.0
  for previous, current in zip(points, points[1:], strict=False):
    elapsed_s = (int(current["mono_ns"]) - int(previous["mono_ns"])) / 1e9
    previous_speed = abs(float(_value(previous, "vehicle", "v_ego") or 0.0))
    current_speed = abs(float(_value(current, "vehicle", "v_ego") or 0.0))
    distance += (previous_speed + current_speed) * 0.5 * elapsed_s
  return distance


def _trigger_timing(samples: list[dict], stop_ns: int, predicate) -> dict | None:
  triggered = next((sample for sample in samples if predicate(sample)), None)
  if triggered is None:
    return None
  trigger_ns = int(triggered["mono_ns"])
  return {
    "lead_s": round((stop_ns - trigger_ns) / 1e9, 3),
    "distance_m": round(_distance_between(samples, trigger_ns, stop_ns), 3),
  }


def stop_candidates(route: str, samples: list[dict]) -> list[dict]:
  stop_indices: list[tuple[int, int]] = []
  approach_armed = False
  approach_index = 0
  stopped = True
  for index, sample in enumerate(samples):
    speed = abs(float(_value(sample, "vehicle", "v_ego") or 0.0))
    if speed >= APPROACH_SPEED_MPS:
      if not approach_armed:
        approach_index = index
      approach_armed = True
      stopped = False
    elif speed <= STOPPED_SPEED_MPS and approach_armed and not stopped:
      stop_indices.append((approach_index, index))
      approach_armed = False
      stopped = True

  events: list[dict] = []
  for approach_index, stop_index in stop_indices:
    stop_ns = int(samples[stop_index]["mono_ns"])
    approach_ns = max(stop_ns - PRE_STOP_WINDOW_NS, int(samples[approach_index]["mono_ns"]))
    before = [sample for sample in samples if approach_ns <= int(sample["mono_ns"]) <= stop_ns]
    around = [sample for sample in samples if approach_ns <= int(sample["mono_ns"]) <= stop_ns + POST_STOP_WINDOW_NS]
    lead_samples = [sample for sample in before if _value(sample, "evidence", "lead_distance_m") is not None]
    last_lead_ns = int(lead_samples[-1]["mono_ns"]) if lead_samples else None
    model_stop_samples = [sample for sample in around if _value(sample, "model", "should_stop")]
    first_model_stop_ns = int(model_stop_samples[0]["mono_ns"]) if model_stop_samples else None
    response_timing = {
      "model_stop": _trigger_timing(before, stop_ns, lambda sample: bool(_value(sample, "model", "should_stop"))),
      "planner_stop": _trigger_timing(before, stop_ns, lambda sample: bool(_value(sample, "plan", "should_stop"))),
      "planner_lead": _trigger_timing(before, stop_ns, lambda sample: bool(_value(sample, "plan", "has_lead"))),
      "planner_decel": _trigger_timing(before, stop_ns, lambda sample: float(_value(sample, "plan", "a_target") or 0.0) < -0.1),
      "driver_brake": _trigger_timing(before, stop_ns, lambda sample: bool(_value(sample, "vehicle", "brake_pressed"))),
      "comma_longitudinal": _trigger_timing(before, stop_ns, lambda sample: bool(_value(sample, "control", "long_active"))),
      "comma_brake": _trigger_timing(before, stop_ns, lambda sample: float(_value(sample, "control", "output_brake") or 0.0) > 0.0),
    }

    events.append({
      "route": route,
      "approach_mono_ns": approach_ns,
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
      "response_timing": response_timing,
      "label": "unreviewed",
    })
  return events


def load_labels(path: Path) -> list[dict]:
  with path.open() as source:
    return [json.loads(line) for line in source if line.strip()]


def apply_confirmed_labels(events: list[dict], labels: list[dict]) -> int:
  matched_indices: set[int] = set()
  confirmed_labels = [
    label for label in labels
    if label.get("video_review") == "confirmed"
    and label.get("control_type") in CONFIRMED_LABEL_TYPES
    and label.get("approx_mono_ns") is not None
  ]
  for label in confirmed_labels:
    candidates = [
      (abs(int(event["stopped_mono_ns"]) - int(label["approx_mono_ns"])), index)
      for index, event in enumerate(events)
      if index not in matched_indices and event["route"] == label.get("route")
    ]
    if not candidates:
      continue
    delta_ns, index = min(candidates)
    if delta_ns > LABEL_MATCH_TOLERANCE_NS:
      continue
    events[index].update({
      "label": label["control_type"],
      "label_state": label.get("state"),
      "label_source": label.get("source"),
      "label_visibility": label.get("visibility"),
      "observed_behavior": label.get("behavior"),
      "driver_intervention": label.get("intervention"),
      "segment": label.get("segment"),
      "video_offset_s": label.get("video_offset_s"),
      "video_review": "confirmed",
    })
    matched_indices.add(index)
  return len(confirmed_labels) - len(matched_indices)


def summarize_responses(events: list[dict]) -> dict:
  summary = {}
  for label in CONFIRMED_LABEL_TYPES:
    labeled = [event for event in events if event["label"] == label]
    if not labeled:
      continue
    summary[label] = {
      "approaches": len(labeled),
      "driver_braked": sum(event["driver_braked"] for event in labeled),
      "lead_seen": sum(event["lead_seen"] for event in labeled),
      "model_stop_while_moving": sum(event["model_stop_while_moving"] for event in labeled),
      "planner_stop": sum(event["planner_stop"] for event in labeled),
      "comma_longitudinal_active": sum(event["comma_longitudinal_active"] for event in labeled),
      "comma_brake_output": sum(event["comma_brake_output"] for event in labeled),
    }
  traffic_controls = [event for event in events if event["label"] in ("stop_sign", "traffic_signal")]
  if traffic_controls:
    summary["traffic_control_total"] = {
      "approaches": len(traffic_controls),
      "model_stop_while_moving": sum(event["model_stop_while_moving"] for event in traffic_controls),
      "planner_stop": sum(event["planner_stop"] for event in traffic_controls),
      "comma_longitudinal_active": sum(event["comma_longitudinal_active"] for event in traffic_controls),
      "comma_brake_output": sum(event["comma_brake_output"] for event in traffic_controls),
    }
  return summary


def summarize_timing(events: list[dict]) -> dict:
  def group_timing(group: list[dict]) -> dict:
    responses = {}
    for signal in RESPONSE_SIGNALS:
      timings = [event["response_timing"][signal] for event in group if event["response_timing"][signal] is not None]
      before_stop = [timing for timing in timings if timing["lead_s"] > 0.0]
      responses[signal] = {
        "before_stop": len(before_stop),
        "lead_s_median": None if not before_stop else round(median(timing["lead_s"] for timing in before_stop), 3),
        "distance_m_median": None if not before_stop else round(median(timing["distance_m"] for timing in before_stop), 3),
      }
    lead_losses = [event["lead_lost_before_stop_s"] for event in group if event["lead_lost_before_stop_s"] is not None]
    return {
      "approaches": len(group),
      "responses": responses,
      "lead_seen": sum(event["lead_seen"] for event in group),
      "lead_lost_before_stop_s_median": None if not lead_losses else round(median(lead_losses), 3),
    }

  summary = {}
  for label in CONFIRMED_LABEL_TYPES:
    labeled = [event for event in events if event["label"] == label]
    if labeled:
      summary[label] = group_timing(labeled)
  traffic_controls = [event for event in events if event["label"] in ("stop_sign", "traffic_signal")]
  if traffic_controls:
    summary["traffic_control_total"] = group_timing(traffic_controls)
  return summary


def _curve_event(route: str, event_samples: list[dict]) -> dict | None:
  duration_ns = int(event_samples[-1]["mono_ns"]) - int(event_samples[0]["mono_ns"])
  if duration_ns < CURVE_MIN_DURATION_NS:
    return None
  peak_index, peak = max(enumerate(event_samples), key=lambda pair: abs(float(pair[1]["curvature"])))
  peak_curvature = abs(float(peak["curvature"]))
  speed_at_peak = abs(float(_value(peak, "vehicle", "v_ego") or 0.0))
  target_speed = sqrt(STANDARD_LATERAL_ACCEL_MPS2 / peak_curvature)
  lane_confidences = [float(sample["lane_confidence"]) for sample in event_samples
                      if sample.get("lane_confidence") is not None and isfinite(float(sample["lane_confidence"]))]
  left_blinker = any(bool(_value(sample, "vehicle", "left_blinker")) for sample in event_samples)
  right_blinker = any(bool(_value(sample, "vehicle", "right_blinker")) for sample in event_samples)
  if left_blinker and right_blinker:
    signal = "both"
  elif left_blinker:
    signal = "left"
  elif right_blinker:
    signal = "right"
  else:
    signal = None
  return {
    "route": route,
    "start_mono_ns": int(event_samples[0]["mono_ns"]),
    "end_mono_ns": int(event_samples[-1]["mono_ns"]),
    "start_segment": event_samples[0].get("segment"),
    "end_segment": event_samples[-1].get("segment"),
    "event_type": "curve_with_turn_signal" if signal is not None else "curve",
    "turn_signal": signal,
    "direction": "left" if float(peak["curvature"]) > 0.0 else "right",
    "duration_s": round(duration_ns / 1e9, 3),
    "entry_speed_mps": round(abs(float(_value(event_samples[0], "vehicle", "v_ego") or 0.0)), 3),
    "minimum_speed_mps": round(min(abs(float(_value(sample, "vehicle", "v_ego") or 0.0)) for sample in event_samples), 3),
    "speed_at_peak_curvature_mps": round(speed_at_peak, 3),
    "peak_curvature": round(peak_curvature, 6),
    "peak_lateral_accel_mps2": round(max(abs(float(_value(sample, "vehicle", "v_ego") or 0.0)) ** 2 *
                                                   abs(float(sample["curvature"])) for sample in event_samples), 3),
    "standard_target_speed_mps": round(target_speed, 3),
    "target_excess_at_peak_mps": round(speed_at_peak - target_speed, 3),
    "speed_reduction_before_peak_mps": round(abs(float(_value(event_samples[0], "vehicle", "v_ego") or 0.0)) - speed_at_peak, 3),
    "lane_confidence_min": None if not lane_confidences else round(min(lane_confidences), 3),
    "lane_confidence_median": None if not lane_confidences else round(median(lane_confidences), 3),
    "lane_confidence_coverage": round(len(lane_confidences) / len(event_samples), 3),
    "driver_braked": any(bool(_value(sample, "vehicle", "brake_pressed")) for sample in event_samples),
    "driver_braked_before_peak": any(bool(_value(sample, "vehicle", "brake_pressed")) for sample in event_samples[:peak_index + 1]),
    "driver_steering_override": any(bool(_value(sample, "vehicle", "steering_pressed")) for sample in event_samples),
    "steering_saturated": any(bool(sample.get("steering_saturated")) for sample in event_samples),
    "lateral_control_active": any(bool(sample.get("lat_active")) for sample in event_samples),
    "samples": len(event_samples),
  }


def curve_candidates(route: str, samples: list[dict]) -> list[dict]:
  samples = sorted(samples, key=lambda sample: int(sample["mono_ns"]))
  events: list[dict] = []
  start_index: int | None = None
  last_curve_index: int | None = None
  previous_ns: int | None = None

  def finish() -> None:
    nonlocal start_index, last_curve_index
    if start_index is not None and last_curve_index is not None:
      event = _curve_event(route, samples[start_index:last_curve_index + 1])
      if event is not None:
        events.append(event)
    start_index = None
    last_curve_index = None

  for index, sample in enumerate(samples):
    mono_ns = int(sample["mono_ns"])
    if start_index is not None and previous_ns is not None and mono_ns - previous_ns > CURVE_EXIT_GAP_NS:
      finish()
    speed = abs(float(_value(sample, "vehicle", "v_ego") or 0.0))
    curvature = abs(float(sample.get("curvature") or 0.0))
    if start_index is None:
      if speed >= CURVE_ENTRY_SPEED_MPS and curvature >= CURVE_ENTER_ABS_CURVATURE:
        start_index = index
        last_curve_index = index
    elif speed >= CURVE_ENTRY_SPEED_MPS and curvature >= CURVE_EXIT_ABS_CURVATURE:
      last_curve_index = index
    elif last_curve_index is not None and mono_ns - int(samples[last_curve_index]["mono_ns"]) > CURVE_EXIT_GAP_NS:
      finish()
    previous_ns = mono_ns
  finish()
  return events


def summarize_curves(events: list[dict]) -> dict:
  return {
    "events": len(events),
    "curves_with_turn_signal": sum(event["event_type"] == "curve_with_turn_signal" for event in events),
    "driver_braked": sum(event["driver_braked"] for event in events),
    "driver_steering_override": sum(event["driver_steering_override"] for event in events),
    "steering_saturated": sum(event["steering_saturated"] for event in events),
    "above_standard_target_at_peak": sum(event["target_excess_at_peak_mps"] > 0.0 for event in events),
    "lane_confidence_below_half_any": sum(event["lane_confidence_min"] is not None and event["lane_confidence_min"] < 0.5 for event in events),
    "peak_lateral_accel_mps2_max": None if not events else round(max(event["peak_lateral_accel_mps2"] for event in events), 3),
  }


def _lateral_saturated(controls_state) -> bool:
  try:
    lateral_state = controls_state.lateralControlState
    return bool(getattr(lateral_state, lateral_state.which()).saturated)
  except Exception:
    return False


def load_qlog_curve_samples(paths: list[Path]) -> dict[str, list[dict]]:
  from openpilot.tools.lib.logreader import LogReader

  routes: dict[str, list[dict]] = {}
  for path in paths:
    try:
      route, segment_text = path.parent.name.rsplit("--", 1)
      segment = int(segment_text)
    except (ValueError, TypeError):
      route = path.parent.name
      segment = None
    latest_car = None
    latest_car_control = None
    latest_model = None
    latest_model_ns = 0
    for message in LogReader(str(path), sort_by_time=True):
      kind = message.which()
      if kind == "carState":
        latest_car = message.carState
      elif kind == "carControl":
        latest_car_control = message.carControl
      elif kind == "drivingModelData":
        latest_model = message.drivingModelData
        latest_model_ns = int(message.logMonoTime)
      elif kind == "controlsState" and latest_car is not None:
        mono_ns = int(message.logMonoTime)
        controls_state = message.controlsState
        lane_confidence = None
        if latest_model is not None and mono_ns - latest_model_ns <= 1_000_000_000:
          lane_confidence = min(float(latest_model.laneLineMeta.leftProb), float(latest_model.laneLineMeta.rightProb))
        routes.setdefault(route, []).append({
          "mono_ns": mono_ns,
          "segment": segment,
          "vehicle": {
            "v_ego": float(latest_car.vEgo),
            "brake_pressed": bool(latest_car.brakePressed),
            "steering_pressed": bool(latest_car.steeringPressed),
            "left_blinker": bool(latest_car.leftBlinker),
            "right_blinker": bool(latest_car.rightBlinker),
          },
          "curvature": float(controls_state.curvature),
          "desired_curvature": float(controls_state.desiredCurvature),
          "lane_confidence": lane_confidence,
          "steering_saturated": _lateral_saturated(controls_state),
          "lat_active": bool(latest_car_control.latActive) if latest_car_control is not None else False,
        })
  return routes


def analyze_files(paths: list[Path], labels_path: Path | None = None, qlog_paths: list[Path] | None = None) -> dict:
  routes = []
  events = []
  for path in paths:
    route, samples = load_calibration(path)
    route_events = stop_candidates(route, samples)
    routes.append({"route": route, "samples": len(samples), "candidate_stops": len(route_events)})
    events.extend(route_events)
  unmatched_confirmed_labels = 0
  if labels_path is not None:
    unmatched_confirmed_labels = apply_confirmed_labels(events, load_labels(labels_path))
  labeled_events = [event for event in events if event["label"] != "unreviewed"]
  report = {
    "routes": routes,
    "candidate_stops": events,
    "response_summary": summarize_responses(events),
    "timing_summary": summarize_timing(events),
    "coverage": {
      "recorded_journals": len(routes),
      "unreviewed_stop_candidates": len(events) - len(labeled_events),
      "qualified_routes": len({event["route"] for event in labeled_events}),
      "video_confirmed_approaches": len(labeled_events),
      "labeled_stop_sign_approaches": sum(event["label"] == "stop_sign" for event in labeled_events),
      "labeled_signal_approaches": sum(event["label"] == "traffic_signal" for event in labeled_events),
      "labeled_lead_stop_approaches": sum(event["label"] == "lead_stop" for event in labeled_events),
      "labeled_cross_traffic_approaches": sum(event["label"] == "cross_traffic_stop" for event in labeled_events),
      "labeled_maneuver_stop_approaches": sum(event["label"] == "maneuver_stop" for event in labeled_events),
      "unmatched_confirmed_labels": unmatched_confirmed_labels,
      "required_validation_routes": 25,
      "required_stop_sign_approaches": 300,
      "required_signal_approaches": 300,
    },
  }
  if qlog_paths is not None:
    curve_samples = load_qlog_curve_samples(qlog_paths)
    curve_events = [event for route, samples in curve_samples.items() for event in curve_candidates(route, samples)]
    report.update({
      "curve_replay": {
        "qlogs": len(qlog_paths),
        "samples": sum(len(samples) for samples in curve_samples.values()),
        "routes": len(curve_samples),
      },
      "curve_events": curve_events,
      "curve_summary": summarize_curves(curve_events),
    })
  return report
