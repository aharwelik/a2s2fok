#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from math import sqrt
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

from openpilot.sunnypilot.selfdrive.ascent_v8.route_evidence import (
  apply_confirmed_labels,
  distance_between,
  load_calibration,
  load_labels,
  stop_candidates,
)


OBJECT_CONFIDENCE = 0.25
INFERENCE_FLOOR = 0.03
INFERENCE_SIZE = 1280
FRAME_RATE = 2.0
APPROACH_WINDOW_S = 20.0
TILE_SIZE = 760
SMOOTH_MAX_DECEL_MPS2 = 1.5
SMOOTH_MAX_JERK_MPS3 = 1.0
DEFAULT_FFMPEG = next((path for path in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/bin/ffmpeg")) if path.exists()),
                      Path("ffmpeg"))


def _iou(first: list[float], second: list[float]) -> float:
  left = max(first[0], second[0])
  top = max(first[1], second[1])
  right = min(first[2], second[2])
  bottom = min(first[3], second[3])
  intersection = max(0.0, right - left) * max(0.0, bottom - top)
  first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
  second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
  union = first_area + second_area - intersection
  return 0.0 if union <= 0.0 else intersection / union


def non_maximum_suppression(detections: list[dict], threshold: float = 0.5) -> list[dict]:
  kept: list[dict] = []
  for detection in sorted(detections, key=lambda item: item["confidence"], reverse=True):
    if all(detection["class_name"] != other["class_name"] or
           _iou(detection["xyxy"], other["xyxy"]) < threshold for other in kept):
      kept.append(detection)
  return kept


def classify_signal_phase_hsv(hsv: np.ndarray) -> str:
  if hsv.size == 0:
    return "unknown"
  hue, saturation, value = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
  bright = (saturation >= 100) & (value >= 170)
  scores = {
    "red": int((bright & ((hue <= 12) | (hue >= 170))).sum()),
    "yellow": int((bright & (hue >= 13) & (hue <= 40)).sum()),
    "green": int((bright & (hue >= 41) & (hue <= 100)).sum()),
  }
  ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
  minimum = max(3, round(hsv.shape[0] * hsv.shape[1] * 0.01))
  if ordered[0][1] < minimum or (ordered[1][1] > 0 and ordered[0][1] < ordered[1][1] * 2):
    return "unknown"
  return ordered[0][0]


def frame_decision(control_type: str, detections: list[dict], width: int, height: int) -> dict:
  detections = [detection for detection in detections if detection["confidence"] >= OBJECT_CONFIDENCE]
  expected_class = "stop sign" if control_type == "stop_sign" else "traffic light"
  expected = [detection for detection in detections if detection["class_name"] == expected_class]
  if control_type == "stop_sign":
    candidates = [detection for detection in expected
                  if (detection["xyxy"][0] + detection["xyxy"][2]) / 2 >= width * 0.5
                  and (detection["xyxy"][1] + detection["xyxy"][3]) / 2 <= height * 0.8]
    return {"object_detected": bool(expected), "relevance": "candidate" if candidates else "unknown",
            "phase_evidence": None, "phase": None}

  phased = [detection for detection in expected
            if detection.get("phase") != "unknown"
            and (detection["xyxy"][1] + detection["xyxy"][3]) / 2 <= height * 0.55
            and width * 0.05 <= (detection["xyxy"][0] + detection["xyxy"][2]) / 2 <= width * 0.95]
  phases = {detection["phase"] for detection in phased}
  phase_evidence = next(iter(phases)) if len(phases) == 1 else "unknown"
  if len(phased) < 2 or len(phases) != 1:
    return {"object_detected": bool(expected), "relevance": "unknown",
            "phase_evidence": phase_evidence, "phase": "unknown"}
  return {"object_detected": bool(expected), "relevance": "candidate",
          "phase_evidence": phase_evidence, "phase": phase_evidence}


def first_consecutive(frames: list[dict], predicate) -> dict | None:
  previous_index = None
  for frame in frames:
    if predicate(frame):
      if previous_index is not None and frame["frame_index"] == previous_index + 1:
        return frame
      previous_index = frame["frame_index"]
    else:
      previous_index = None
  return None


def required_constant_decel(speed_mps: float, distance_m: float) -> float | None:
  return None if distance_m <= 0.0 else speed_mps ** 2 / (2.0 * distance_m)


def jerk_limited_stop_distance(speed_mps: float, max_decel_mps2: float = SMOOTH_MAX_DECEL_MPS2,
                               max_jerk_mps3: float = SMOOTH_MAX_JERK_MPS3) -> float:
  ramp_time_s = max_decel_mps2 / max_jerk_mps3
  ramp_speed_reduction = 0.5 * max_jerk_mps3 * ramp_time_s ** 2
  if speed_mps <= ramp_speed_reduction:
    stop_time_s = sqrt(2.0 * speed_mps / max_jerk_mps3)
    return speed_mps * stop_time_s - max_jerk_mps3 * stop_time_s ** 3 / 6.0
  speed_after_ramp = speed_mps - ramp_speed_reduction
  ramp_distance = speed_mps * ramp_time_s - max_jerk_mps3 * ramp_time_s ** 3 / 6.0
  return ramp_distance + speed_after_ramp ** 2 / (2.0 * max_decel_mps2)


def stable_phase_transitions(frames: list[dict]) -> list[dict]:
  transitions = []
  previous_phase = None
  previous_frame = None
  for current in frames:
    phase = current["decision"]["phase"]
    if current["decision"]["relevance"] != "candidate" or phase in (None, "unknown"):
      previous_frame = None
      continue
    if (previous_frame is None or current["frame_index"] != previous_frame["frame_index"] + 1 or
        previous_frame["decision"] != current["decision"] or phase == previous_phase):
      previous_frame = current
      continue
    transition = {"phase": phase, "lead_s": current["lead_s"], "distance_m": current["distance_m"]}
    for key in ("speed_mps", "required_constant_decel_mps2", "smooth_stop_required_distance_m", "smooth_stop_margin_m"):
      if key in current:
        transition[key] = current[key]
    transitions.append(transition)
    previous_phase = phase
    previous_frame = current
  return transitions


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _extract_frames(ffmpeg: Path, video: Path, destination: Path, start_s: float, duration_s: float) -> list[Path]:
  destination.mkdir(parents=True)
  subprocess.run([
    str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(video), "-ss", f"{start_s:.3f}",
    "-t", f"{duration_s:.3f}", "-vf", f"fps={FRAME_RATE:g}", str(destination / "%04d.jpg"),
  ], check=True)
  return sorted(destination.glob("*.jpg"))


def _sources(image: np.ndarray) -> list[tuple[np.ndarray, int, int]]:
  height, width = image.shape[:2]
  tile = min(TILE_SIZE, height, width)
  sources = [(image, 0, 0)]
  for left in sorted({0, width - tile}):
    sources.append((image[0:tile, left:left + tile], left, 0))
  return sources


def _infer_event(model, cv2, frame_paths: list[Path]) -> tuple[list[np.ndarray], list[list[dict]]]:
  frames = [cv2.imread(str(path)) for path in frame_paths]
  sources = []
  mapping = []
  for frame_index, image in enumerate(frames):
    for source, left, top in _sources(image):
      sources.append(source)
      mapping.append((frame_index, left, top))
  predictions = model.predict(sources, imgsz=INFERENCE_SIZE, conf=INFERENCE_FLOOR, verbose=False)
  detections: list[list[dict]] = [[] for _ in frames]
  for prediction, (frame_index, left, top) in zip(predictions, mapping, strict=True):
    for box in prediction.boxes:
      class_name = prediction.names[int(box.cls.item())]
      if class_name not in ("stop sign", "traffic light"):
        continue
      x1, y1, x2, y2 = (float(value) for value in box.xyxy[0])
      detections[frame_index].append({
        "class_name": class_name,
        "confidence": round(float(box.conf.item()), 4),
        "xyxy": [round(x1 + left, 1), round(y1 + top, 1), round(x2 + left, 1), round(y2 + top, 1)],
      })
  for frame_index, image in enumerate(frames):
    detections[frame_index] = non_maximum_suppression(detections[frame_index])
    for detection in detections[frame_index]:
      detection["phase"] = None
      if detection["class_name"] == "traffic light":
        x1, y1, x2, y2 = (round(value) for value in detection["xyxy"])
        crop = image[max(0, y1):min(image.shape[0], y2 + 1), max(0, x1):min(image.shape[1], x2 + 1)]
        detection["phase"] = classify_signal_phase_hsv(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)) if crop.size else "unknown"
  return frames, detections


def main() -> None:
  parser = argparse.ArgumentParser(description="Run full-resolution tiled Ascent traffic-control replay")
  parser.add_argument("--labels", type=Path, required=True)
  parser.add_argument("--journal", type=Path, required=True)
  parser.add_argument("--realdata", type=Path, required=True)
  parser.add_argument("--model", type=Path, required=True)
  parser.add_argument("--ffmpeg", type=Path, default=DEFAULT_FFMPEG)
  parser.add_argument("--output", type=Path, required=True)
  parser.add_argument("--confirmation-root", type=Path)
  args = parser.parse_args()

  try:
    import cv2
    from ultralytics import YOLO, __version__ as ultralytics_version
  except ImportError as error:
    raise SystemExit("run with an isolated environment that provides ultralytics and OpenCV") from error

  labels = [label for label in load_labels(args.labels)
            if label.get("video_review") == "confirmed" and label.get("control_type") in ("stop_sign", "traffic_signal")]
  route, samples = load_calibration(args.journal)
  stops = stop_candidates(route, samples)
  apply_confirmed_labels(stops, labels)
  model = YOLO(str(args.model))
  event_reports = []

  with tempfile.TemporaryDirectory(prefix="ascent-v8-fullres-") as temporary_root:
    for label in labels:
      stop = min((event for event in stops if event.get("segment") == label["segment"] and event["label"] == label["control_type"]),
                 key=lambda event: abs(event["stopped_mono_ns"] - label["approx_mono_ns"]))
      video = args.realdata / f"{label['route']}--{label['segment']}" / "fcamera.hevc"
      start_s = max(0.0, float(label["video_offset_s"]) - APPROACH_WINDOW_S)
      frame_paths = _extract_frames(args.ffmpeg, video, Path(temporary_root) / str(label["approx_mono_ns"]),
                                    start_s, float(label["video_offset_s"]) - start_s + 0.01)
      images, detections = _infer_event(model, cv2, frame_paths)
      frames = []
      for index, (frame_path, image, frame_detections) in enumerate(zip(frame_paths, images, detections, strict=True)):
        video_offset_s = start_s + index / FRAME_RATE
        lead_s = max(0.0, float(label["video_offset_s"]) - video_offset_s)
        frame_mono_ns = int(label["approx_mono_ns"] - round(lead_s * 1e9))
        nearest_sample = min(samples, key=lambda sample: abs(int(sample["mono_ns"]) - frame_mono_ns))
        speed_mps = abs(float(nearest_sample.get("vehicle", {}).get("v_ego") or 0.0))
        distance_m = distance_between(samples, frame_mono_ns, stop["stopped_mono_ns"])
        required_decel = required_constant_decel(speed_mps, distance_m)
        smooth_stop_distance = jerk_limited_stop_distance(speed_mps)
        frames.append({
          "frame_index": index,
          "frame": frame_path.name,
          "video_offset_s": round(video_offset_s, 3),
          "lead_s": round(lead_s, 3),
          "distance_m": round(distance_m, 3),
          "speed_mps": round(speed_mps, 3),
          "required_constant_decel_mps2": None if required_decel is None else round(required_decel, 3),
          "smooth_stop_required_distance_m": round(smooth_stop_distance, 3),
          "smooth_stop_margin_m": round(distance_m - smooth_stop_distance, 3),
          "decision": frame_decision(label["control_type"], frame_detections, image.shape[1], image.shape[0]),
          "detections": frame_detections,
        })
      object_confirmation = first_consecutive(frames, lambda frame: frame["decision"]["object_detected"])
      expected_phase = label.get("state") if label["control_type"] == "traffic_signal" else None
      phase_confirmation = None if expected_phase is None else first_consecutive(
        frames, lambda frame, phase=expected_phase: frame["decision"]["phase_evidence"] == phase,
      )
      def state_matches(frame, control_type=label["control_type"], phase=expected_phase):
        return (frame["decision"]["relevance"] == "candidate" and
                (control_type == "stop_sign" or frame["decision"]["phase"] == phase))
      state_confirmation = first_consecutive(
        frames,
        state_matches,
      )
      if state_confirmation is not None and args.confirmation_root is not None:
        args.confirmation_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(frame_paths[state_confirmation["frame_index"]],
                     args.confirmation_root / f"{label['control_type']}-seg{label['segment']}-{state_confirmation['distance_m']:.3f}m.jpg")
      event_reports.append({
        "route": label["route"],
        "segment": label["segment"],
        "control_type": label["control_type"],
        "expected_state": label.get("state"),
        "source_video": str(video),
        "source_sha256": _sha256(video),
        "object_confirmation": None if object_confirmation is None else
          {key: object_confirmation[key] for key in
           ("frame", "lead_s", "distance_m", "speed_mps", "required_constant_decel_mps2",
            "smooth_stop_required_distance_m", "smooth_stop_margin_m", "decision")},
        "phase_confirmation": None if phase_confirmation is None else
          {key: phase_confirmation[key] for key in
           ("frame", "lead_s", "distance_m", "speed_mps", "required_constant_decel_mps2",
            "smooth_stop_required_distance_m", "smooth_stop_margin_m", "decision")},
        "state_relevance_confirmation": None if state_confirmation is None else
          {key: state_confirmation[key] for key in
           ("frame", "lead_s", "distance_m", "speed_mps", "required_constant_decel_mps2",
            "smooth_stop_required_distance_m", "smooth_stop_margin_m", "decision")},
        "stable_phase_transitions": stable_phase_transitions(frames),
        "frames": frames,
      })

  confirmed = [event for event in event_reports if event["state_relevance_confirmation"] is not None]
  phase_confirmed = [event for event in event_reports if event["phase_confirmation"] is not None]
  report = {
    "schema": 1,
    "purpose": "offline full-resolution proposal, phase, and relevance-candidate replay; never vehicle actuation",
    "model": {"path": str(args.model), "sha256": _sha256(args.model), "ultralytics_version": ultralytics_version},
    "settings": {
      "frame_rate": FRAME_RATE, "approach_window_s": APPROACH_WINDOW_S, "tile_size": TILE_SIZE,
      "inference_size": INFERENCE_SIZE, "inference_floor": INFERENCE_FLOOR,
      "object_confidence": OBJECT_CONFIDENCE, "temporal_confirmation_frames": 2,
      "smooth_max_decel_mps2": SMOOTH_MAX_DECEL_MPS2, "smooth_max_jerk_mps3": SMOOTH_MAX_JERK_MPS3,
      "smooth_stop_latency_s": 0.0,
    },
    "limitations": [
      "ego relevance is a conservative image-position and same-phase cluster candidate, not validated map/lane ownership",
      "red/yellow/green HSV phase scoring has only three red approaches in this route and no green held-out validation",
      "five approaches are far below the release gate and this output must not feed braking",
    ],
    "summary": {
      "approaches": len(event_reports),
      "state_relevance_candidates_confirmed": len(confirmed),
      "confirmed_by_40m": sum(event["state_relevance_confirmation"]["distance_m"] >= 40.0 for event in confirmed),
      "stop_signs_confirmed_by_40m": sum(event["control_type"] == "stop_sign" and
                                           event["state_relevance_confirmation"]["distance_m"] >= 40.0 for event in confirmed),
      "signals_confirmed_by_40m": sum(event["control_type"] == "traffic_signal" and
                                       event["state_relevance_confirmation"]["distance_m"] >= 40.0 for event in confirmed),
      "signal_phase_confirmed_by_40m": sum(event["phase_confirmation"]["distance_m"] >= 40.0 for event in phase_confirmed),
      "smoothly_stoppable_at_confirmation": sum(event["state_relevance_confirmation"]["smooth_stop_margin_m"] >= 0.0
                                                 for event in confirmed),
      "ego_relevance_ground_truth_confirmed": 0,
    },
    "events": event_reports,
  }
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(report, indent=2) + "\n")
  print(json.dumps({"output": str(args.output), "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
  main()
