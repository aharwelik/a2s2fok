from pathlib import Path

from tools.ascent_v8_route_scan import confirmed_runs, run_counts_by_confidence, select_route_videos


def observation(class_name: str, route_offset_s: float, confidence: float = 0.5) -> dict:
  return {
    "class_name": class_name,
    "route_offset_s": route_offset_s,
    "segment": int(route_offset_s // 60),
    "video_offset_s": route_offset_s % 60,
    "confidence": confidence,
    "xyxy": [10.0, 20.0, 30.0, 40.0],
  }


def test_confirmed_runs_require_consecutive_frames_of_same_class():
  observations = [
    observation("traffic light", 1.0, 0.4),
    observation("traffic light", 2.0, 0.8),
    observation("traffic light", 5.0, 0.9),
    observation("stop sign", 8.0, 0.7),
    observation("stop sign", 9.0, 0.6),
  ]

  assert confirmed_runs(observations, sample_interval_s=1.0) == [
    {
      "class_name": "traffic light",
      "first_route_offset_s": 1.0,
      "last_route_offset_s": 2.0,
      "confirmation_route_offset_s": 2.0,
      "confirmation_segment": 0,
      "confirmation_video_offset_s": 2.0,
      "frames": 2,
      "max_confidence": 0.8,
      "best_segment": 0,
      "best_video_offset_s": 2.0,
      "best_xyxy": [10.0, 20.0, 30.0, 40.0],
    },
    {
      "class_name": "stop sign",
      "first_route_offset_s": 8.0,
      "last_route_offset_s": 9.0,
      "confirmation_route_offset_s": 9.0,
      "confirmation_segment": 0,
      "confirmation_video_offset_s": 9.0,
      "frames": 2,
      "max_confidence": 0.7,
      "best_segment": 0,
      "best_video_offset_s": 8.0,
      "best_xyxy": [10.0, 20.0, 30.0, 40.0],
    },
  ]


def test_confirmed_runs_join_adjacent_route_segments():
  observations = [observation("stop sign", 59.0), observation("stop sign", 60.0)]

  assert confirmed_runs(observations, sample_interval_s=1.0)[0]["frames"] == 2


def test_run_counts_by_confidence_reapplies_temporal_confirmation():
  observations = [
    observation("stop sign", 1.0, 0.8),
    observation("stop sign", 2.0, 0.4),
    observation("traffic light", 5.0, 0.9),
    observation("traffic light", 6.0, 0.7),
  ]

  assert run_counts_by_confidence(observations, 1.0, (0.1, 0.5)) == {
    "0.10": {"confirmed_runs": 2, "stop_sign_runs": 1, "traffic_light_runs": 1},
    "0.50": {"confirmed_runs": 1, "stop_sign_runs": 0, "traffic_light_runs": 1},
  }


def test_select_route_videos_requires_choice_for_mixed_root():
  videos = [Path("route-a--0/qcamera.ts"), Path("route-b--0/qcamera.ts")]

  try:
    select_route_videos(videos, None)
  except ValueError as error:
    assert str(error) == "multiple routes found; provide --route"
  else:
    raise AssertionError("mixed route root was accepted")

  route, selected = select_route_videos(videos, "route-b")
  assert route == "route-b"
  assert selected == [Path("route-b--0/qcamera.ts")]
