import numpy as np
from math import isclose

from tools.ascent_v8_perception_replay import (
  classify_signal_phase_hsv,
  first_consecutive,
  frame_decision,
  jerk_limited_stop_distance,
  non_maximum_suppression,
  required_constant_decel,
  stable_phase_transitions,
)


def test_signal_phase_requires_bright_dominant_color():
  red = np.zeros((10, 10, 3), dtype=np.uint8)
  red[2:5, 2:5] = (2, 220, 220)
  assert classify_signal_phase_hsv(red) == "red"

  yellow = np.zeros((10, 10, 3), dtype=np.uint8)
  yellow[2:5, 2:5] = (25, 220, 220)
  assert classify_signal_phase_hsv(yellow) == "yellow"

  green = np.zeros((10, 10, 3), dtype=np.uint8)
  green[2:5, 2:5] = (65, 220, 220)
  assert classify_signal_phase_hsv(green) == "green"

  disagreement = red.copy()
  disagreement[6:9, 6:9] = (25, 220, 220)
  assert classify_signal_phase_hsv(disagreement) == "unknown"
  assert classify_signal_phase_hsv(np.zeros((10, 10, 3), dtype=np.uint8)) == "unknown"


def test_nms_merges_tiled_duplicates_but_not_other_classes():
  detections = [
    {"class_name": "traffic light", "confidence": 0.9, "xyxy": [10, 10, 30, 50]},
    {"class_name": "traffic light", "confidence": 0.7, "xyxy": [11, 11, 31, 51]},
    {"class_name": "stop sign", "confidence": 0.8, "xyxy": [10, 10, 30, 50]},
  ]

  kept = non_maximum_suppression(detections)

  assert [(item["class_name"], item["confidence"]) for item in kept] == [
    ("traffic light", 0.9), ("stop sign", 0.8),
  ]


def test_relevance_stays_unknown_on_single_or_disagreeing_signal_heads():
  red = {"class_name": "traffic light", "confidence": 0.8, "xyxy": [300, 50, 330, 100], "phase": "red"}
  second_red = {"class_name": "traffic light", "confidence": 0.7, "xyxy": [500, 60, 530, 110], "phase": "red"}
  yellow = {"class_name": "traffic light", "confidence": 0.7, "xyxy": [500, 60, 530, 110], "phase": "yellow"}

  assert frame_decision("traffic_signal", [red], 1000, 600) == {
    "object_detected": True, "relevance": "unknown", "phase_evidence": "red", "phase": "unknown",
  }
  assert frame_decision("traffic_signal", [red, yellow], 1000, 600) == {
    "object_detected": True, "relevance": "unknown", "phase_evidence": "unknown", "phase": "unknown",
  }
  assert frame_decision("traffic_signal", [red, second_red], 1000, 600) == {
    "object_detected": True, "relevance": "candidate", "phase_evidence": "red", "phase": "red",
  }


def test_temporal_confirmation_and_phase_transitions_require_two_frames():
  def frame(index, phase, relevance="candidate"):
    return {
      "frame_index": index,
      "lead_s": 10 - index,
      "distance_m": 50 - index * 5,
      "decision": {"object_detected": True, "relevance": relevance, "phase": phase},
    }

  frames = [frame(0, "yellow"), frame(1, "yellow"), frame(2, "unknown", "unknown"),
            frame(3, "red"), frame(4, "red")]

  confirmation = first_consecutive(
    frames, lambda item: item["decision"]["relevance"] == "candidate" and item["decision"]["phase"] == "red",
  )
  assert confirmation["frame_index"] == 4
  assert stable_phase_transitions(frames) == [
    {"phase": "yellow", "lead_s": 9, "distance_m": 45},
    {"phase": "red", "lead_s": 6, "distance_m": 30},
  ]


def test_required_deceleration_uses_current_speed_and_remaining_distance():
  assert required_constant_decel(10.0, 25.0) == 2.0
  assert required_constant_decel(10.0, 0.0) is None
  assert isclose(jerk_limited_stop_distance(10.0), 40.6927083333)
  assert isclose(jerk_limited_stop_distance(1.0), 0.9428090416)
