#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from openpilot.sunnypilot.selfdrive.ascent_v8.route_evidence import load_labels


EARTH_RADIUS_M = 6_371_000.0
DEFAULT_MAX_GPS_ACCURACY_M = 10.0
DEFAULT_LABEL_MATCH_DISTANCE_M = 50.0
DEFAULT_ROUTE_NODE_DISTANCE_M = 30.0


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def haversine_m(first_lat: float, first_lon: float, second_lat: float, second_lon: float) -> float:
  first_phi = radians(first_lat)
  second_phi = radians(second_lat)
  delta_phi = radians(second_lat - first_lat)
  delta_lambda = radians(second_lon - first_lon)
  value = sin(delta_phi / 2.0) ** 2 + cos(first_phi) * cos(second_phi) * sin(delta_lambda / 2.0) ** 2
  return 2.0 * EARTH_RADIUS_M * asin(sqrt(value))


def evaluate_labels(labels: list[dict], points: list[dict], nodes: list[dict], match_distance_m: float) -> list[dict]:
  results = []
  for label in labels:
    if label.get("video_review") not in (None, "confirmed") or label.get("control_type") not in ("stop_sign", "traffic_signal"):
      continue
    point = min(points, key=lambda item: abs(item["mono_ns"] - label["approx_mono_ns"]))
    highway = "stop" if label["control_type"] == "stop_sign" else "traffic_signals"
    matching_nodes = [node for node in nodes if node.get("tags", {}).get("highway") == highway]
    nearest = min(matching_nodes, key=lambda node: haversine_m(point["lat"], point["lon"], node["lat"], node["lon"]))
    distance_m = haversine_m(point["lat"], point["lon"], nearest["lat"], nearest["lon"])
    results.append({
      "segment": label["segment"],
      "control_type": label["control_type"],
      "state": label.get("state"),
      "gps_age_s": round(abs(point["mono_ns"] - label["approx_mono_ns"]) / 1e9, 3),
      "gps_accuracy_m": round(point["accuracy_m"], 3),
      "nearest_osm_id": nearest["id"],
      "nearest_osm_distance_m": round(distance_m, 3),
      "map_match": distance_m <= match_distance_m,
      "osm_tags": nearest.get("tags", {}),
    })
  return results


def extract_gps_points(qlogs: list[Path], max_accuracy_m: float) -> list[dict]:
  from openpilot.tools.lib.logreader import LogReader

  points = []
  for qlog in qlogs:
    segment = int(qlog.parent.name.rsplit("--", 1)[1])
    for message in LogReader(str(qlog)):
      if message.which() != "gpsLocationExternal":
        continue
      gps = message.gpsLocationExternal
      if not gps.hasFix or gps.horizontalAccuracy > max_accuracy_m or not gps.latitude or not gps.longitude:
        continue
      points.append({
        "segment": segment,
        "mono_ns": int(message.logMonoTime),
        "lat": float(gps.latitude),
        "lon": float(gps.longitude),
        "accuracy_m": float(gps.horizontalAccuracy),
      })
  return points


def route_node_matches(nodes: list[dict], points: list[dict], maximum_distance_m: float) -> list[dict]:
  matches = []
  for node in nodes:
    nearest_point = min(points, key=lambda point: haversine_m(point["lat"], point["lon"], node["lat"], node["lon"]))
    distance_m = haversine_m(nearest_point["lat"], nearest_point["lon"], node["lat"], node["lon"])
    if distance_m <= maximum_distance_m:
      matches.append({
        "osm_id": node["id"],
        "highway": node.get("tags", {}).get("highway"),
        "nearest_route_distance_m": round(distance_m, 3),
        "nearest_route_segment": nearest_point["segment"],
        "osm_tags": node.get("tags", {}),
      })
  return sorted(matches, key=lambda item: (item["nearest_route_segment"], item["nearest_route_distance_m"]))


def main() -> None:
  parser = argparse.ArgumentParser(description="Evaluate OSM traffic-control nodes as an offline Ascent route prior")
  parser.add_argument("--qlog-root", type=Path, required=True)
  parser.add_argument("--labels", type=Path, required=True)
  parser.add_argument("--osm", type=Path, required=True)
  parser.add_argument("--output", type=Path, required=True)
  parser.add_argument("--max-gps-accuracy-m", type=float, default=DEFAULT_MAX_GPS_ACCURACY_M)
  parser.add_argument("--label-match-distance-m", type=float, default=DEFAULT_LABEL_MATCH_DISTANCE_M)
  parser.add_argument("--route-node-distance-m", type=float, default=DEFAULT_ROUTE_NODE_DISTANCE_M)
  args = parser.parse_args()

  qlogs = sorted(args.qlog_root.glob("*/qlog.zst"), key=lambda path: int(path.parent.name.rsplit("--", 1)[1]))
  if not qlogs:
    parser.error(f"no qlog.zst segments found under {args.qlog_root}")
  labels = load_labels(args.labels)
  osm = json.loads(args.osm.read_text())
  nodes = [element for element in osm.get("elements", [])
           if element.get("type") == "node" and element.get("tags", {}).get("highway") in ("stop", "traffic_signals")]
  if not nodes:
    parser.error("OSM input has no highway=stop or highway=traffic_signals nodes")
  points = extract_gps_points(qlogs, args.max_gps_accuracy_m)
  if not points:
    parser.error("saved qlogs have no qualifying GPS fixes")

  label_results = evaluate_labels(labels, points, nodes, args.label_match_distance_m)
  node_matches = route_node_matches(nodes, points, args.route_node_distance_m)
  report = {
    "schema": 1,
    "purpose": "offline map anticipation prior evaluation; never signal phase, right-of-way, or actuation",
    "route": qlogs[0].parent.name.rsplit("--", 1)[0],
    "osm": {
      "path": str(args.osm),
      "sha256": _sha256(args.osm),
      "timestamp_osm_base": osm.get("osm3s", {}).get("timestamp_osm_base"),
      "copyright": osm.get("osm3s", {}).get("copyright"),
    },
    "settings": {
      "max_gps_accuracy_m": args.max_gps_accuracy_m,
      "label_match_distance_m": args.label_match_distance_m,
      "route_node_distance_m": args.route_node_distance_m,
    },
    "summary": {
      "gps_points": len(points),
      "osm_control_nodes": len(nodes),
      "route_nearby_nodes": len(node_matches),
      "route_nearby_stop_nodes": sum(match["highway"] == "stop" for match in node_matches),
      "route_nearby_signal_nodes": sum(match["highway"] == "traffic_signals" for match in node_matches),
      "labeled_controls": len(label_results),
      "labeled_controls_map_matched": sum(result["map_match"] for result in label_results),
      "stop_sign_labels_map_matched": sum(result["control_type"] == "stop_sign" and result["map_match"]
                                            for result in label_results),
      "signal_labels_map_matched": sum(result["control_type"] == "traffic_signal" and result["map_match"]
                                         for result in label_results),
    },
    "limitations": [
      "OSM inventory can be missing or stale and is not traffic-signal phase data",
      "distance alone does not establish approach direction, ego lane, stop line, or right-of-way",
      "map absence must never suppress a camera control candidate",
    ],
    "labeled_controls": label_results,
    "route_nearby_nodes": node_matches,
  }
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(report, indent=2) + "\n")
  print(json.dumps({"output": str(args.output), "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
  main()
