#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


TARGET_CLASSES = {"stop sign", "traffic light"}
INFERENCE_FLOOR = 0.03
OBJECT_CONFIDENCE = 0.10
INFERENCE_SIZE = 1280
FRAME_RATE = 1.0
DEFAULT_FFMPEG = next((path for path in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/bin/ffmpeg")) if path.exists()),
                      Path("ffmpeg"))


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _finish_run(run: list[dict], minimum_frames: int) -> dict | None:
  if len(run) < minimum_frames:
    return None
  best = max(run, key=lambda item: item["confidence"])
  confirmation = run[minimum_frames - 1]
  return {
    "class_name": run[0]["class_name"],
    "first_route_offset_s": round(run[0]["route_offset_s"], 3),
    "last_route_offset_s": round(run[-1]["route_offset_s"], 3),
    "confirmation_route_offset_s": round(confirmation["route_offset_s"], 3),
    "confirmation_segment": confirmation["segment"],
    "confirmation_video_offset_s": round(confirmation["video_offset_s"], 3),
    "frames": len(run),
    "max_confidence": round(best["confidence"], 4),
    "best_segment": best["segment"],
    "best_video_offset_s": round(best["video_offset_s"], 3),
    "best_xyxy": best["xyxy"],
  }


def confirmed_runs(observations: list[dict], sample_interval_s: float, minimum_frames: int = 2) -> list[dict]:
  candidates = []
  maximum_gap_s = sample_interval_s * 1.25
  for class_name in sorted(TARGET_CLASSES):
    class_observations = sorted((item for item in observations if item["class_name"] == class_name),
                                key=lambda item: item["route_offset_s"])
    run: list[dict] = []
    for observation in class_observations:
      if run and observation["route_offset_s"] - run[-1]["route_offset_s"] > maximum_gap_s:
        candidate = _finish_run(run, minimum_frames)
        if candidate is not None:
          candidates.append(candidate)
        run = []
      run.append(observation)
    candidate = _finish_run(run, minimum_frames)
    if candidate is not None:
      candidates.append(candidate)
  return sorted(candidates, key=lambda item: item["first_route_offset_s"])


def run_counts_by_confidence(observations: list[dict], sample_interval_s: float,
                             thresholds: tuple[float, ...]) -> dict:
  result = {}
  for threshold in thresholds:
    runs = confirmed_runs([item for item in observations if item["confidence"] >= threshold], sample_interval_s)
    result[f"{threshold:.2f}"] = {
      "confirmed_runs": len(runs),
      "stop_sign_runs": sum(run["class_name"] == "stop sign" for run in runs),
      "traffic_light_runs": sum(run["class_name"] == "traffic light" for run in runs),
    }
  return result


def _extract_frames(ffmpeg: Path, video: Path, destination: Path, frame_rate: float) -> list[Path]:
  destination.mkdir(parents=True)
  subprocess.run([
    str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(video),
    "-vf", f"fps={frame_rate:g}", str(destination / "%04d.jpg"),
  ], check=True)
  return sorted(destination.glob("*.jpg"))


def _extract_confirmation(ffmpeg: Path, video: Path, offset_s: float, destination: Path) -> None:
  destination.parent.mkdir(parents=True, exist_ok=True)
  subprocess.run([
    str(ffmpeg), "-hide_banner", "-loglevel", "error", "-ss", f"{offset_s:.3f}", "-i", str(video),
    "-frames:v", "1", "-y", str(destination),
  ], check=True)


def _segment_number(video: Path) -> int:
  return int(video.parent.name.rsplit("--", 1)[1])


def select_route_videos(videos: list[Path], route: str | None) -> tuple[str, list[Path]]:
  routes = {video.parent.name.rsplit("--", 1)[0] for video in videos}
  if route is None:
    if len(routes) > 1:
      raise ValueError("multiple routes found; provide --route")
    route = next(iter(routes))
  selected = [video for video in videos if video.parent.name.rsplit("--", 1)[0] == route]
  if not selected:
    raise ValueError(f"route {route!r} has no qcamera.ts segments")
  return route, sorted(selected, key=_segment_number)


def main() -> None:
  parser = argparse.ArgumentParser(description="Scan a saved Ascent route for traffic-control review candidates")
  parser.add_argument("--video-root", type=Path, required=True)
  parser.add_argument("--route", help="route ID to select when --video-root contains more than one route")
  parser.add_argument("--model", type=Path, required=True)
  parser.add_argument("--output", type=Path, required=True)
  parser.add_argument("--confirmation-root", type=Path)
  parser.add_argument("--ffmpeg", type=Path, default=DEFAULT_FFMPEG)
  parser.add_argument("--frame-rate", type=float, default=FRAME_RATE)
  args = parser.parse_args()
  if args.frame_rate <= 0.0:
    parser.error("--frame-rate must be positive")

  try:
    from ultralytics import YOLO, __version__ as ultralytics_version
  except ImportError as error:
    raise SystemExit("run with an isolated environment that provides ultralytics") from error

  all_videos = list(args.video_root.glob("*/qcamera.ts"))
  if not all_videos:
    parser.error(f"no qcamera.ts segments found under {args.video_root}")
  try:
    route, videos = select_route_videos(all_videos, args.route)
  except ValueError as error:
    parser.error(str(error))
  model = YOLO(str(args.model))
  observations = []
  sampled_frames = 0

  with tempfile.TemporaryDirectory(prefix="ascent-v8-route-scan-") as temporary_root:
    for video in videos:
      segment = _segment_number(video)
      frames = _extract_frames(args.ffmpeg, video, Path(temporary_root) / str(segment), args.frame_rate)
      sampled_frames += len(frames)
      predictions = model.predict([str(path) for path in frames], imgsz=INFERENCE_SIZE, conf=INFERENCE_FLOOR,
                                  verbose=False)
      for frame_index, prediction in enumerate(predictions):
        best_by_class = {}
        for box in prediction.boxes:
          class_name = prediction.names[int(box.cls.item())]
          confidence = float(box.conf.item())
          if class_name not in TARGET_CLASSES or confidence < OBJECT_CONFIDENCE:
            continue
          x1, y1, x2, y2 = (round(float(value), 1) for value in box.xyxy[0])
          current = best_by_class.get(class_name)
          if current is None or confidence > current["confidence"]:
            video_offset_s = frame_index / args.frame_rate
            best_by_class[class_name] = {
              "class_name": class_name,
              "route_offset_s": segment * 60.0 + video_offset_s,
              "segment": segment,
              "video_offset_s": video_offset_s,
              "confidence": confidence,
              "xyxy": [x1, y1, x2, y2],
            }
        observations.extend(best_by_class.values())

  candidates = confirmed_runs(observations, 1.0 / args.frame_rate)
  threshold_counts = run_counts_by_confidence(observations, 1.0 / args.frame_rate, (0.10, 0.25, 0.50))
  if args.confirmation_root is not None:
    by_segment = {_segment_number(video): video for video in videos}
    for index, candidate in enumerate(candidates):
      filename = f"{index:03d}-{candidate['class_name'].replace(' ', '_')}-seg{candidate['best_segment']}.jpg"
      _extract_confirmation(args.ffmpeg, by_segment[candidate["best_segment"]], candidate["best_video_offset_s"],
                            args.confirmation_root / filename)
      candidate["confirmation_image"] = str(args.confirmation_root / filename)

  report = {
    "schema": 1,
    "purpose": "offline object-only route scan for human review; never signal state, ego relevance, or actuation",
    "route": route,
    "model": {"path": str(args.model), "sha256": _sha256(args.model), "ultralytics_version": ultralytics_version},
    "settings": {
      "frame_rate": args.frame_rate,
      "inference_size": INFERENCE_SIZE,
      "inference_floor": INFERENCE_FLOOR,
      "object_confidence": OBJECT_CONFIDENCE,
      "temporal_confirmation_frames": 2,
    },
    "limitations": [
      "qcamera resolution is proposal-only and can miss small distant controls",
      "multiple tracks may refer to the same physical control after a detection gap",
      "higher confidence can split one low-threshold run; threshold counts are fragments, not unique controls",
      "every candidate requires full-resolution human review and must not feed vehicle control",
    ],
    "summary": {
      "segments": len(videos),
      "sampled_frames": sampled_frames,
      "confirmed_runs": len(candidates),
      "stop_sign_runs": sum(candidate["class_name"] == "stop sign" for candidate in candidates),
      "traffic_light_runs": sum(candidate["class_name"] == "traffic light" for candidate in candidates),
      "run_fragments_by_confidence": threshold_counts,
    },
    "candidates": candidates,
    "observations": observations,
  }
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(report, indent=2) + "\n")
  print(json.dumps({"output": str(args.output), "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
  main()
