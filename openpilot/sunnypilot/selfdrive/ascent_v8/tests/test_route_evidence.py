import json

from openpilot.sunnypilot.selfdrive.ascent_v8.route_evidence import (
  analyze_files,
  curve_candidates,
  stop_candidates,
  summarize_curves,
)


def sample(second: float, speed: float, *, brake=False, lead=None, model_stop=False, plan_stop=False,
           plan_lead=False, plan_accel=0.0, long_active=False, output_brake=0.0):
  return {
    "mono_ns": int(second * 1e9),
    "vehicle": {"v_ego": speed, "brake_pressed": brake},
    "model": {"should_stop": model_stop},
    "plan": {"should_stop": plan_stop, "has_lead": plan_lead, "a_target": plan_accel},
    "control": {"long_active": long_active, "output_brake": output_brake},
    "evidence": {"lead_distance_m": lead},
  }


def test_lead_turns_away_and_model_stop_arrives_after_manual_stop():
  samples = [
    sample(0, 11.0, lead=18.0),
    sample(1, 8.0, lead=12.0),
    sample(2, 5.0),
    sample(3, 2.0, brake=True),
    sample(4, 0.0, brake=True),
    sample(5, 0.0, brake=True, model_stop=True),
  ]

  assert stop_candidates("route", samples) == [{
    "route": "route",
    "approach_mono_ns": 0,
    "stopped_mono_ns": 4_000_000_000,
    "approach_speed_mps": 11.0,
    "driver_braked": True,
    "lead_seen": True,
    "lead_lost_before_stop_s": 3.0,
    "model_stop_while_moving": False,
    "first_model_stop_relative_s": 1.0,
    "planner_stop": False,
    "comma_longitudinal_active": False,
    "comma_brake_output": False,
    "response_timing": {
      "model_stop": None,
      "planner_stop": None,
      "planner_lead": None,
      "planner_decel": None,
      "driver_brake": {"lead_s": 1.0, "distance_m": 1.0},
      "comma_longitudinal": None,
      "comma_brake": None,
    },
    "label": "unreviewed",
  }]


def test_standstill_frames_do_not_duplicate_candidates():
  samples = [sample(0, 6.0), sample(1, 0.2), sample(2, 0.0), sample(3, 0.1)]
  assert len(stop_candidates("route", samples)) == 1


def test_stop_response_timing_starts_at_current_approach_and_integrates_distance():
  samples = [
    sample(-2, 0.0, model_stop=True),
    sample(0, 10.0),
    sample(1, 8.0, model_stop=True, plan_lead=True),
    sample(2, 5.0, plan_stop=True, plan_accel=-0.5, long_active=True),
    sample(3, 2.0, brake=True, output_brake=0.2),
    sample(4, 0.0, brake=True),
  ]

  event = stop_candidates("route", samples)[0]

  assert event["response_timing"] == {
    "model_stop": {"lead_s": 3.0, "distance_m": 11.0},
    "planner_stop": {"lead_s": 2.0, "distance_m": 4.5},
    "planner_lead": {"lead_s": 3.0, "distance_m": 11.0},
    "planner_decel": {"lead_s": 2.0, "distance_m": 4.5},
    "driver_brake": {"lead_s": 1.0, "distance_m": 1.0},
    "comma_longitudinal": {"lead_s": 2.0, "distance_m": 4.5},
    "comma_brake": {"lead_s": 1.0, "distance_m": 1.0},
  }


def curve_sample(second: float, speed: float, curvature: float, *, lane=0.8, brake=False, steering=False,
                 saturated=False, left=False, right=False, segment=0):
  return {
    "mono_ns": int(second * 1e9),
    "segment": segment,
    "vehicle": {
      "v_ego": speed,
      "brake_pressed": brake,
      "steering_pressed": steering,
      "left_blinker": left,
      "right_blinker": right,
    },
    "curvature": curvature,
    "lane_confidence": lane,
    "steering_saturated": saturated,
    "lat_active": True,
  }


def test_curve_replay_scores_slowing_lane_confidence_and_saturation():
  samples = [
    curve_sample(0.0, 10.0, 0.003),
    curve_sample(0.5, 9.0, 0.005, brake=True, left=True),
    curve_sample(1.0, 8.0, 0.010, lane=0.4, saturated=True, left=True),
    curve_sample(1.5, 7.0, 0.0025, steering=True),
    curve_sample(2.1, 7.0, 0.001),
  ]

  events = curve_candidates("route", samples)

  assert len(events) == 1
  event = events[0]
  assert event["event_type"] == "curve_with_turn_signal"
  assert event["turn_signal"] == "left"
  assert event["direction"] == "left"
  assert event["duration_s"] == 1.5
  assert event["entry_speed_mps"] == 10.0
  assert event["minimum_speed_mps"] == 7.0
  assert event["speed_at_peak_curvature_mps"] == 8.0
  assert event["peak_curvature"] == 0.01
  assert event["peak_lateral_accel_mps2"] == 0.64
  assert event["standard_target_speed_mps"] == 12.649
  assert event["target_excess_at_peak_mps"] == -4.649
  assert event["speed_reduction_before_peak_mps"] == 2.0
  assert event["lane_confidence_min"] == 0.4
  assert event["lane_confidence_median"] == 0.8
  assert event["driver_braked_before_peak"]
  assert event["driver_steering_override"]
  assert event["steering_saturated"]
  assert summarize_curves(events)["curves_with_turn_signal"] == 1


def test_analyze_files_reports_coverage(tmp_path):
  journal = tmp_path / "route.jsonl"
  rows = [{"schema": 1, "kind": "ascent_v8_calibration", "route": "route-a"}, sample(0, 6.0), sample(1, 0.0)]
  journal.write_text("".join(json.dumps(row) + "\n" for row in rows))

  result = analyze_files([journal])

  assert result["routes"] == [{"route": "route-a", "samples": 2, "candidate_stops": 1}]
  assert result["coverage"]["recorded_journals"] == 1
  assert result["coverage"]["unreviewed_stop_candidates"] == 1
  assert result["coverage"]["qualified_routes"] == 0


def test_analyze_files_applies_only_confirmed_video_labels(tmp_path):
  journal = tmp_path / "route.jsonl"
  rows = [
    {"schema": 1, "kind": "ascent_v8_calibration", "route": "route-a"},
    sample(0, 6.0), sample(1, 0.0), sample(4, 7.0), sample(5, 0.0),
    sample(8, 8.0), sample(9, 0.0),
  ]
  journal.write_text("".join(json.dumps(row) + "\n" for row in rows))
  labels = tmp_path / "labels.jsonl"
  label_rows = [
    {"route": "route-a", "approx_mono_ns": 1_100_000_000, "control_type": "stop_sign",
     "state": "stop_required", "source": "qcamera", "video_review": "confirmed"},
    {"route": "route-a", "approx_mono_ns": 5_000_000_000, "control_type": "traffic_signal",
     "state": "red", "source": "driver_report", "video_review": "pending"},
    {"route": "route-a", "approx_mono_ns": 9_000_000_000, "control_type": "lead_stop",
     "state": "lead_stationary", "source": "qcamera", "video_review": "confirmed"},
    {"route": "route-a", "approx_mono_ns": 20_000_000_000, "control_type": "traffic_signal",
     "state": "red", "source": "qcamera", "video_review": "confirmed"},
  ]
  labels.write_text("".join(json.dumps(row) + "\n" for row in label_rows))

  result = analyze_files([journal], labels)

  assert result["candidate_stops"][0]["label"] == "stop_sign"
  assert result["candidate_stops"][0]["label_state"] == "stop_required"
  assert result["candidate_stops"][1]["label"] == "unreviewed"
  assert result["candidate_stops"][2]["label"] == "lead_stop"
  assert result["coverage"]["qualified_routes"] == 1
  assert result["coverage"]["video_confirmed_approaches"] == 2
  assert result["coverage"]["labeled_stop_sign_approaches"] == 1
  assert result["coverage"]["labeled_signal_approaches"] == 0
  assert result["coverage"]["labeled_lead_stop_approaches"] == 1
  assert result["coverage"]["unreviewed_stop_candidates"] == 1
  assert result["coverage"]["unmatched_confirmed_labels"] == 1
  assert result["response_summary"]["stop_sign"]["approaches"] == 1
  assert result["response_summary"]["lead_stop"]["approaches"] == 1
  assert result["response_summary"]["traffic_control_total"] == {
    "approaches": 1,
    "model_stop_while_moving": 0,
    "planner_stop": 0,
    "comma_longitudinal_active": 0,
    "comma_brake_output": 0,
  }
